"""Regression checks for clean non-oracle candidate-map reconstruction.

The test exercises one seeded clean cover through calibration, blind candidate
regeneration, sync-guided and replica-consensus selection, and two negative
controls. It guards the experiment's no-oracle decoder contract while avoiding
claims about broad reconstruction rates from a single fixture.
"""

from stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_001_clean_candidate_map.run import (
    evaluate_trial,
)


def test_clean_candidate_map_reconstruction_uses_no_encoder_map() -> None:
    """Reconstruct a complete clean candidate map and reject both exact-token controls."""

    trial = evaluate_trial(0)

    assert trial.error is None
    assert not trial.decoder_received_oracle_map
    assert trial.map_metrics is not None
    assert trial.measurement is not None
    assert int(trial.map_metrics["physical_carrier_positions"]) > 0
    assert 0.0 <= float(trial.map_metrics["oracle_candidate_coverage"]) <= 1.0
    assert 0.0 <= float(trial.map_metrics["selected_map_accuracy"]) <= 1.0
    assert trial.unwatermarked_control_token_match is False
    assert trial.wrong_secret_control_token_match is False
