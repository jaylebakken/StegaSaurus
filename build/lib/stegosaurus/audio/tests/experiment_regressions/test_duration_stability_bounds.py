"""Test aggregation rules for the archived iteration-six stability experiment.

The tests cover exact-token recovery accounting and the all-trials reliability
criterion. They avoid running the full multi-duration signal experiment during
normal regression testing.
"""

from stegosaurus.audio.experiments.transport_optimization.iteration_006_duration_stability_bounds.run import (
    TrialRecord,
    _aggregate_threshold,
)


def _trial(token_matches_input: bool, capacity_error: str | None = None) -> TrialRecord:
    """Build a compact deterministic threshold observation for aggregation testing."""

    measurements = (
        {}
        if capacity_error
        else {
            "0.030": {
                "token_matches_input": token_matches_input,
                "rs_error_cost": 7,
            }
        }
    )
    return TrialRecord(30, 0, 6100, 37.0, 1876, 50.0 if not capacity_error else None, capacity_error, measurements)


def test_aggregate_threshold_requires_every_trial_for_reliability() -> None:
    """Mark a setting reliable only when every trial exactly recovers without capacity failure."""

    summary = _aggregate_threshold(30, 0.03, (_trial(True), _trial(True)))

    assert summary["exact_recovery_rate"] == 1.0
    assert summary["reliable"] is True


def test_aggregate_threshold_rejects_failed_or_unavailable_trials() -> None:
    """Treat mismatched tokens and capacity failures as evidence against a reliable setting."""

    summary = _aggregate_threshold(30, 0.03, (_trial(True), _trial(False), _trial(True, "capacity")))

    assert summary["exact_recoveries"] == 1
    assert summary["capacity_failures"] == 1
    assert summary["reliable"] is False
