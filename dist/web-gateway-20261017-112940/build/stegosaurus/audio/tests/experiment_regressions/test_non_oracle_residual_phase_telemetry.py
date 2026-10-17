"""Regression checks for iteration 014's per-phase crop telemetry collection.

The test evaluates one leading and one trailing crop, verifies that telemetry
is gathered without an encoder map, and confirms that at least one phase row
is preserved for each crop/control stream when its coarse scan is accepted.
It intentionally makes no phase-recovery assertion because the experiment is
collecting data for a future independent acceptance-policy calibration.
"""

from stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_014_residual_phase_telemetry.run import (
    _crop_attacks,
    evaluate_variant,
)


def test_residual_phase_telemetry_records_blind_candidate_measurements() -> None:
    """Record per-phase payload evidence for both retained crop transformations and their controls."""

    trials, telemetry = evaluate_variant(1, _crop_attacks())

    assert len(trials) == 2
    assert all(trial.error is None for trial in trials)
    assert all(trial.decoder_received_oracle_map is False for trial in trials)
    assert any(row.stream == "watermarked" for row in telemetry)
    assert all(row.phase_candidate_count == 9 for row in telemetry)
