"""Run iteration 014: compare block-vote thresholds and fallback handoffs.

Goal: optimize how repeated-block recovery should spend work. A controller can
rank candidate windows, decode the strongest few blocks cheaply, and then decide
whether the remaining distress is block evidence weakness or geometry mismatch.

Toy flow:
    rank top seven windows -> cheap recovery once -> evaluate top-K policies
        -> spend real fallback only on threshold-changing cases

This experiment uses the same claimed-plan synthetic song as iteration 013. It
does not implement cross-block soft pooling yet; it identifies where pooling
should replace geometry fallback.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from time import perf_counter

from ....pilot import PcmAudio
from ..iteration_004_staged_recovery_controller.run import _run_controller
from ..iteration_013_block_waterfall_controller.run import (
    WindowRecovery,
    _fallback_stages,
    _matches,
    _rank_windows,
    _song,
)
from ..iteration_012_window_prefilter_smoke.run import _stage, _window


@dataclass(frozen=True, slots=True)
class OptimizationPolicy:
    """Declare one top-K voting and fallback optimization case."""

    name: str
    top_window_count: int
    voting_threshold: int
    fallback_window_budget: int


@dataclass(frozen=True, slots=True)
class OptimizationResult:
    """Record one policy outcome over the shared cheap-recovery fixture."""

    policy_name: str
    top_window_count: int
    voting_threshold: int
    fallback_window_budget: int
    exact_starts: int
    cheap_recoveries: int
    cheap_failures_with_high_pilot: int
    fallback_attempts: int
    fallback_recoveries: int
    final_recoveries: int
    accepted: bool
    recommended_next_tool: str
    estimated_total_ms: float
    fallback_elapsed_ms: float


def _policies() -> tuple[OptimizationPolicy, ...]:
    """Return policies that expose top-K and threshold tradeoffs."""

    return (
        OptimizationPolicy("fast_any_top3", 3, 1, 0),
        OptimizationPolicy("fast_two_vote_top3", 3, 2, 0),
        OptimizationPolicy("strict_three_top3_with_fallback", 3, 3, 1),
        OptimizationPolicy("balanced_three_top5", 5, 3, 0),
        OptimizationPolicy("strict_four_top5_with_fallback", 5, 4, 2),
        OptimizationPolicy("wide_three_top7", 7, 3, 0),
    )


def _recover_top_windows(
    song: PcmAudio,
    encoder: object,
    embedding: object,
    handle: bytes,
    top_window_count: int,
) -> tuple[tuple[WindowRecovery, ...], float, float]:
    """Rank candidate windows and run cheap recovery on the strongest windows."""

    ranked, prefilter_elapsed_ms = _rank_windows(song, encoder, embedding, top_window_count)
    block_length = len(embedding.audio.samples)
    records: list[WindowRecovery] = []
    started = perf_counter()
    for score in ranked:
        start = int(round(score.start_seconds * song.sample_rate))
        vote = _run_controller(_window(song, start, block_length), encoder, embedding.carrier_plan, _stage(), (embedding, handle))
        records.append(WindowRecovery(score.start_seconds, score.pilot_score, score.is_exact_block_start, _matches(vote), False, False))
    return tuple(records), prefilter_elapsed_ms, (perf_counter() - started) * 1000.0


def _fallback(
    records: tuple[WindowRecovery, ...],
    policy: OptimizationPolicy,
    song: PcmAudio,
    encoder: object,
    embedding: object,
    handle: bytes,
) -> tuple[int, int, float]:
    """Spend fallback attempts only until the policy threshold is met or budget is exhausted."""

    cheap_recoveries = sum(record.cheap_recovered for record in records)
    if cheap_recoveries >= policy.voting_threshold:
        return 0, 0, 0.0
    block_length = len(embedding.audio.samples)
    attempts = 0
    recoveries = 0
    started = perf_counter()
    for record in records:
        if attempts >= policy.fallback_window_budget:
            break
        if record.cheap_recovered:
            continue
        start = int(round(record.start_seconds * song.sample_rate))
        vote = _run_controller(_window(song, start, block_length), encoder, embedding.carrier_plan, _fallback_stages(), (embedding, handle))
        attempts += 1
        recoveries += int(_matches(vote))
        if cheap_recoveries + recoveries >= policy.voting_threshold:
            break
    return attempts, recoveries, (perf_counter() - started) * 1000.0


def _next_tool(result: OptimizationResult) -> str:
    """Classify the next recovery tool from policy outcome and observed distress."""

    if result.accepted:
        return "stop_at_block_vote"
    if result.cheap_failures_with_high_pilot > 0 and result.fallback_recoveries == 0:
        return "cross_block_symbol_pooling"
    if result.exact_starts < result.top_window_count:
        return "window_prefilter_or_geometry_search"
    return "bounded_geometry_fallback"


def _evaluate_policy(
    policy: OptimizationPolicy,
    records: tuple[WindowRecovery, ...],
    prefilter_elapsed_ms: float,
    cheap_elapsed_ms: float,
    context: tuple[PcmAudio, object, object, bytes],
) -> OptimizationResult:
    """Evaluate one optimization policy against the shared top-seven fixture."""

    selected = records[: policy.top_window_count]
    cheap_recoveries = sum(record.cheap_recovered for record in selected)
    exact_starts = sum(record.is_exact_block_start for record in selected)
    high_pilot_failures = sum(record.is_exact_block_start and not record.cheap_recovered for record in selected)
    attempts, fallback_recoveries, fallback_elapsed_ms = _fallback(selected, policy, *context)
    final_recoveries = cheap_recoveries + fallback_recoveries
    accepted = final_recoveries >= policy.voting_threshold
    estimated_total_ms = prefilter_elapsed_ms + cheap_elapsed_ms * policy.top_window_count / len(records) + fallback_elapsed_ms
    result = OptimizationResult(
        policy.name,
        policy.top_window_count,
        policy.voting_threshold,
        policy.fallback_window_budget,
        exact_starts,
        cheap_recoveries,
        high_pilot_failures,
        attempts,
        fallback_recoveries,
        final_recoveries,
        accepted,
        "",
        estimated_total_ms,
        fallback_elapsed_ms,
    )
    return OptimizationResult(
        policy.name,
        policy.top_window_count,
        policy.voting_threshold,
        policy.fallback_window_budget,
        exact_starts,
        cheap_recoveries,
        high_pilot_failures,
        attempts,
        fallback_recoveries,
        final_recoveries,
        accepted,
        _next_tool(result),
        estimated_total_ms,
        fallback_elapsed_ms,
    )


def run() -> dict[str, object]:
    """Run the block-voting and fallback optimization experiment."""

    handle, _, encoder, embeddings, song = _song()
    records, prefilter_elapsed_ms, cheap_elapsed_ms = _recover_top_windows(song, encoder, embeddings[0], handle, 7)
    context = (song, encoder, embeddings[0], handle)
    results = tuple(_evaluate_policy(policy, records, prefilter_elapsed_ms, cheap_elapsed_ms, context) for policy in _policies())
    return {
        "goal": "optimize block voting thresholds and fallback handoff policy",
        "shared_fixture": {
            "song_seconds": 150,
            "window_seconds": 30,
            "ranked_windows": len(records),
            "prefilter_elapsed_ms": prefilter_elapsed_ms,
            "cheap_recovery_elapsed_ms": cheap_elapsed_ms,
        },
        "ranked_windows": [asdict(record) for record in records],
        "results": [asdict(result) for result in results],
        "recommendation": "use block voting for acceptance, route high-pilot cheap failures to cross-block pooling before geometry fallback",
    }


def main() -> None:
    """Print the block-voting and fallback optimization experiment."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

