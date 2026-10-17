"""Classify repeated-block attribution with a block-vote waterfall.

This decision layer sits over retained repeated-block carrier evidence. It does
not solve arbitrary unknown-handle discovery or capacity selection. It names
the concrete stages exercised by the application and experiments:

    block verification -> fast block vote -> pooled carrier evidence -> abstain

The policy accepts independent block votes when enough blocks recover, accepts
pooled evidence when individual votes are weak, rejects on control acceptance,
and otherwise preserves uncertainty as an abstention.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum

from .blocks import BlockAttributionVerification


class RepeatedBlockWaterfallStage(str, Enum):
    """Name the repeated-block stage that made or blocked a decision."""

    FAST_BLOCK_VOTE = "fast_block_vote"
    CROSS_BLOCK_POOL = "cross_block_pool"
    CONTROL_REJECTION = "control_rejection"
    ABSTAINED = "abstained"


@dataclass(frozen=True, slots=True)
class RepeatedBlockWaterfallDecision:
    """Expose the repeated-block waterfall decision and diagnostics."""

    accepted: bool
    stage: RepeatedBlockWaterfallStage
    reason: str
    block_votes: int
    block_count: int
    pooled_rs_cost: int
    control_acceptances: int


@dataclass(frozen=True, slots=True)
class RepeatedBlockWaterfallPolicy:
    """Apply fast block-vote then pooled-evidence gates to repeated blocks."""

    fast_vote_threshold: int = 2
    maximum_pooled_rs_cost: int = 16

    def __post_init__(self) -> None:
        """Validate policy thresholds before any attribution decisions are made."""

        if self.fast_vote_threshold < 1:
            raise ValueError("fast_vote_threshold must be positive")
        if self.maximum_pooled_rs_cost < 0:
            raise ValueError("maximum_pooled_rs_cost must be non-negative")

    def decide(
        self,
        verification: BlockAttributionVerification,
        controls: Iterable[BlockAttributionVerification] = (),
    ) -> RepeatedBlockWaterfallDecision:
        """Classify one repeated-block claim using optional negative controls."""

        control_results = tuple(controls)
        control_acceptances = sum(control.recovered for control in control_results)
        if control_acceptances:
            return self._decision(
                False,
                RepeatedBlockWaterfallStage.CONTROL_REJECTION,
                "negative_control_accepted",
                verification,
                control_acceptances,
            )
        if verification.recovered_block_count >= self.fast_vote_threshold:
            return self._decision(
                True,
                RepeatedBlockWaterfallStage.FAST_BLOCK_VOTE,
                "independent_block_votes_met_threshold",
                verification,
                0,
            )
        if verification.recovered and verification.pooled_verification.claim_rs_cost <= self.maximum_pooled_rs_cost:
            return self._decision(
                True,
                RepeatedBlockWaterfallStage.CROSS_BLOCK_POOL,
                "pooled_carrier_evidence_within_rs_budget",
                verification,
                0,
            )
        return self._decision(False, RepeatedBlockWaterfallStage.ABSTAINED, "no_waterfall_stage_accepted", verification, 0)

    @staticmethod
    def _decision(
        accepted: bool,
        stage: RepeatedBlockWaterfallStage,
        reason: str,
        verification: BlockAttributionVerification,
        control_acceptances: int,
    ) -> RepeatedBlockWaterfallDecision:
        """Build one immutable waterfall decision from a block verification."""

        return RepeatedBlockWaterfallDecision(
            accepted,
            stage,
            reason,
            verification.recovered_block_count,
            len(verification.block_verifications),
            verification.pooled_verification.claim_rs_cost,
            control_acceptances,
        )
