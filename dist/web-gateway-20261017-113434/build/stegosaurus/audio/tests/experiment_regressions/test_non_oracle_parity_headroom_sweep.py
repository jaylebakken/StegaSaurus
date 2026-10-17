"""Regression checks for the held-out non-oracle Reed--Solomon parity sweep.

The test exercises the baseline and increased parity encoder plans on one fresh
cover, verifying that both preserve blind map reconstruction and produce
measurement records plus exact-token negative controls.
"""

from stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_009_parity_headroom_sweep.run import (
    evaluate_trial,
)


def test_parity_headroom_sweep_measures_baseline_and_extra_parity() -> None:
    """Blindly decode one fresh cover under 12 and 14 parity symbols with declared controls."""

    baseline = evaluate_trial(12, 0)
    increased = evaluate_trial(14, 0)

    assert baseline.error is None
    assert increased.error is None
    assert baseline.measurement is not None
    assert increased.measurement is not None
    assert baseline.carrier_bit_count is not None
    assert increased.carrier_bit_count is not None
    assert increased.carrier_bit_count > baseline.carrier_bit_count
    assert baseline.unwatermarked_control_token_match is False
    assert increased.wrong_secret_control_token_match is False
