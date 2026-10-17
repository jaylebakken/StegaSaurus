"""Regression checks for contrastive local-pilot non-oracle calibration.

The test verifies one seeded clean cover can complete contrastive candidate
probing, pilot-only map selection, payload extraction, and the two exact-token
negative controls without giving the decoder the encoder-selected frame map.
"""

from stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_002_local_selection_pilot.run import (
    _profiles,
)
from stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_005_contrastive_pilot_calibration.run import (
    evaluate_trial,
)


def test_contrastive_calibration_reconstructs_clean_candidates_without_an_oracle_map() -> None:
    """Complete contrastive pilot selection on one clean cover and reject exact-token controls."""

    trial = evaluate_trial(_profiles()[0], 0)

    assert trial.error is None
    assert trial.map_metrics is not None
    assert trial.measurement is not None
    assert int(trial.map_metrics["physical_carrier_positions"]) > 0
    assert 0.0 <= float(trial.map_metrics["oracle_candidate_coverage"]) <= 1.0
    assert 0.0 <= float(trial.map_metrics["selection_erasure_rate"]) <= 1.0
    assert trial.unwatermarked_control_token_match is False
    assert trial.wrong_secret_control_token_match is False
