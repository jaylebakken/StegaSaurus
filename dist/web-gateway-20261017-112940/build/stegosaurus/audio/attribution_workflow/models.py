"""Define V4 known-song registry and verification records.

The V4 workflow is registry-backed. A ``SongRecord`` stores source-audio
geometry and cached localization fingerprints. Each ``ExportRecord`` stores one
recipient/export watermark record for that song. A verification job localizes a
clean suspicious excerpt once per song, then fans those candidate windows out
across the export records.

Pseudocode:
    source WAV -> SongRecord + SongFingerprintIndex
    source WAV + recipient + optional parent export -> ExportRecord
    suspicious excerpt + song -> KnownSongVerification

These records deliberately do not model cloud sync, account identity, or
recorded-audio robustness. Export parentage is registry metadata; child exports
are still encoded from the clean source audio rather than stacked onto parent
audio.
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
    parent_export_id: str | None
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


@dataclass(frozen=True, slots=True)
class RecoveryProfile:
    """Declare localization and phase-search cost knobs for verification."""

    candidate_count: int = 5
    coarse_stride_seconds: float = 5.0
    fine_radius_seconds: float = 3.0
    fine_stride_seconds: float = 0.5
    phase_radius_seconds: float = 0.30
    phase_stride_seconds: float = 0.025
    maximum_rs_cost: int = 16
    maximum_expanded_candidates: int = 10
    fallback_export_count: int = 2


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

    def add_export(
        self,
        song_id: str,
        recipient_label: str,
        handle: bytes,
        record: BlockAttributionRecord,
        parent_export_id: str | None = None,
    ) -> ExportRecord:
        """Register one recipient/export watermark record for a song."""

        if song_id not in self.songs:
            raise ValueError("song_id is not registered")
        if parent_export_id is not None:
            parent = self.exports.get(parent_export_id)
            if parent is None:
                raise ValueError("parent_export_id is not registered")
            if parent.song_id != song_id:
                raise ValueError("parent_export_id must belong to the same song")
        normalized = recipient_label.strip()
        if not normalized:
            raise ValueError("recipient_label must not be empty")
        export = ExportRecord(str(uuid4()), song_id, normalized, parent_export_id, bytes(handle), record)
        self.exports[export.export_id] = export
        return export

    def exports_for_song(self, song_id: str) -> tuple[ExportRecord, ...]:
        """Return export records for one registered song in stable label order."""

        if song_id not in self.songs:
            raise ValueError("song_id is not registered")
        return tuple(sorted((export for export in self.exports.values() if export.song_id == song_id), key=lambda item: item.recipient_label))

    def export_lineage(self, export_id: str) -> tuple[ExportRecord, ...]:
        """Return one export's registry ancestry from root to selected export."""

        lineage = []
        current = self.exports.get(export_id)
        if current is None:
            raise ValueError("export_id is not registered")
        while current is not None:
            lineage.append(current)
            if current.parent_export_id is None:
                break
            current = self.exports.get(current.parent_export_id)
            if current is None:
                raise ValueError("export parent chain is incomplete")
        return tuple(reversed(lineage))


def as_vector(values: tuple[float, ...]) -> np.ndarray:
    """Convert an immutable fingerprint to a numeric vector."""

    return np.asarray(values, dtype=np.float64)
