"""Define records for the chain-ledger attack-surface experiment.

The ledger model separates system-observed facts from user-supplied labels. A
chain event can say "this registry created handle X as a child of event Y";
labels such as recipient names remain editable context, not proof of fault.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ChainLedgerEvent:
    """Represent one append-only custody-chain event."""

    event_id: str
    parent_event_id: str | None
    handle_hex: str
    trust_level: str
    user_label: str
    system_fact: str


@dataclass(frozen=True, slots=True)
class EventEvidence:
    """Record verification evidence for one chain event."""

    event_id: str
    handle_hex: str
    recovered: bool
    pooled_rs_cost: int
    block_votes: int
    rank: int


@dataclass(frozen=True, slots=True)
class ScenarioOutcome:
    """Summarize one chain-ledger stress scenario."""

    scenario: str
    chain_length: int
    transform: str
    recovered_events: int
    latest_event_recovered: bool
    false_or_unexpected_recoveries: int
    best_event_id: str | None
    minimum_rs_cost: int | None
    status: str
