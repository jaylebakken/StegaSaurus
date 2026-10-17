"""Run iteration 013: prototype block voting plus expensive fallback.

Goal: turn the repeated-block idea into a production-shaped maximum-cost
controller. The controller first uses cheap pilot-only evidence to rank likely
30-second windows, then runs received-duration recovery on the best windows,
then spends single-edge crop-search only if the requested vote threshold is not
met.

Toy flow:
    repeated-block song -> pilot window ranking -> top windows
        -> received-duration recovery -> block vote
        -> optional 125..500 ms single-edge fallback -> final vote

The experiment still receives a claimed carrier plan and synthetic repeated
blocks. It evaluates scheduling policy and cost shape; it does not claim fully
unknown-handle or arbitrary-geometry attribution.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from time import perf_counter

import numpy as np

from ....pilot import PcmAudio
from ..iteration_004_staged_recovery_controller.run import ControllerStage, _run_controller
from ..iteration_012_window_prefilter_smoke.run import (
    WindowScore,
    _block_cover,
    _encoder,
    _pilot_window_score,
    _stage,
    _window,
)


@dataclass(frozen=True, slots=True)
class WaterfallPolicy:
    """Declare one block-voting policy and its fallback budget."""
    name: str
    voting_threshold: int
    maximum_fallback_windows: int


@dataclass(frozen=True, slots=True)
class WindowRecovery:
    """Record recovery behavior for one ranked candidate window."""
    start_seconds: float
    pilot_score: float
    is_exact_block_start: bool
    cheap_recovered: bool
    fallback_recovered: bool
    fallback_attempted: bool


@dataclass(frozen=True, slots=True)
class WaterfallTrial:
    """Record one policy decision over the same ranked window set."""

    policy_name: str
    voting_threshold: int
    maximum_fallback_windows: int
    top_window_count: int
    exact_starts_in_top_windows: int
    cheap_recoveries: int
    fallback_attempts: int
    fallback_recoveries: int
    final_recoveries: int
    accepted: bool
    prefilter_elapsed_ms: float
    cheap_recovery_elapsed_ms: float
    fallback_elapsed_ms: float
    total_elapsed_ms: float


def _fallback_stages() -> tuple[ControllerStage, ...]:
    """Return the expensive crop-search hypotheses used after cheap voting fails."""

    return (
        ControllerStage("crop_loss_0.125s", (0.125,), "single-edge crop fallback"),
        ControllerStage("crop_loss_0.250s", (0.25,), "single-edge crop fallback"),
        ControllerStage("crop_loss_0.375s", (0.375,), "single-edge crop fallback"),
        ControllerStage("crop_loss_0.500s", (0.5,), "single-edge crop fallback"),
    )


def _policies() -> tuple[WaterfallPolicy, ...]:
    """Return waterfall policies from online attribution to maximum-cost mode."""

    return (
        WaterfallPolicy("online_any_block", 1, 0),
        WaterfallPolicy("high_assurance_two_block", 2, 0),
        WaterfallPolicy("max_cost_four_block", 4, 2),
    )


def _song() -> tuple[bytes, object, object, tuple[object, ...], PcmAudio]:
    """Build one deterministic 2.5-minute song made of five watermarked blocks."""

    handle, pilot, encoder = _encoder()
    embeddings = tuple(encoder.embed(_block_cover(index), handle) for index in range(5))
    samples = np.concatenate([embedding.audio.samples for embedding in embeddings])
    audio = PcmAudio(np.asarray(samples, dtype=np.float64), embeddings[0].audio.sample_rate)
    return handle, pilot, encoder, embeddings, audio


def _rank_windows(song: PcmAudio, encoder: object, embedding: object, top_window_count: int) -> tuple[tuple[WindowScore, ...], float]:
    """Rank sliding windows by pilot-only evidence and return the top candidates."""

    block_length = len(embedding.audio.samples)
    exact_starts = {index * block_length for index in range(5)}
    started = perf_counter()
    scores = tuple(
        WindowScore(
            start / song.sample_rate,
            _pilot_window_score(encoder, _window(song, start, block_length), embedding.carrier_plan),
            start in exact_starts,
        )
        for start in range(0, len(song.samples) - block_length + 1, block_length // 2)
    )
    elapsed = (perf_counter() - started) * 1000.0
    return tuple(sorted(scores, key=lambda score: score.pilot_score, reverse=True)[:top_window_count]), elapsed


def _matches(vote: object) -> bool:
    """Return whether a controller vote recovered the expected token."""

    measurement = vote.measurement or {}
    return bool(vote.accepted and measurement.get("token_matches_input", False))


def _cheap_recoveries(
    song: PcmAudio,
    encoder: object,
    embedding: object,
    handle: bytes,
    windows: tuple[WindowScore, ...],
) -> tuple[tuple[WindowRecovery, ...], float]:
    """Run received-duration recovery on the ranked windows."""

    block_length = len(embedding.audio.samples)
    records: list[WindowRecovery] = []
    started = perf_counter()
    for score in windows:
        start = int(round(score.start_seconds * song.sample_rate))
        vote = _run_controller(_window(song, start, block_length), encoder, embedding.carrier_plan, _stage(), (embedding, handle))
        records.append(WindowRecovery(score.start_seconds, score.pilot_score, score.is_exact_block_start, _matches(vote), False, False))
    return tuple(records), (perf_counter() - started) * 1000.0


def _run_policy(
    policy: WaterfallPolicy,
    song: PcmAudio,
    encoder: object,
    embedding: object,
    handle: bytes,
    windows: tuple[WindowRecovery, ...],
    prefilter_elapsed_ms: float,
    cheap_elapsed_ms: float,
) -> tuple[WaterfallTrial, tuple[WindowRecovery, ...]]:
    """Apply one voting policy and spend fallback only when required."""

    block_length = len(embedding.audio.samples)
    final_windows = list(windows)
    cheap_recoveries = sum(record.cheap_recovered for record in final_windows)
    fallback_attempts = 0
    fallback_recoveries = 0
    started = perf_counter()
    if cheap_recoveries < policy.voting_threshold:
        for index, record in enumerate(final_windows):
            if fallback_attempts >= policy.maximum_fallback_windows:
                break
            if record.cheap_recovered:
                continue
            start = int(round(record.start_seconds * song.sample_rate))
            vote = _run_controller(
                _window(song, start, block_length),
                encoder,
                embedding.carrier_plan,
                _fallback_stages(),
                (embedding, handle),
            )
            recovered = _matches(vote)
            fallback_attempts += 1
            fallback_recoveries += int(recovered)
            final_windows[index] = WindowRecovery(
                record.start_seconds,
                record.pilot_score,
                record.is_exact_block_start,
                record.cheap_recovered,
                recovered,
                True,
            )
            if cheap_recoveries + fallback_recoveries >= policy.voting_threshold:
                break
    fallback_elapsed_ms = (perf_counter() - started) * 1000.0
    final_recoveries = cheap_recoveries + fallback_recoveries
    trial = WaterfallTrial(
        policy.name,
        policy.voting_threshold,
        policy.maximum_fallback_windows,
        len(final_windows),
        sum(record.is_exact_block_start for record in final_windows),
        cheap_recoveries,
        fallback_attempts,
        fallback_recoveries,
        final_recoveries,
        final_recoveries >= policy.voting_threshold,
        prefilter_elapsed_ms,
        cheap_elapsed_ms,
        fallback_elapsed_ms,
        prefilter_elapsed_ms + cheap_elapsed_ms + fallback_elapsed_ms,
    )
    return trial, tuple(final_windows)


def run(top_window_count: int = 5) -> dict[str, object]:
    """Run the block-waterfall controller experiment."""

    handle, _, encoder, embeddings, song = _song()
    ranked, prefilter_elapsed_ms = _rank_windows(song, encoder, embeddings[0], top_window_count)
    cheap, cheap_elapsed_ms = _cheap_recoveries(song, encoder, embeddings[0], handle, ranked)
    policy_results = tuple(
        _run_policy(policy, song, encoder, embeddings[0], handle, cheap, prefilter_elapsed_ms, cheap_elapsed_ms)
        for policy in _policies()
    )
    trials = tuple(result[0] for result in policy_results)
    windows = {trial.policy_name: tuple(asdict(record) for record in records) for trial, records in policy_results}
    return {
        "goal": "compose pilot prefilter, repeated-block voting, and bounded expensive fallback",
        "song_seconds": 150,
        "window_seconds": 30,
        "stride_seconds": 15,
        "controller_shape": "rank top windows, vote cheap recoveries, then spend fallback only if threshold is unmet",
        "trials": [asdict(trial) for trial in trials],
        "policy_windows": windows,
    }


def main() -> None:
    """Print the block-waterfall controller experiment."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
