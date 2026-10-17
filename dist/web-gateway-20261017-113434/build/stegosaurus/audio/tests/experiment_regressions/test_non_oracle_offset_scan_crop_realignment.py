"""Regression checks for the bounded blind offset scan used in iteration 012.

The test embeds one disjoint cover, applies the existing leading and trailing
crop transformations, and verifies that the keyed scan records a bounded
offset decision before blind local-pilot reconstruction. It does not assert
successful crop recovery because that result is the experiment's measured
outcome rather than a fixture assumption.
"""

from stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_012_offset_scan_crop_realignment.run import (
    _crop_attacks,
    evaluate_variant,
)


def test_offset_scan_records_bounded_blind_crop_decisions() -> None:
    """Measure both retained crop attacks with a secret-derived scan and no encoder frame map."""

    records = evaluate_variant(0, _crop_attacks())

    assert len(records) == 2
    assert all(record.error is None for record in records)
    assert all(record.decoder_received_oracle_map is False for record in records)
    assert all(record.scan_searched_offset_count == 65 for record in records)
    assert all(record.measurement is not None for record in records)
    assert all(record.unwatermarked_control_handle_match is False for record in records)
