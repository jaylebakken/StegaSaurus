"""Run iteration 016: model the optimized V3 blind-recovery waterfall.

Goal: convert the recent block experiments into a controller policy for full
blind recovery. Iterations 014 and 015 show that high-pilot block failures are
better handled by cross-block pooling than by geometry search, while geometry
fallback remains useful when localization or timing is suspect.

Toy flow:
    window ranking -> block votes -> pooled evidence -> distress classifier
        -> geometry fallback only for localization/timing distress

The model uses measured outcomes from the current synthetic fixture. It is a
release-planning artifact and does not claim broad robustness by itself.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json


@dataclass(frozen=True, slots=True)
class RecoveryObservation:
    """Describe the measured evidence available after ranked block recovery."""

    name: str
    top_windows: int
    exact_starts: int
    block_votes: int
    required_votes: int
    pooled_recovered: bool
    pooled_rs_cost: int
    geometry_attempts: int
    geometry_recoveries: int


@dataclass(frozen=True, slots=True)
class WaterfallStage:
    """Describe one ordered V3 recovery stage and its stop condition."""

    order: int
    name: str
    purpose: str
    enter_when: str
    stop_when: str
    v3_release_status: str


@dataclass(frozen=True, slots=True)
class PolicyDecision:
    """Record the optimized route for one measured observation."""

    observation_name: str
    accepted_stage: str
    final_status: str
    geometry_fallback_recommended: bool
    reason: str


def _observations() -> tuple[RecoveryObservation, ...]:
    """Return compact measured cases from iterations 014 and 015."""

    return (
        RecoveryObservation("top3_fast_vote", 3, 3, 2, 2, True, 2, 0, 0),
        RecoveryObservation("top5_balanced_vote", 5, 5, 3, 3, True, 0, 0, 0),
        RecoveryObservation("top7_wide_pool", 7, 5, 3, 3, True, 1, 0, 0),
        RecoveryObservation("strict_geometry_spend", 5, 5, 3, 4, False, 99, 2, 0),
        RecoveryObservation("zero_vote_pool_recovery", 5, 5, 0, 2, True, 6, 0, 0),
        RecoveryObservation("hypothetical_low_localization", 7, 3, 0, 2, False, 99, 0, 0),
    )


def _stages() -> tuple[WaterfallStage, ...]:
    """Return the proposed V3 controller stages in cost order."""

    return (
        WaterfallStage(
            1,
            "pilot_window_prefilter",
            "rank likely block windows before expensive recovery",
            "always",
            "top candidate windows are scored and retained",
            "promote",
        ),
        WaterfallStage(
            2,
            "fast_block_vote",
            "accept independent recovered blocks when enough agree",
            "top three windows available",
            "two recovered block votes, or continue to pooling",
            "promote",
        ),
        WaterfallStage(
            3,
            "cross_block_pool",
            "combine carrier evidence across repeated blocks before RS recovery",
            "localized/high-pilot windows exist but block votes are weak or stricter assurance is requested",
            "pooled recovery within RS budget, or classify remaining distress",
            "promote after broader controls",
        ),
        WaterfallStage(
            4,
            "geometry_fallback",
            "search received-duration and bounded crop hypotheses",
            "few exact-looking windows, low pilot localization, or timing/crop symptoms",
            "unique low-burden recovery, otherwise abstain",
            "experimental",
        ),
        WaterfallStage(
            5,
            "max_cost_search",
            "bounded offline expansion for support tooling and evidence capture",
            "operator requests offline recovery and earlier stages abstain",
            "unique accepted claim or explicit abstention with diagnostics",
            "V3-later",
        ),
    )


def _decide(observation: RecoveryObservation) -> PolicyDecision:
    """Route one observation through the V3 waterfall."""

    if observation.block_votes >= observation.required_votes:
        return PolicyDecision(
            observation.name,
            "fast_block_vote",
            "accepted",
            False,
            "independent block votes satisfy the requested vote threshold",
        )
    if observation.pooled_recovered and observation.pooled_rs_cost <= 16:
        return PolicyDecision(
            observation.name,
            "cross_block_pool",
            "accepted",
            False,
            "localized repeated blocks pooled into a recoverable low-burden codeword",
        )
    if observation.exact_starts < max(1, observation.top_windows - 2):
        return PolicyDecision(
            observation.name,
            "geometry_fallback",
            "continue",
            True,
            "candidate windows are not reliably localizing block starts",
        )
    if observation.geometry_attempts and observation.geometry_recoveries == 0:
        return PolicyDecision(
            observation.name,
            "cross_block_pool",
            "abstained",
            False,
            "measured geometry spend did not rescue high-pilot block distress",
        )
    return PolicyDecision(
        observation.name,
        "geometry_fallback",
        "continue",
        True,
        "remaining failure lacks a low-burden pooled recovery and needs timing diagnostics",
    )


def run() -> dict[str, object]:
    """Return the V3 waterfall policy and decisions for measured cases."""

    observations = _observations()
    decisions = tuple(_decide(observation) for observation in observations)
    return {
        "goal": "optimize waterfall fallback order for V3 blind recovery planning",
        "policy": [asdict(stage) for stage in _stages()],
        "observations": [asdict(observation) for observation in observations],
        "decisions": [asdict(decision) for decision in decisions],
        "v3_release_plan": {
            "promote_now": [
                "repeated 30-second block schema",
                "pilot window prefilter",
                "two-vote fast block acceptance",
                "cross-block carrier evidence pooling",
            ],
            "keep_experimental": [
                "broad geometry fallback",
                "unknown arbitrary crop length recovery",
                "codec and recorded-audio claims",
            ],
            "next_validation": [
                "separately seeded block-pooling controls",
                "clean plus bounded crop fixtures",
                "negative controls for wrong secret and unwatermarked audio",
                "runtime budget across 2.5-minute and 5-minute songs",
            ],
        },
    }


def main() -> None:
    """Print the V3 waterfall policy model."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

