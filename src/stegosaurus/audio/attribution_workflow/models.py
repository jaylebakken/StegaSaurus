"""Define V4 known-song registry and verification records.

The V4 workflow is registry-backed. A ``SongRecord`` stores source-audio
geometry and cached localization fingerprints. Each ``ExportRecord`` stores one
recipient/export watermark record for that song. A verification job localizes a
clean suspicious excerpt once per song, then fans those candidate windows out
across the export records.

Pseudocode:
    source WAV -> SongRecord + SongFingerprintIndex
    source WAV + recipient -> ExportRecord
    suspicious excerpt + song -> KnownSongVerification

These records deliberately do not model cloud sync, account identity, or
recorded-audio robustness.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from uuid import uuid4

import numpy as np

from ..attribution import BlockAttributionRecord
from ..pilot import PcmAudio


@dataclass(frozen=True, slots=True)
class SongFingerprintIndex:
    """Cache source-song block fingerprints shared by all export records."""

    block_seconds: float
    fingerprints: tuple[tuple[float, ...], ...]


@dataclass(frozen=True, slots=True)
class SongRecord:
    """Represent one registered source song for known-song attribution."""

    song_id: str
    title: str
    source_audio: PcmAudio
    fingerprint_index: SongFingerprintIndex

    @property
    def duration_seconds(self) -> float:
        """Return the source-song duration."""

        return self.source_audio.duration_seconds


@dataclass(frozen=True, slots=True)
class ExportRecord:
    """Store one recipient/export watermark record for a registered song."""

    export_id: str
    song_id: str
    recipient_label: str
    handle: bytes
    attribution_record: BlockAttributionRecord


@dataclass(frozen=True, slots=True)
class LocalizationCandidate:
    """Rank one crop-local window that may contain a registered song block."""

    crop_window_start_seconds: float
    registry_block_index: int
    score: float


@dataclass(frozen=True, slots=True)
class ExportAttributionResult:
    """Report one export record's pooled attribution evidence."""

    export_id: str
    recipient_label: str
    accepted: bool
    pooled_rs_cost: int
    recovered_windows: int
    rank: int


@dataclass(frozen=True, slots=True)
class KnownSongVerification:
    """Summarize a known-song attribution fanout job."""

    song_id: str
    accepted: bool
    matched_export_id: str | None
    matched_recipient_label: str | None
    candidates: tuple[LocalizationCandidate, ...]
    ranked_exports: tuple[ExportAttributionResult, ...]
    prefilter_elapsed_ms: float
    verification_elapsed_ms: float


@dataclass(slots=True)
class InMemoryAttributionCatalog:
    """Keep V4 song and export records in memory for the desktop demo."""

    songs: dict[str, SongRecord] = field(default_factory=dict)
    exports: dict[str, ExportRecord] = field(default_factory=dict)

    def add_song(self, title: str, source_audio: PcmAudio, fingerprint_index: SongFingerprintIndex) -> SongRecord:
        """Register one source song and return its record."""

        normalized = title.strip()
        if not normalized:
            raise ValueError("song title must not be empty")
        song = SongRecord(str(uuid4()), normalized, source_audio, fingerprint_index)
        self.songs[song.song_id] = song
        return song

    def add_export(self, song_id: str, recipient_label: str, handle: bytes, record: BlockAttributionRecord) -> ExportRecord:
        """Register one recipient/export watermark record for a song."""

        if song_id not in self.songs:
            raise ValueError("song_id is not registered")
        normalized = recipient_label.strip()
        if not normalized:
            raise ValueError("recipient_label must not be empty")
        export = ExportRecord(str(uuid4()), song_id, normalized, bytes(handle), record)
        self.exports[export.export_id] = export
        return export

    def exports_for_song(self, song_id: str) -> tuple[ExportRecord, ...]:
        """Return export records for one registered song in stable label order."""

        if song_id not in self.songs:
            raise ValueError("song_id is not registered")
        return tuple(sorted((export for export in self.exports.values() if export.song_id == song_id), key=lambda item: item.recipient_label))


def as_vector(values: tuple[float, ...]) -> np.ndarray:
    """Convert an immutable fingerprint to a numeric vector."""

    return np.asarray(values, dtype=np.float64)
