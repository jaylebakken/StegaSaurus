"""Run iteration 024: sweep recorded-proxy distortion and save a WAV example.

Goal: find the strongest deterministic recorded-audio proxy that the current
waterfall can still recover while unwatermarked and wrong-secret controls
reject. The winning attacked WAV is written beside this experiment so it can be
auditioned directly.

Toy flow:
    held-out watermarked song -> severity ladder -> rank/pool controls
        -> choose highest passing severity -> write WAV artifact

The sweep tests named synthetic processing chains only. It does not establish
real microphone, room, platform, or device robustness.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from time import perf_counter

from ....attacks import add_reverberation, add_white_noise, low_pass_filter, normalize_peak, resample_audio
from ....pilot import PcmAudio, write_pcm16_wav
from ..iteration_018_pooling_control_gate.run import _evidence_for_scores, _pool_records, _wrong_encoder
from ..iteration_019_held_out_pooling_controls.run import CropFixture, TrialContext, _held_out_song, _rank_fixture


@dataclass(frozen=True, slots=True)
class DistortionLevel:
    """Declare one deterministic recorded-audio proxy severity."""

    name: str
    resample_hz: int
    low_pass_hz: float
    reverb_decay_seconds: float
    reverb_mix: float
    noise_snr_db: float
    target_peak: float


@dataclass(frozen=True, slots=True)
class LevelResult:
    """Record one severity outcome."""

    name: str
    severity_index: int
    watermarked_recovered: bool
    watermarked_rs_cost: int
    unwatermarked_recovered: bool
    unwatermarked_rs_cost: int
    wrong_secret_recovered: bool
    wrong_secret_rs_cost: int
    token_returning_blocks: int
    elapsed_ms: float
    gate_passed: bool


def _levels() -> tuple[DistortionLevel, ...]:
    """Return a monotonic recorded-proxy severity ladder."""

    return (
        DistortionLevel("level_1_light", 12000, 3800.0, 0.080, 0.10, 35.0, 0.85),
        DistortionLevel("level_2_moderate", 10000, 3400.0, 0.120, 0.16, 30.0, 0.82),
        DistortionLevel("level_3_strong", 9000, 3000.0, 0.180, 0.22, 26.0, 0.78),
        DistortionLevel("level_4_heavy", 8000, 2600.0, 0.260, 0.30, 22.0, 0.74),
        DistortionLevel("level_5_extreme", 7000, 2200.0, 0.360, 0.38, 18.0, 0.70),
    )


def _apply_level(audio: PcmAudio, level: DistortionLevel) -> PcmAudio:
    """Apply one recorded-audio proxy severity to an audio signal."""

    transformed = resample_audio(resample_audio(audio, level.resample_hz), audio.sample_rate)
    transformed = low_pass_filter(transformed, level.low_pass_hz)
    transformed = add_reverberation(transformed, level.reverb_decay_seconds, level.reverb_mix, seed=20261010)
    transformed = add_white_noise(transformed, level.noise_snr_db, seed=20261010)
    return normalize_peak(transformed, level.target_peak)


def _recover(context: TrialContext, watermarked: PcmAudio, source: PcmAudio) -> tuple[object, object, object, float]:
    """Run the current rank-and-pool waterfall for one attacked pair."""

    ranked = _rank_fixture(watermarked, context.encoder, context.embeddings[0], CropFixture("attacked", 0.0, 0.0), 5)
    block_length = len(context.embeddings[0].audio.samples)
    started = perf_counter()
    watermarked_records = _evidence_for_scores(watermarked, context.encoder, context.embeddings[0].carrier_plan, context.handle, ranked, block_length)
    unwatermarked_records = _evidence_for_scores(source, context.encoder, context.embeddings[0].carrier_plan, context.handle, ranked, block_length)
    wrong_encoder = _wrong_encoder()
    wrong_plan = wrong_encoder._pilot.schema.plan_attribution(context.handle)
    wrong_records = _evidence_for_scores(watermarked, wrong_encoder, wrong_plan, context.handle, ranked, block_length)
    elapsed_ms = (perf_counter() - started) * 1000.0
    return (
        _pool_records("watermarked", watermarked_records, context.encoder, context.embeddings[0].carrier_plan, context.handle),
        _pool_records("unwatermarked", unwatermarked_records, context.encoder, context.embeddings[0].carrier_plan, context.handle),
        _pool_records("wrong_secret", wrong_records, wrong_encoder, wrong_plan, context.handle),
        elapsed_ms,
    )


def _level_result(index: int, level: DistortionLevel, context: TrialContext) -> tuple[LevelResult, PcmAudio]:
    """Evaluate one severity level and return its attacked watermarked audio."""

    watermarked = _apply_level(context.watermarked_song, level)
    source = _apply_level(context.source_song, level)
    watermarked_pool, unwatermarked_pool, wrong_pool, elapsed_ms = _recover(context, watermarked, source)
    watermarked_recovered = bool(watermarked_pool.pooled_recovered and watermarked_pool.pooled_rs_cost <= 16)
    unwatermarked_recovered = bool(unwatermarked_pool.pooled_recovered and unwatermarked_pool.pooled_rs_cost <= 16)
    wrong_recovered = bool(wrong_pool.pooled_recovered and wrong_pool.pooled_rs_cost <= 16)
    return (
        LevelResult(
            level.name,
            index,
            watermarked_recovered,
            watermarked_pool.pooled_rs_cost,
            unwatermarked_recovered,
            unwatermarked_pool.pooled_rs_cost,
            wrong_recovered,
            wrong_pool.pooled_rs_cost,
            watermarked_pool.blocks_returning_token,
            elapsed_ms,
            watermarked_recovered and not unwatermarked_recovered and not wrong_recovered,
        ),
        watermarked,
    )


def run() -> dict[str, object]:
    """Run the distortion sweep and write the highest passing WAV artifact."""

    context = _held_out_song(0)
    results: list[LevelResult] = []
    audio_by_name: dict[str, PcmAudio] = {}
    for index, level in enumerate(_levels(), start=1):
        result, attacked_audio = _level_result(index, level, context)
        results.append(result)
        audio_by_name[level.name] = attacked_audio
    passing = tuple(result for result in results if result.gate_passed)
    best = passing[-1] if passing else None
    artifact_path = None
    if best is not None:
        artifact_path = Path(__file__).with_name(f"{best.name}_recovered_example.wav")
        write_pcm16_wav(artifact_path, audio_by_name[best.name])
    return {
        "goal": "find the strongest named recorded-audio proxy recovered by the current waterfall",
        "levels": [asdict(level) for level in _levels()],
        "results": [asdict(result) for result in results],
        "highest_recovered": asdict(best) if best is not None else None,
        "artifact_path": str(artifact_path) if artifact_path is not None else None,
        "recommendation": _recommendation(best),
    }


def _recommendation(best: LevelResult | None) -> str:
    """Return the implementation recommendation for the sweep."""

    if best is None:
        return "no recorded-audio proxy level passed controls with the current waterfall"
    return f"use {best.name} as the current measured upper-bound listening artifact; validate wider seeds before claiming robustness"


def main() -> None:
    """Print the recorded-proxy upper-bound sweep."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
