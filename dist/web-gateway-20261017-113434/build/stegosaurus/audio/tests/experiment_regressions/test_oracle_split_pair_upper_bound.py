"""Regression checks for the retained-map split-pair payload upper bound.

The test confirms a clean joint-calibrated split-pair embedding can be decoded
through its exact stored carrier map. It intentionally tests the oracle upper
bound, not non-oracle candidate-map reconstruction.
"""

from stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_002_local_selection_pilot.run import (
    _profiles,
)
from stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_004_oracle_split_pair_upper_bound.run import (
    evaluate_trial,
)


def test_oracle_split_pair_upper_bound_produces_channel_measurement() -> None:
    """Recover one clean split-pair cover through its retained encoder frame map."""

    trial = evaluate_trial(_profiles()[0], 0)

    assert trial.error is None
    assert trial.measurement is not None
    assert trial.embedding_snr_db is not None
    assert int(trial.measurement["rs_error_cost"]) >= 0
