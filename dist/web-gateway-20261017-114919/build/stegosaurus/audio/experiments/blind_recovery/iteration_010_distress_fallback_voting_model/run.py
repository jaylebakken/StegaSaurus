"""Run iteration 010: model distress-driven fallback and block voting.

Goal: turn the block schema idea into a maximum-cost recovery controller. A
verifier should escalate from cheap block recovery to expensive crop search only
when distress evidence justifies the cost, then vote across recovered blocks.

Toy flow:
    block outcomes -> received-only stage -> single-edge stage -> vote result

The numbers are seeded planning assumptions from measured local timings:
received-only recovery is roughly 2.2 seconds per block; the 500 ms single-edge
grid is roughly 9.0 seconds when needed. This model does not run audio recovery.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json


@dataclass(frozen=True, slots=True)
class FallbackScenario:
    """Describe one song/block recovery stress pattern."""

    name: str
    block_count: int
    clean_recoveries: int
    distressed_recoveries: int
    unrecoverable_blocks: int
    voting_threshold: int


@dataclass(frozen=True, slots=True)
class FallbackResult:
    """Record cost and vote result for one fallback scenario."""

    scenario_name: str
    accepted: bool
    recovered_blocks: int
    received_only_attempts: int
    fallback_attempts: int
    estimated_seconds: float
    reason: str


def _scenarios() -> tuple[FallbackScenario, ...]:
    """Return compact fallback scenarios for 2.5-minute and 5-minute songs."""

    return (
        FallbackScenario("2_5min_many_clean_any_block", 5, 3, 1, 1, 1),
        FallbackScenario("2_5min_distressed_two_vote", 5, 1, 2, 2, 2),
        FallbackScenario("5min_sparse_clean_any_block", 10, 1, 2, 7, 1),
        FallbackScenario("5min_distressed_two_vote", 10, 1, 3, 6, 2),
    )


def _evaluate(scenario: FallbackScenario) -> FallbackResult:
    """Evaluate a maximum-cost waterfall model for one scenario."""

    received_only_attempts = scenario.block_count
    remaining_after_clean = scenario.block_count - scenario.clean_recoveries
    recovered = scenario.clean_recoveries
    fallback_attempts = 0
    if recovered < scenario.voting_threshold:
        fallback_attempts = remaining_after_clean
        recovered += scenario.distressed_recoveries
    accepted = recovered >= scenario.voting_threshold
    estimated_seconds = received_only_attempts * 2.2 + fallback_attempts * (9.0 - 2.2)
    reason = "threshold_met" if accepted else "insufficient_recovered_blocks"
    return FallbackResult(scenario.name, accepted, recovered, received_only_attempts, fallback_attempts, estimated_seconds, reason)


def run() -> dict[str, object]:
    """Run the distress fallback and block-voting planning model."""

    scenarios = _scenarios()
    results = tuple(_evaluate(scenario) for scenario in scenarios)
    return {
        "goal": "model maximum-cost distress fallback and block voting",
        "timing_assumptions_seconds": {
            "received_only_per_block": 2.2,
            "single_edge_grid_per_block": 9.0,
        },
        "scenarios": [asdict(scenario) for scenario in scenarios],
        "recommendation": "run received-only across candidate blocks first, then spend single-edge fallback only until the voting threshold is met",
        "results": [asdict(result) for result in results],
    }


def main() -> None:
    """Print the distress fallback planning model."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
