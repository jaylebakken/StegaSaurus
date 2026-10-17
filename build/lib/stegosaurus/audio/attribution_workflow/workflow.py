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
from .models import ExportRecord, InMemoryAttributionCatalog, KnownSongVerification, LocalizationCandidate, RecoveryProfile, SongRecord
from ..attribution import BlockAttributionCodec
from ..pilot import PcmAudio


CLEAN_BLOCK_SECONDS = 30.0
ROBUST_BLOCK_SECONDS = 15.0


class KnownSongAttributionWorkflow:
    """Register songs, create exports, and verify clean suspicious excerpts."""

    def __init__(self, master_secret: bytes = b"stegosaurus-v4-known-song-secret") -> None:
        """Initialize an in-memory V4 workflow with one attribution codec."""

        self.catalog = InMemoryAttributionCatalog()
        self.codec = BlockAttributionCodec(master_secret)

    def register_song(self, title: str, source_audio: PcmAudio, block_seconds: float = CLEAN_BLOCK_SECONDS) -> SongRecord:
        """Register a source song and cache its clean localization fingerprints."""

        index = build_song_fingerprint_index(source_audio, block_seconds)
        return self.catalog.add_song(title, source_audio, index)

    def register_robust_song(self, title: str, source_audio: PcmAudio) -> SongRecord:
        """Register a source song with the measured robust block profile."""

        return self.register_song(title, source_audio, ROBUST_BLOCK_SECONDS)

    def create_export(self, song_id: str, recipient_label: str, handle: bytes) -> tuple[ExportRecord, PcmAudio]:
        """Create one watermarked recipient/export copy for a registered song."""

        return self.create_child_export(song_id, recipient_label, handle)

    def create_child_export(
        self,
        song_id: str,
        recipient_label: str,
        handle: bytes,
        parent_export_id: str | None = None,
    ) -> tuple[ExportRecord, PcmAudio]:
        """Create one registry-linked export from the clean registered source."""

        song = self.catalog.songs.get(song_id)
        if song is None:
            raise ValueError("song_id is not registered")
        embedding = self.codec.embed(song.source_audio, handle, block_seconds=song.fingerprint_index.block_seconds)
        export = self.catalog.add_export(song.song_id, recipient_label, handle, embedding.record, parent_export_id)
        return export, embedding.audio

    def verify_excerpt(self, song_id: str, excerpt: PcmAudio, profile: RecoveryProfile | None = None) -> KnownSongVerification:
        """Identify the matching export record for a clean excerpt of a known song."""

        song = self.catalog.songs.get(song_id)
        if song is None:
            raise ValueError("song_id is not registered")
        exports = self.catalog.exports_for_song(song_id)
        if not exports:
            raise ValueError("song has no export records")
        active_profile = profile or RecoveryProfile()
        candidates, prefilter_elapsed_ms = localize_excerpt(
            excerpt,
            song.fingerprint_index,
            active_profile.candidate_count,
            active_profile.coarse_stride_seconds,
            active_profile.fine_radius_seconds,
            active_profile.fine_stride_seconds,
        )
        candidates = _expand_consecutive_candidates(
            excerpt,
            song.fingerprint_index.block_seconds,
            candidates,
            active_profile.maximum_expanded_candidates,
        )
        return self._verify_candidates(song_id, excerpt, candidates, prefilter_elapsed_ms, active_profile)

    def _verify_candidates(
        self,
        song_id: str,
        excerpt: PcmAudio,
        candidates: tuple[LocalizationCandidate, ...],
        prefilter_elapsed_ms: float,
        profile: RecoveryProfile,
        exports: tuple[ExportRecord, ...] | None = None,
    ) -> KnownSongVerification:
        """Verify already-localized candidates with one recovery profile."""

        song = self.catalog.songs.get(song_id)
        if song is None:
            raise ValueError("song_id is not registered")
        active_exports = exports or self.catalog.exports_for_song(song_id)
        if not active_exports:
            raise ValueError("song has no export records")
        ranked, verification_elapsed_ms = verify_export_fanout(
            self.codec,
            excerpt,
            active_exports,
            candidates,
            profile.phase_radius_seconds,
            profile.phase_stride_seconds,
            profile.maximum_rs_cost,
        )
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

    def verify_excerpt_with_fallbacks(self, song_id: str, excerpt: PcmAudio) -> KnownSongVerification:
        """Verify an excerpt with clean first-pass and distressed fallback budgets."""

        profile = RecoveryProfile()
        song = self.catalog.songs.get(song_id)
        if song is None:
            raise ValueError("song_id is not registered")
        candidates, prefilter_elapsed_ms = localize_excerpt(
            excerpt,
            song.fingerprint_index,
            profile.candidate_count,
            profile.coarse_stride_seconds,
            profile.fine_radius_seconds,
            profile.fine_stride_seconds,
        )
        candidates = _expand_consecutive_candidates(
            excerpt,
            song.fingerprint_index.block_seconds,
            candidates,
            profile.maximum_expanded_candidates,
        )
        first_pass = self._verify_candidates(song_id, excerpt, candidates, prefilter_elapsed_ms, profile)
        if first_pass.accepted:
            return first_pass
        wide_phase = RecoveryProfile(phase_radius_seconds=4.0, phase_stride_seconds=1.0)
        second_pass = self._verify_candidates(song_id, excerpt, candidates, prefilter_elapsed_ms, wide_phase)
        if second_pass.accepted:
            return second_pass
        shortlist = _shortlist_exports(self.catalog.exports_for_song(song_id), second_pass, profile.fallback_export_count)
        deep_phase = RecoveryProfile(phase_radius_seconds=4.0, phase_stride_seconds=0.25)
        deep_pass = self._verify_candidates(song_id, excerpt, candidates, prefilter_elapsed_ms, deep_phase, shortlist)
        accepted = tuple(result for result in deep_pass.ranked_exports if result.accepted)
        return deep_pass if len(accepted) == 1 else second_pass


def _expand_consecutive_candidates(
    excerpt: PcmAudio,
    block_seconds: float,
    candidates: tuple[LocalizationCandidate, ...],
    maximum_candidates: int,
) -> tuple[LocalizationCandidate, ...]:
    """Project localized anchors onto adjacent complete crop-local blocks."""

    if maximum_candidates < 1:
        raise ValueError("maximum_candidates must be positive")
    expanded: dict[tuple[float, int], LocalizationCandidate] = {}
    max_start = excerpt.duration_seconds - block_seconds
    for candidate in candidates:
        for offset in range(-4, 5):
            start = round(candidate.crop_window_start_seconds + offset * block_seconds, 3)
            block_index = candidate.registry_block_index + offset
            if start < 0 or start > max_start or block_index < 0:
                continue
            key = (start, block_index)
            projected = LocalizationCandidate(start, block_index, candidate.score)
            current = expanded.get(key)
            if current is None or projected.score > current.score:
                expanded[key] = projected
    ordered = sorted(expanded.values(), key=lambda item: (-item.score, item.crop_window_start_seconds, item.registry_block_index))
    selected = sorted(ordered[:maximum_candidates], key=lambda item: (item.crop_window_start_seconds, item.registry_block_index))
    return tuple(selected)


def _shortlist_exports(
    exports: tuple[ExportRecord, ...],
    verification: KnownSongVerification,
    fallback_export_count: int,
) -> tuple[ExportRecord, ...]:
    """Return the strongest registry records for expensive fallback search."""

    if fallback_export_count < 1:
        raise ValueError("fallback_export_count must be positive")
    by_id = {export.export_id: export for export in exports}
    selected = []
    for result in verification.ranked_exports:
        export = by_id.get(result.export_id)
        if export is not None:
            selected.append(export)
        if len(selected) == fallback_export_count:
            break
    return tuple(selected)
