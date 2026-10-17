"""Test selection rules for the archived duration and parity budget experiment.

These tests check that iteration 005 prefers exact token recovery and, among
successful candidates, chooses the smallest physical carrier plan. Full sweep
measurements remain in the experiment archive rather than regression tests.
"""

from stegosaurus.audio.experiments.transport_optimization.iteration_005_duration_parity_budget.run import (
    CandidateResult,
    _optimal_candidate,
)


def _candidate(
    duration_seconds: int,
    parity_symbols: int,
    physical_carrier_frames: int,
    verified: bool,
) -> CandidateResult:
    """Build a compact candidate fixture with an optional exact-token recovery threshold."""

    return CandidateResult(
        duration_seconds,
        parity_symbols,
        500,
        physical_carrier_frames // 4,
        physical_carrier_frames,
        50.0,
        0.05,
        {"token_matches_input": verified, "rs_error_cost": 0, "unknown_byte_errors": 0, "byte_erasures": 0},
        (0.05,) if verified else (),
    )


def test_optimal_candidate_prefers_smallest_verified_physical_plan() -> None:
    """Choose successful recovery over failure and minimize the selected carrier-frame plan."""

    failed = _candidate(30, 8, 576, False)
    larger_verified = _candidate(30, 16, 832, True)
    smaller_verified = _candidate(45, 12, 704, True)

    assert _optimal_candidate((failed, larger_verified, smaller_verified)) == smaller_verified


def test_optimal_candidate_prefers_shorter_duration_when_verified_plans_match() -> None:
    """Prefer the shorter cover when two verified candidates use the same carrier plan."""

    longer = _candidate(60, 12, 736, True)
    shorter = _candidate(30, 12, 736, True)

    assert _optimal_candidate((longer, shorter)) == shorter


def test_optimal_candidate_returns_none_when_no_configuration_verifies() -> None:
    """Report no optimum rather than mistaking a non-null decoder output for recovery."""

    assert _optimal_candidate((_candidate(30, 8, 576, False),)) is None
