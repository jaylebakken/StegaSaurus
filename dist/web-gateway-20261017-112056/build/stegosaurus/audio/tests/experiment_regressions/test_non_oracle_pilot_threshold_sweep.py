"""Regression checks for the non-oracle local-pilot decoder threshold sweep.

The test exercises one calibrated clean cover through baseline and stricter
threshold pairs, ensuring every decoder path uses no encoder frame map and
reports the expected measurement and control fields.
"""

from stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_006_pilot_threshold_sweep.run import (
    PilotThresholds,
    evaluate_variant,
)


def test_pilot_threshold_sweep_reports_clean_non_oracle_measurements() -> None:
    """Decode one clean cover under two threshold pairs and reject exact-token controls."""

    trials = evaluate_variant(0, (PilotThresholds(0.01, 0.01), PilotThresholds(0.04, 0.04)))

    assert len(trials) == 2
    for trial in trials:
        assert trial.error is None
        assert trial.map_metrics is not None
        assert trial.measurement is not None
        assert int(trial.map_metrics["physical_carrier_positions"]) > 0
        assert 0.0 <= float(trial.map_metrics["selection_erasure_rate"]) <= 1.0
        assert trial.unwatermarked_control_token_match is False
        assert trial.wrong_secret_control_token_match is False
