"""Regression-test sync-only oracle-map offset recovery after a leading crop.

The test protects the current bounded synchronization capability: a 250 ms
leading crop of a calibrated 30-second cover must be aligned from framing sync
bits alone before full token extraction. It does not claim blind synchronization.
"""

from stegosaurus.audio.experiments.transport_optimization.iteration_011_oracle_map_offset_sync.run import (
    evaluate_trial,
)


def test_sync_only_offset_scan_recovers_a_token_after_a_250ms_leading_crop() -> None:
    """Recover the known token after a non-hop leading crop with no protected-data alignment aid."""

    result = evaluate_trial(0)

    assert result.error is None
    assert result.selected_offset_frames is not None
    assert result.selected_offset_frames > 0
    assert result.selected_sample_offset is not None
    assert result.selected_sample_offset > 0
    assert result.measurement is not None
    assert result.measurement["token_matches_input"] is True
