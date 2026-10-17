"""Test the production-facing blind-recovery decision policy.

The staged blind-recovery experiments produce votes from declared geometry
hypotheses. These tests cover only the application policy that turns such votes
into accept, reject, or abstain decisions. They do not claim blind handle
discovery or audio robustness beyond the measured experiment fixtures.
"""

from __future__ import annotations

import pytest

from stegosaurus.audio.attribution import (
    BlindRecoveryDecisionPolicy,
    BlindRecoveryStatus,
    BlindRecoveryVote,
)


def test_blind_recovery_policy_accepts_a_unique_low_burden_vote() -> None:
    """Accept a selected watermarked vote only when controls abstain and RS cost is low."""

    policy = BlindRecoveryDecisionPolicy(maximum_rs_error_cost=8, maximum_hypotheses=5)
    watermarked = BlindRecoveryVote(True, 2, "single_250ms_edge_loss", 4)
    unwatermarked = BlindRecoveryVote(False, 5, rejection_reason="bounded_search_exhausted")
    wrong_secret = BlindRecoveryVote(False, 5, rejection_reason="bounded_search_exhausted")

    decision = policy.decide(watermarked, (unwatermarked, wrong_secret))

    assert decision.status is BlindRecoveryStatus.ACCEPTED
    assert decision.accepted
    assert decision.reason == "unique_low_burden_success"
    assert decision.selected_stage == "single_250ms_edge_loss"
    assert decision.attempted_hypotheses == 5


def test_blind_recovery_policy_rejects_when_any_control_accepts() -> None:
    """Reject rather than attribute when an independent control also produces a success."""

    policy = BlindRecoveryDecisionPolicy()
    watermarked = BlindRecoveryVote(True, 1, "received_only", 4)
    unwatermarked = BlindRecoveryVote(True, 1, "received_only", 4)

    decision = policy.decide(watermarked, (unwatermarked,))

    assert decision.status is BlindRecoveryStatus.REJECTED
    assert decision.reason == "control_acceptance"
    assert not decision.accepted


def test_blind_recovery_policy_abstains_after_bounded_search_exhaustion() -> None:
    """Abstain when the staged search exhausts its declared hypotheses without a success."""

    policy = BlindRecoveryDecisionPolicy(maximum_hypotheses=5)
    watermarked = BlindRecoveryVote(False, 5)

    decision = policy.decide(watermarked)

    assert decision.status is BlindRecoveryStatus.ABSTAINED
    assert decision.reason == "bounded_search_exhausted"
    assert decision.attempted_hypotheses == 5


def test_blind_recovery_policy_abstains_on_ambiguous_or_high_cost_success() -> None:
    """Preserve uncertainty when a success is ambiguous or exceeds the configured RS burden."""

    policy = BlindRecoveryDecisionPolicy(maximum_rs_error_cost=8)

    ambiguous = policy.decide(BlindRecoveryVote(True, 2, "single_250ms_edge_loss", 4, ambiguous_successes=2))
    high_cost = policy.decide(BlindRecoveryVote(True, 2, "single_250ms_edge_loss", 12))

    assert ambiguous.status is BlindRecoveryStatus.ABSTAINED
    assert ambiguous.reason == "ambiguous_success"
    assert high_cost.status is BlindRecoveryStatus.ABSTAINED
    assert high_cost.reason == "rs_cost_gate"


def test_blind_recovery_vote_validates_invalid_policy_inputs() -> None:
    """Reject malformed votes and policy thresholds at the application boundary."""

    with pytest.raises(ValueError, match="accepted votes must name"):
        BlindRecoveryVote(True, 1, rs_error_cost=4)
    with pytest.raises(ValueError, match="attempted_hypotheses"):
        BlindRecoveryVote(False, -1)
    with pytest.raises(ValueError, match="maximum_hypotheses"):
        BlindRecoveryDecisionPolicy(maximum_hypotheses=0)
