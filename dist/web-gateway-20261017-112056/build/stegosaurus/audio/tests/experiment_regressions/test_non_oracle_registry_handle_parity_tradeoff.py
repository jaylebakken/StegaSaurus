"""Regression checks for iteration 019's fixed-codeword registry-handle parity comparison.

The test evaluates both protected allocations on one fresh leading/trailing
crop pair. It verifies that both preserve the 20-byte codeword and identical
carrier plan size, use blind deterministic center alignment, and retain exact
known-handle negative controls.
"""

from stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_019_registry_handle_parity_tradeoff.run import (
    _crop_attacks,
    _handle_allocations,
    evaluate_variant,
)


def test_registry_handle_parity_tradeoff_preserves_transport_demand() -> None:
    """Measure baseline and compact registry allocations with equal codeword length and carrier demand."""

    records = evaluate_variant(0, _crop_attacks())
    allocations = _handle_allocations()

    assert len(records) == 4
    assert all(record.error is None for record in records)
    assert {record.allocation_name for record in records} == {allocation.name for allocation in allocations}
    assert all(record.protected_codeword_bytes == 20 for record in records)
    assert all(record.carrier_bit_count == 184 for record in records)
    assert all(record.unwatermarked_control_handle_match is False for record in records)
