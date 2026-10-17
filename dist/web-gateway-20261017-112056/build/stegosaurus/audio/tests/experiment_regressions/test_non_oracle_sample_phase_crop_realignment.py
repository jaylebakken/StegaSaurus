"""Regression checks for iteration 013's coarse-to-fine sample-phase realignment.

The test processes one leading and one trailing crop with the bounded residual
phase scan. It verifies that the decoder uses no oracle frame map, records its
coarse and sample-domain scan decisions, and preserves exact-handle negative
controls without assuming that either crop must recover.
"""

from stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_013_sample_phase_crop_realignment.run import (
    _crop_attacks,
    evaluate_variant,
)


def test_sample_phase_scan_records_blind_crop_decisions() -> None:
    """Measure both fixed crop directions with coarse keyed synchronization and residual phase search."""

    records = evaluate_variant(0, _crop_attacks())

    assert len(records) == 2
    assert all(record.error is None for record in records)
    assert all(record.decoder_received_oracle_map is False for record in records)
    assert all(record.residual_phase_candidate_count in (0, 9) for record in records)
    assert all(record.measurement is not None for record in records)
    assert all(record.unwatermarked_control_handle_match is False for record in records)
