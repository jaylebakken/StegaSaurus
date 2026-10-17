"""Regression checks for offline non-oracle pilot-score telemetry collection.

The test verifies that one clean contrastive cover produces linked physical,
logical, and codeword-byte tables. Oracle labels are checked only as recorded
post-hoc fields and are not supplied to the blind candidate reconstruction.
"""

from stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_007_pilot_score_telemetry.run import (
    evaluate_trial,
)


def test_pilot_score_telemetry_records_all_three_channel_layers() -> None:
    """Collect one blind decode's physical, logical, and RS-byte diagnostic rows."""

    trial = evaluate_trial(0)

    assert trial.error is None
    assert trial.aggregate is not None
    assert trial.physical_carriers
    assert trial.logical_carriers
    assert trial.codeword_bytes
    assert "pilot_gap" in trial.physical_carriers[0]
    assert "oracle_map_correct" in trial.physical_carriers[0]
    assert "logical_payload_correct" in trial.logical_carriers[0]
    assert "rs_cost_contribution" in trial.codeword_bytes[0]
