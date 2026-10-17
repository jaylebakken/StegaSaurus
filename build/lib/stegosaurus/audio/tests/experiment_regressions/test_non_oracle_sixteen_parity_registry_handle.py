"""Regression checks for iteration 020's sixteen-parity registry-handle experiment.

The test evaluates the fourteen-parity baseline and four-byte/sixteen-parity
registry allocation on one fresh leading/trailing crop pair. It verifies that
the new allocation preserves the protected-codeword and carrier demand while
raising the error-only Reed--Solomon correction radius by one byte symbol.
"""

from stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_020_sixteen_parity_registry_handle.run import (
    _crop_attacks,
    _handle_allocations,
    evaluate_variant,
)


def test_sixteen_parity_registry_handle_preserves_transport_demand() -> None:
    """Measure equal-capacity allocations and verify the sixteen-parity codeword's larger error-only radius."""

    records = evaluate_variant(0, _crop_attacks())
    allocations = _handle_allocations()

    assert len(records) == 4
    assert all(record.error is None for record in records)
    assert {record.allocation_name for record in records} == {allocation.name for allocation in allocations}
    assert all(record.protected_codeword_bytes == 20 for record in records)
    assert all(record.carrier_bit_count == 184 for record in records)
    assert all(record.unwatermarked_control_handle_match is False for record in records)
    assert [allocation.parity_symbols // 2 for allocation in allocations] == [7, 8]
