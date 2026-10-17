"""Regression checks for held-out non-oracle local-pilot gap-policy validation.

The test confirms the frozen policy runs blindly on a fresh cover seed, records
post-hoc map metrics only after reconstruction, and rejects exact known-token
matches from both unwatermarked and wrong-secret controls.
"""

from stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_008_held_out_gap_validation.run import (
    _threshold_policy,
    evaluate_trial,
)


def test_held_out_gap_policy_runs_blindly_on_a_fresh_cover() -> None:
    """Validate the frozen policy on one fresh cover and reject exact-token controls."""

    trial = evaluate_trial(0)

    assert _threshold_policy().absolute_pilot_threshold == 0.0
    assert _threshold_policy().pilot_gap_threshold == 0.24
    assert trial.cover_seed == 6300
    assert trial.error is None
    assert trial.map_metrics is not None
    assert trial.measurement is not None
    assert int(trial.map_metrics["physical_carrier_positions"]) > 0
    assert trial.unwatermarked_control_token_match is False
    assert trial.wrong_secret_control_token_match is False
