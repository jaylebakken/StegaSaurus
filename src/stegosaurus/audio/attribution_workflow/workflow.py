"""Orchestrate the V4 known-song attribution workflow.

The workflow is intentionally product-shaped: register a source song, create
recipient/export watermarked copies, then verify a clean suspicious excerpt
against the exports for a selected song. Source localization is performed once
per song and reused across the export fanout.

It does not claim unknown-song search, recorded-audio recovery, or platform
transcode robustness.
"""

from __future__ import annotations

from .fanout import verify_export_fanout
from .fingerprints import build_song_fingerprint_index, localize_excerpt
from .models import ExportRecord, InMemoryAttributionCatalog, KnownSongVerification, SongRecord
from ..attribution import BlockAttributionCodec
from ..pilot import PcmAudio


class KnownSongAttributionWorkflow:
    """Register songs, create exports, and verify clean suspicious excerpts."""

    def __init__(self, master_secret: bytes = b"stegosaurus-v4-known-song-secret") -> None:
        """Initialize an in-memory V4 workflow with one attribution codec."""

        self.catalog = InMemoryAttributionCatalog()
        self.codec = BlockAttributionCodec(master_secret)

    def register_song(self, title: str, source_audio: PcmAudio, block_seconds: float = 30.0) -> SongRecord:
        """Register a source song and cache its clean localization fingerprints."""

        index = build_song_fingerprint_index(source_audio, block_seconds)
        return self.catalog.add_song(title, source_audio, index)

    def create_export(self, song_id: str, recipient_label: str, handle: bytes) -> tuple[ExportRecord, PcmAudio]:
        """Create one watermarked recipient/export copy for a registered song."""

        song = self.catalog.songs.get(song_id)
        if song is None:
            raise ValueError("song_id is not registered")
        embedding = self.codec.embed(song.source_audio, handle, block_seconds=song.fingerprint_index.block_seconds)
        export = self.catalog.add_export(song.song_id, recipient_label, handle, embedding.record)
        return export, embedding.audio

    def verify_excerpt(self, song_id: str, excerpt: PcmAudio) -> KnownSongVerification:
        """Identify the matching export record for a clean excerpt of a known song."""

        song = self.catalog.songs.get(song_id)
        if song is None:
            raise ValueError("song_id is not registered")
        exports = self.catalog.exports_for_song(song_id)
        if not exports:
            raise ValueError("song has no export records")
        candidates, prefilter_elapsed_ms = localize_excerpt(excerpt, song.fingerprint_index)
        ranked, verification_elapsed_ms = verify_export_fanout(self.codec, excerpt, exports, candidates)
        accepted = tuple(result for result in ranked if result.accepted)
        winner = accepted[0] if accepted else None
        return KnownSongVerification(
            song.song_id,
            winner is not None,
            None if winner is None else winner.export_id,
            None if winner is None else winner.recipient_label,
            candidates,
            ranked,
            prefilter_elapsed_ms,
            verification_elapsed_ms,
        )
