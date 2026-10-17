"""Run iteration 022: finer phase-bank search for off-grid crop recovery.

Goal: determine whether the arbitrary-crop failure in iteration 021 is caused
by the coarse 15-second window grid or by a deeper reconstruction limit. This
experiment keeps the same pooled waterfall but ranks windows every 2.5 seconds
after an off-grid dual-edge crop.

Toy flow:
    off-grid cropped song -> 2.5s candidate bank -> pool top windows
        -> compare watermarked, unwatermarked, and wrong-secret controls

This is a targeted crop-recovery experiment. It does not claim arbitrary crop
robustness unless the measured controls also reject.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from time import perf_counter

import numpy as np

from ....attacks import trim_audio
from ....pilot import PcmAudio
from ..iteration_012_window_prefilter_smoke.run import WindowScore, _pilot_window_score, _window
from ..iteration_018_pooling_control_gate.run import _evidence_for_scores, _pool_records, _wrong_encoder
from ..iteration_019_held_out_pooling_controls.run import TrialContext, _held_out_song


@dataclass(frozen=True, slots=True)
class PhaseBankControl:
    """Record one pooled control under a phase-bank crop search."""

    control_name: str
    expected_recovered: bool
    pooled_recovered: bool
    pooled_rs_cost: int
    exact_or_near_starts: int
    token_returning_blocks: int
    gate_passed: bool


@dataclass(frozen=True, slots=True)
class PhaseBankResult:
    """Summarize one phase-bank search budget."""

    stride_seconds: float
    top_window_count: int
    ranked_windows: int
    prefilter_elapsed_ms: float
    extraction_elapsed_ms: float
    controls_passed: bool
    watermarked_recovered: bool


def _off_grid_crop(audio: PcmAudio) -> PcmAudio:
    """Apply the arbitrary off-grid crop that failed in iteration 021."""

    return trim_audio(audio, 7.3, audio.duration_seconds - 11.7)


def _rank_phase_bank(
    audio: PcmAudio,
    context: TrialContext,
    stride_seconds: float,
    top_window_count: int,
) -> tuple[tuple[WindowScore, ...], float, int]:
    """Rank a finer candidate bank over the cropped received song."""

    block_length = len(context.embeddings[0].audio.samples)
    stride = max(1, int(round(stride_seconds * audio.sample_rate)))
    near_tolerance = int(round(0.30 * audio.sample_rate))
    exact_starts = tuple(index * block_length - int(round(7.3 * audio.sample_rate)) for index in range(5))
    started = perf_counter()
    scores = tuple(
        WindowScore(
            start / audio.sample_rate,
            _pilot_window_score(context.encoder, _window(audio, start, block_length), context.embeddings[0].carrier_plan),
            any(abs(start - exact_start) <= near_tolerance for exact_start in exact_starts),
        )
        for start in range(0, len(audio.samples) - block_length + 1, stride)
    )
    elapsed = (perf_counter() - started) * 1000.0
    return tuple(sorted(scores, key=lambda score: score.pilot_score, reverse=True)[:top_window_count]), elapsed, len(scores)


def _control(name: str, expected: bool, pool: object) -> PhaseBankControl:
    """Convert a pooled result into a phase-bank control row."""

    recovered = bool(pool.pooled_recovered and pool.pooled_rs_cost <= 16)
    return PhaseBankControl(
        name,
        expected,
        recovered,
        pool.pooled_rs_cost,
        pool.exact_starts,
        pool.blocks_returning_token,
        recovered is expected,
    )


def _run_controls(context: TrialContext, stride_seconds: float, top_window_count: int) -> tuple[PhaseBankResult, tuple[PhaseBankControl, ...], tuple[WindowScore, ...]]:
    """Run top-window pooling controls for one phase-bank budget."""

    watermarked = _off_grid_crop(context.watermarked_song)
    source = _off_grid_crop(context.source_song)
    ranked, prefilter_elapsed_ms, ranked_windows = _rank_phase_bank(watermarked, context, stride_seconds, top_window_count)
    block_length = len(context.embeddings[0].audio.samples)
    started = perf_counter()
    watermarked_records = _evidence_for_scores(watermarked, context.encoder, context.embeddings[0].carrier_plan, context.handle, ranked, block_length)
    unwatermarked_records = _evidence_for_scores(source, context.encoder, context.embeddings[0].carrier_plan, context.handle, ranked, block_length)
    wrong_encoder = _wrong_encoder()
    wrong_plan = wrong_encoder._pilot.schema.plan_attribution(context.handle)
    wrong_records = _evidence_for_scores(watermarked, wrong_encoder, wrong_plan, context.handle, ranked, block_length)
    extraction_elapsed_ms = (perf_counter() - started) * 1000.0
    pools = (
        _pool_records("watermarked_top", watermarked_records, context.encoder, context.embeddings[0].carrier_plan, context.handle),
        _pool_records("unwatermarked_top", unwatermarked_records, context.encoder, context.embeddings[0].carrier_plan, context.handle),
        _pool_records("wrong_secret_top", wrong_records, wrong_encoder, wrong_plan, context.handle),
    )
    controls = (
        _control("watermarked_top", True, pools[0]),
        _control("unwatermarked_top", False, pools[1]),
        _control("wrong_secret_top", False, pools[2]),
    )
    result = PhaseBankResult(
        stride_seconds,
        top_window_count,
        ranked_windows,
        prefilter_elapsed_ms,
        extraction_elapsed_ms,
        all(control.gate_passed for control in controls),
        controls[0].pooled_recovered,
    )
    return result, controls, ranked


def run() -> dict[str, object]:
    """Run a 2.5-second phase bank against the off-grid crop failure."""

    context = _held_out_song(0)
    result, controls, ranked = _run_controls(context, 2.5, 5)
    return {
        "goal": "test whether finer phase-bank ranking rescues arbitrary off-grid crop",
        "result": asdict(result),
        "controls": [asdict(control) for control in controls],
        "top_windows": [asdict(score) for score in ranked],
        "recommendation": (
            "phase-bank crop search is a launch candidate"
            if result.controls_passed
            else "arbitrary crop needs a new recovery stage beyond finer window ranking"
        ),
    }


def main() -> None:
    """Print the arbitrary-crop phase-bank experiment."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
