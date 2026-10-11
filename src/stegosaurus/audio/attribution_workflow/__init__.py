"""Expose the V4 known-song attribution workflow.

V4 promotes the measured clean-file leak workflow: a user selects a registered
song, the app localizes a suspicious excerpt against the song's source audio,
then attribution evidence is pooled across that song's recipient/export records.

This package does not claim recorded-audio, compression, or unknown-song
discovery robustness. Those remain experiment tracks until measured here.
"""

from __future__ import annotations

from .fanout import verify_export_fanout
from .fingerprints import build_song_fingerprint_index, localize_excerpt
from .models import (
    ExportAttributionResult,
    ExportRecord,
    InMemoryAttributionCatalog,
    KnownSongVerification,
    LocalizationCandidate,
    RecoveryProfile,
    SongFingerprintIndex,
    SongRecord,
)
from .workflow import CLEAN_BLOCK_SECONDS, ROBUST_BLOCK_SECONDS, KnownSongAttributionWorkflow

__all__ = [
    "CLEAN_BLOCK_SECONDS",
    "ExportAttributionResult",
    "ExportRecord",
    "InMemoryAttributionCatalog",
    "KnownSongAttributionWorkflow",
    "KnownSongVerification",
    "LocalizationCandidate",
    "RecoveryProfile",
    "ROBUST_BLOCK_SECONDS",
    "SongFingerprintIndex",
    "SongRecord",
    "build_song_fingerprint_index",
    "localize_excerpt",
    "verify_export_fanout",
]
