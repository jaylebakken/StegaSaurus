"""Regression checks for iteration 010's constant-codeword allocation experiment.

The test exercises the baseline eight-byte token and compact six-byte registry
handle on one fresh cover. It ensures their protected lengths and framed audio
transport remain identical while both blind extraction paths emit measurement
records and reject the exact known handle under their negative controls.
"""

from stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_010_constant_codeword_allocation.run import (
    _allocations,
    evaluate_trial,
)


def test_constant_codeword_allocations_preserve_transport_demand() -> None:
    """Measure two fixed-length allocations with equal carrier demand and exact-handle controls."""

    baseline, _, compact = _allocations()
    baseline_trial = evaluate_trial(baseline, 0)
    compact_trial = evaluate_trial(compact, 0)

    assert baseline_trial.error is None
    assert compact_trial.error is None
    assert baseline_trial.measurement is not None
    assert compact_trial.measurement is not None
    assert baseline_trial.protected_codeword_bytes == compact_trial.protected_codeword_bytes == 20
    assert baseline_trial.carrier_bit_count == compact_trial.carrier_bit_count == 184
    assert baseline_trial.physical_carrier_count == compact_trial.physical_carrier_count == 736
    assert baseline_trial.unwatermarked_control_handle_match is False
    assert compact_trial.wrong_secret_control_handle_match is False
