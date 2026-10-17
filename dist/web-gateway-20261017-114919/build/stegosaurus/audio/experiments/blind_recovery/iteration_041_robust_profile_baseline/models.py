"""Define robust-profile baseline result records.

The robust profile is still a measured candidate rather than a universal
robustness claim. These records capture whether parent/child visibility,
arbitrary crop, and named synthetic distress all pass the current baseline.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RobustScenario:
    """Summarize one robust-profile baseline scenario."""

    scenario: str
    visible_label: str
    distress: str
    accepted_label: str | None
    best_label: str
    best_rs_cost: int
    false_accept_count: int
    status: str

