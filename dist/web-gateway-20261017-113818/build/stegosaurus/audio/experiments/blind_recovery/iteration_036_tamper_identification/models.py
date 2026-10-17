"""Define records for tamper-identification diagnostics.

The experiment separates attribution acceptance from tamper identification. A
file may contain no accepted handle while still showing stronger watermark-like
evidence than an unwatermarked source.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ClaimDiagnostic:
    """Record diagnostic evidence for one retained claim."""

    claim_name: str
    recovered: bool
    pooled_rs_cost: int
    carrier_erasures: int
    known_bit_errors: int
    block_votes: int


@dataclass(frozen=True, slots=True)
class IdentificationOutcome:
    """Summarize one tamper-identification scenario."""

    scenario: str
    expected_class: str
    predicted_class: str
    accepted_claims: int
    best_rs_cost: int
    second_best_rs_cost: int | None
    rs_gap: int | None
    matched_expected: bool
