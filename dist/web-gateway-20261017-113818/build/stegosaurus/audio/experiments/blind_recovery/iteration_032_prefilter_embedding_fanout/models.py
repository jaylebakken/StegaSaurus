"""Define records for the prefilter-to-embedding fanout experiment.

Iteration 032 measures a registry workflow rather than a new codec primitive:
one song has many recipient/export embedding records, a suspicious excerpt
comes from one of them, and shared crop localization feeds a small verification
fanout.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class SimulatedEmbeddingRecord:
    """Represent one recipient/export copy in the song registry."""

    label: str
    handle_hex: str
    is_leaked_copy: bool


@dataclass(frozen=True, slots=True)
class FanoutVerification:
    """Record one embedding-record verification after shared prefiltering."""

    label: str
    expected_match: bool
    recovered: bool
    pooled_rs_cost: int
    recovered_windows: int
    rank: int
    gate_passed: bool


@dataclass(frozen=True, slots=True)
class FanoutSummary:
    """Summarize whether the simulated registry fanout found the leaked copy."""

    source_file: str
    embedding_records: int
    crop_seconds: float
    crop_start_seconds: float
    prefilter_elapsed_ms: float
    verification_elapsed_ms: float
    correct_record_rank: int | None
    correct_record_recovered: bool
    false_acceptances: int
    workflow_passed: bool
