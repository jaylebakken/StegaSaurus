"""Regression checks for joint local-pilot and payload-margin calibration.

The test verifies one seeded clean cover can complete the joint encoder probe,
pilot-only map selection, payload decode, and two exact-token negative controls
without supplying the encoder's selected frame map to the decoder.
"""

from stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_002_local_selection_pilot.run import (
    _profiles,
)
from stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_003_joint_pilot_payload_calibration.run import (
    evaluate_trial,
)


def test_joint_calibration_reconstructs_clean_candidates_without_an_oracle_map() -> None:
    """Complete the clean joint-calibration path and reject both exact-token controls."""

    trial = evaluate_trial(_profiles()[0], 0)

    assert trial.error is None
    assert trial.map_metrics is not None
    assert trial.measurement is not None
    assert int(trial.map_metrics["physical_carrier_positions"]) > 0
    assert 0.0 <= float(trial.map_metrics["oracle_candidate_coverage"]) <= 1.0
    assert 0.0 <= float(trial.map_metrics["selection_erasure_rate"]) <= 1.0
    assert trial.unwatermarked_control_token_match is False
    assert trial.wrong_secret_control_token_match is False
