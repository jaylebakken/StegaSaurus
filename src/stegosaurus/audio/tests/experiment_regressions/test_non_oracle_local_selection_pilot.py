"""Regression checks for local-pilot non-oracle candidate-map reconstruction.

The test verifies that one small-pilot clean cover can be calibrated, decoded
without an oracle frame map, and evaluated against unwatermarked and wrong-key
exact-token controls. It does not assert a benchmark recovery rate.
"""

from stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_002_local_selection_pilot.run import (
    _profiles,
    evaluate_trial,
)


def test_local_selection_pilot_reconstructs_without_an_oracle_map() -> None:
    """Select clean carrier frames from local pilots and reject both exact-token controls."""

    trial = evaluate_trial(_profiles()[0], 0)

    assert trial.error is None
    assert trial.map_metrics is not None
    assert trial.measurement is not None
    assert int(trial.map_metrics["physical_carrier_positions"]) > 0
    assert 0.0 <= float(trial.map_metrics["oracle_candidate_coverage"]) <= 1.0
    assert 0.0 <= float(trial.map_metrics["selection_erasure_rate"]) <= 1.0
    assert trial.unwatermarked_control_token_match is False
    assert trial.wrong_secret_control_token_match is False
