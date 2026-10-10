"""Regression checks for iteration 017's fixed-median fresh-cover validation.

The test processes both unchanged crop directions on one new cover using only
the predeclared five-phase median strategy. It verifies that the decoder stays
blind to encoder maps and produces exact-handle negative-control outcomes
without selecting a phase by telemetry or payload result.
"""

from stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_017_fixed_median_held_out_validation.run import (
    _crop_attacks,
    evaluate_variant,
)


def test_fixed_median_validation_uses_predeclared_blind_strategy() -> None:
    """Evaluate both crop directions on one fresh cover with the fixed five-phase median combiner."""

    records = evaluate_variant(0, _crop_attacks())

    assert len(records) == 2
    assert all(record.error is None for record in records)
    assert all(record.decoder_received_oracle_map is False for record in records)
    assert all(record.strategy_name == "median_neighborhood_5" for record in records)
    assert all(record.unwatermarked_control_handle_match is False for record in records)
