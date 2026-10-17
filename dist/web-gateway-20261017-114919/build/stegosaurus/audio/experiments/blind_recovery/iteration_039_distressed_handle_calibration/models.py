"""Define records for distressed handle-calibration experiments.

The suite treats handle assignment as part of the product pipeline. If a child
export cannot stay distinguishable from parent, sibling, and unrelated controls
under a named baseline crop-plus-distress recipe, the registry should discard
that candidate handle instead of shipping it.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class HandleTrial:
    """Summarize one calibrated handle-family trial."""

    trial_index: int
    parent_handle_hex: str
    child_handle_hex: str
    sibling_handle_hex: str
    unrelated_handle_hex: str
    best_label: str
    best_rs_cost: int
    second_label: str
    second_rs_cost: int
    rs_gap: int
    accepted_unique_child: bool
    status: str

