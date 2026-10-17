"""Regression checks for iteration 016's center-neighborhood soft combiner.

The test decodes one fresh cover under both fixed strategies for each crop
direction. It verifies that neither strategy receives an oracle map, that the
neighborhood is fixed around the deterministic center rather than pilot rank,
and that median-combined control decodes do not exactly return the known handle.
"""

from stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_016_center_neighborhood_soft_combine.run import (
    _crop_attacks,
    evaluate_variant,
)


def test_center_neighborhood_combiner_records_blind_strategy_measurements() -> None:
    """Evaluate center-only and fixed-neighborhood median strategies on one fresh leading/trailing crop pair."""

    records = evaluate_variant(0, _crop_attacks())

    assert len(records) == 4
    assert all(record.error is None for record in records)
    assert all(record.decoder_received_oracle_map is False for record in records)
    assert {record.strategy_name for record in records} == {"center_only", "median_neighborhood_5"}
    assert all(record.unwatermarked_control_handle_match is False for record in records)
