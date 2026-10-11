"""Define records for the registry-only chain-update experiment.

Independent stacked re-watermarking behaved like destructive interference in
iteration 035. This suite tests the alternative product rule:

    clean registered master + selected event handle -> exported audio
    registry event graph -> parent/child history

Only the selected event should be recoverable from audio. Parent, sibling, and
unrelated events should remain registry context rather than additional visible
claims in the waveform.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RegistryOnlyEvent:
    """Represent one custody-chain event stored in the registry."""

    event_id: str
    parent_event_id: str | None
    handle_hex: str
    trust_level: str
    user_label: str
    system_fact: str


@dataclass(frozen=True, slots=True)
class EventClaimEvidence:
    """Record verification evidence for one retained event claim."""

    event_id: str
    parent_event_id: str | None
    recovered: bool
    pooled_rs_cost: int
    block_votes: int
    rank: int


@dataclass(frozen=True, slots=True)
class ScenarioOutcome:
    """Summarize one registry-only chain-update scenario."""

    scenario: str
    visible_event_id: str | None
    expected_accepted_event_id: str | None
    accepted_event_ids: tuple[str, ...]
    sibling_or_parent_recovered: bool
    unrelated_recovered: bool
    best_event_id: str | None
    minimum_rs_cost: int | None
    status: str

