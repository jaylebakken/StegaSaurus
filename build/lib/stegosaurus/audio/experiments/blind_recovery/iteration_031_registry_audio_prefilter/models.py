"""Define records for the registry-audio prefilter experiment.

These records keep iteration 031 readable by separating the measured outputs
from the localization process. They are experiment diagnostics, not product
contracts.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class PrefilterCandidate:
    """Record one localized candidate window."""

    crop_window_start_seconds: float
    registry_block_index: int
    registry_block_start_seconds: float
    score: float
    nearest_boundary_error_seconds: float
    useful_boundary_hit: bool


@dataclass(frozen=True, slots=True)
class PrefilterTrial:
    """Summarize one crop-localization trial."""

    source_file: str
    crop_seconds: float
    crop_start_seconds: float
    searched_coarse_windows: int
    useful_boundaries: int
    top1_hit: bool
    top5_hit: bool
    best_error_seconds: float | None
    elapsed_ms: float


@dataclass(frozen=True, slots=True)
class TrackPrefilterSummary:
    """Summarize shared prefilter performance for one registered song."""

    source_file: str
    embedded_blocks: int
    trials: int
    top1_hits: int
    top5_hits: int
    median_elapsed_ms: float
    workflow_note: str
