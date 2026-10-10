"""Define the production-facing decision policy for blind attribution recovery.

The blind-recovery experiments currently produce decoder votes from declared
pipeline hypotheses such as "received duration" or "one 250 ms edge loss." This
module does not reconstruct audio carriers and does not discover unknown
handles. It converts those votes into a conservative production decision:

    watermarked vote + control votes -> accept | reject | abstain

The policy is intentionally small. It accepts only a unique, low-burden
watermarked success while independent controls abstain. It rejects when controls
accept, and otherwise abstains after bounded search exhaustion. That lets a
future blind decoder expose uncertainty without widening search until it finds
an accidental payload.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import Enum


class BlindRecoveryStatus(str, Enum):
    """Classify a blind-recovery verifier outcome without hiding uncertainty."""

    ACCEPTED = "accepted"
    REJECTED = "rejected"
    ABSTAINED = "abstained"


@dataclass(frozen=True, slots=True)
class BlindRecoveryVote:
    """Represent one staged decoder vote before production policy is applied."""

    accepted: bool
    attempted_hypotheses: int
    stage_name: str | None = None
    rs_error_cost: int | None = None
    ambiguous_successes: int = 0
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        """Validate one staged decoder vote before it reaches policy ranking."""

        if self.attempted_hypotheses < 0:
            raise ValueError("attempted_hypotheses must be non-negative")
        if self.rs_error_cost is not None and self.rs_error_cost < 0:
            raise ValueError("rs_error_cost must be non-negative when supplied")
        if self.ambiguous_successes < 0:
            raise ValueError("ambiguous_successes must be non-negative")
        if self.accepted and self.stage_name is None:
            raise ValueError("accepted votes must name the selected stage")


@dataclass(frozen=True, slots=True)
class BlindRecoveryDecision:
    """Expose the final production-facing blind-recovery outcome and reason."""

    status: BlindRecoveryStatus
    reason: str
    selected_stage: str | None
    attempted_hypotheses: int
    rs_error_cost: int | None

    @property
    def accepted(self) -> bool:
        """Return whether policy accepted the claimed-plan blind recovery."""

        return self.status is BlindRecoveryStatus.ACCEPTED


@dataclass(frozen=True, slots=True)
class BlindRecoveryDecisionPolicy:
    """Apply bounded staged-recovery gates to one watermarked vote and controls."""

    maximum_rs_error_cost: int = 8
    maximum_hypotheses: int = 5

    def __post_init__(self) -> None:
        """Validate production gates before they are used for attribution decisions."""

        if self.maximum_rs_error_cost < 0:
            raise ValueError("maximum_rs_error_cost must be non-negative")
        if self.maximum_hypotheses < 1:
            raise ValueError("maximum_hypotheses must be positive")

    def decide(
        self,
        watermarked: BlindRecoveryVote,
        controls: Iterable[BlindRecoveryVote] = (),
    ) -> BlindRecoveryDecision:
        """Return accept, reject, or abstain for one claimed-plan recovery attempt."""

        control_votes = tuple(controls)
        attempted = max(
            (watermarked.attempted_hypotheses, *(vote.attempted_hypotheses for vote in control_votes))
        )
        if any(vote.accepted for vote in control_votes):
            return BlindRecoveryDecision(
                BlindRecoveryStatus.REJECTED,
                "control_acceptance",
                None,
                attempted,
                None,
            )
        if watermarked.accepted:
            return self._accepted_or_abstained(watermarked, attempted)
        reason = "bounded_search_exhausted" if attempted >= self.maximum_hypotheses else watermarked.rejection_reason
        return BlindRecoveryDecision(
            BlindRecoveryStatus.ABSTAINED,
            reason or "no_unique_success",
            None,
            attempted,
            None,
        )

    def _accepted_or_abstained(self, vote: BlindRecoveryVote, attempted: int) -> BlindRecoveryDecision:
        """Apply acceptance gates to a selected watermarked vote."""

        if vote.ambiguous_successes > 0:
            return BlindRecoveryDecision(
                BlindRecoveryStatus.ABSTAINED,
                "ambiguous_success",
                None,
                attempted,
                vote.rs_error_cost,
            )
        if vote.rs_error_cost is None:
            return BlindRecoveryDecision(BlindRecoveryStatus.ABSTAINED, "missing_rs_cost", None, attempted, None)
        if vote.rs_error_cost > self.maximum_rs_error_cost:
            return BlindRecoveryDecision(
                BlindRecoveryStatus.ABSTAINED,
                "rs_cost_gate",
                vote.stage_name,
                attempted,
                vote.rs_error_cost,
            )
        return BlindRecoveryDecision(
            BlindRecoveryStatus.ACCEPTED,
            "unique_low_burden_success",
            vote.stage_name,
            attempted,
            vote.rs_error_cost,
        )
