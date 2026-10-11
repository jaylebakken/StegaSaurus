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
    SongFingerprintIndex,
    SongRecord,
)
from .workflow import KnownSongAttributionWorkflow

__all__ = [
    "ExportAttributionResult",
    "ExportRecord",
    "InMemoryAttributionCatalog",
    "KnownSongAttributionWorkflow",
    "KnownSongVerification",
    "LocalizationCandidate",
    "SongFingerprintIndex",
    "SongRecord",
    "build_song_fingerprint_index",
    "localize_excerpt",
    "verify_export_fanout",
]
