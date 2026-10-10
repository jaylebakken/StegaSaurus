"""Regression checks for iteration 015's held-out deterministic center-phase decoder.

The test applies both unchanged crop directions to one fresh cover. It ensures
the decoder records a blind coarse decision and a deterministic residual center
without importing telemetry ranks or post-hoc labels, while retaining exact
known-handle negative controls.
"""

from stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_015_center_phase_held_out_validation.run import (
    _crop_attacks,
    evaluate_variant,
)


def test_center_phase_validation_uses_blind_deterministic_residuals() -> None:
    """Evaluate both fixed crops on one fresh cover without residual phase ranking or oracle map inputs."""

    records = evaluate_variant(0, _crop_attacks())

    assert len(records) == 2
    assert all(record.error is None for record in records)
    assert all(record.decoder_received_oracle_map is False for record in records)
    assert all(record.residual_phase_selection == "deterministic_model_center" for record in records)
    assert all(record.unwatermarked_control_handle_match is False for record in records)
