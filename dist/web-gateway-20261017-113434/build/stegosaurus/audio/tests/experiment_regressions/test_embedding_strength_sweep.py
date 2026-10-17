"""Test selection rules for the archived embedding-strength sweep.

The tests ensure that recovery count dominates quality metrics when comparing
settings, without running the full multi-variant audio experiment.
"""

from stegosaurus.audio.experiments.transport_optimization.iteration_007_embedding_strength_sweep.run import (
    _best_record,
)


def _record(exact_recoveries: int, median_rs_cost: float, median_snr_db: float) -> dict[str, object]:
    """Build a compact strength record for selection testing."""

    return {
        "best_summary": {
            "exact_recoveries": exact_recoveries,
            "capacity_failures": 0,
            "median_rs_cost": median_rs_cost,
            "median_embedding_snr_db": median_snr_db,
        }
    }


def test_best_record_prefers_exact_recovery_count_over_higher_snr() -> None:
    """Select the setting with more verified tokens even when its SNR is lower."""

    weaker = _record(1, 8.0, 55.0)
    stronger = _record(2, 12.0, 42.0)

    assert _best_record((weaker, stronger)) == stronger


def test_best_record_returns_none_for_an_empty_sweep() -> None:
    """Represent an absent search result without inventing a best strength setting."""

    assert _best_record(()) is None
