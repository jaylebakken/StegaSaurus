"""Define result records for the crop-distortion chain baseline.

The baseline keeps the production workflow intact: a known song is registered,
parent and child exports are generated from the clean master, a suspicious
excerpt is cropped from one visible export, and the verifier tries to identify
that visible export.

The model separates ranking, acceptance, and chain ambiguity. Passing requires
the visible event to be accepted while parent, sibling, and unrelated events are
not accepted.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    """Summarize one crop-plus-distortion verification scenario."""

    scenario: str
    visible_label: str
    distress: str
    crop_start_seconds: float
    crop_duration_seconds: float
    accepted: bool
    matched_label: str | None
    matched_expected: bool
    false_accept_count: int
    correct_rank: int | None
    correct_rs_cost: int | None
    best_label: str | None
    best_rs_cost: int | None
    localization_blocks: tuple[int, ...]
    status: str

