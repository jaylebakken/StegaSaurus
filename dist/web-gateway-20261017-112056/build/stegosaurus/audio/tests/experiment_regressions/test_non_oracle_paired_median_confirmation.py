"""Regression checks for iteration 018's paired center-only versus median confirmation.

The test applies both predeclared strategies to the same fresh leading and
trailing crop inputs. It ensures every record remains map-blind, both strategy
names appear for each crop direction, and negative controls remain exact known
handle non-matches.
"""

from stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_018_paired_median_confirmation.run import (
    _crop_attacks,
    evaluate_variant,
)


def test_paired_median_confirmation_records_both_fixed_strategies() -> None:
    """Evaluate center-only and fixed median strategies for one fresh leading/trailing crop pair."""

    records = evaluate_variant(0, _crop_attacks())

    assert len(records) == 4
    assert all(record.error is None for record in records)
    assert all(record.decoder_received_oracle_map is False for record in records)
    assert {record.strategy_name for record in records} == {"center_only", "median_neighborhood_5"}
    assert all(record.unwatermarked_control_handle_match is False for record in records)
