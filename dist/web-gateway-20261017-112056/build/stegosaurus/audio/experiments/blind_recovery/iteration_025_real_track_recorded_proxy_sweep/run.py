"""Run iteration 025: recorded-proxy sweep on a user-supplied WAV file.

Goal: repeat the recorded-audio proxy upper-bound sweep on a real cover track
chosen by the user. The file is trimmed to complete 30-second blocks, embedded
with repeated attribution, attacked by the same severity ladder, and verified
with pooled carrier evidence plus negative controls.

Toy flow:
    user WAV -> first three 30s blocks -> embed repeated handle
        -> distortion ladder -> rank/pool controls -> write listening artifacts

The sweep measures this one file and these named synthetic transformations. It
does not claim general classical, codec, room, or recorded-audio robustness.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from time import perf_counter

import numpy as np

from ....attacks import add_reverberation, add_white_noise, low_pass_filter, normalize_peak, resample_audio
from ....encoder import SpectralAudioEncoder
from ....pilot import PcmAudio, read_pcm16_wav, write_pcm16_wav
from ..iteration_012_window_prefilter_smoke.run import WindowScore, _encoder, _pilot_window_score, _window
from ..iteration_018_pooling_control_gate.run import _evidence_for_scores, _pool_records, _wrong_encoder
from ..iteration_024_recorded_proxy_upper_bound.run import DistortionLevel, LevelResult, _levels
from ...transport_optimization.iteration_004_four_frame_soft_combine.run import FourFrameCapacityError


SOURCE_PATH = Path(r"C:\Users\jay\Downloads\onclassical_demo_luisi_bach_partita_a-minor_bwv-827_1_small-version.wav")
BLOCK_SECONDS = 30


@dataclass(frozen=True, slots=True)
class TrackContext:
    """Hold one real-track repeated-block watermark fixture."""

    handle: bytes
    encoder: object
    embeddings: tuple[object, ...]
    watermarked_song: PcmAudio
    source_song: PcmAudio
    source_starts_seconds: tuple[float, ...]


def _track_context(source_path: Path = SOURCE_PATH) -> TrackContext:
    """Read the supplied WAV and embed capacity-valid 30-second excerpts."""

    source = read_pcm16_wav(source_path)
    block_length = int(round(BLOCK_SECONDS * source.sample_rate))
    if len(source.samples) < block_length:
        raise ValueError("source WAV must contain at least one complete 30-second block")
    handle, _, encoder = _encoder()
    blocks: list[PcmAudio] = []
    embeddings: list[object] = []
    starts: list[float] = []
    stride = int(round(5.0 * source.sample_rate))
    for start in range(0, len(source.samples) - block_length + 1, stride):
        raw_block = PcmAudio(np.asarray(source.samples[start : start + block_length], dtype=np.float64), source.sample_rate)
        block = normalize_peak(raw_block, 0.90)
        try:
            embedding = encoder.embed(block, handle)
        except FourFrameCapacityError:
            continue
        blocks.append(block)
        embeddings.append(embedding)
        starts.append(start / source.sample_rate)
        if len(blocks) == 3:
            break
    if not blocks:
        raise ValueError("no capacity-valid 30-second excerpts were found in the supplied WAV")
    watermarked = PcmAudio(np.asarray(np.concatenate([embedding.audio.samples for embedding in embeddings]), dtype=np.float64), source.sample_rate)
    source_song = PcmAudio(np.asarray(np.concatenate([block.samples for block in blocks]), dtype=np.float64), source.sample_rate)
    return TrackContext(handle, encoder, tuple(embeddings), watermarked, source_song, tuple(starts))


def _capacity_audit(source_path: Path) -> tuple[dict[str, object], ...]:
    """Measure detector-pilot capacity and attribution carrier capacity by excerpt."""

    source = read_pcm16_wav(source_path)
    block_length = int(round(BLOCK_SECONDS * source.sample_rate))
    handle, _, attribution_encoder = _encoder()
    pilot_encoder = SpectralAudioEncoder(b"audio-pilot-test-key")
    rows: list[dict[str, object]] = []
    for start in range(0, len(source.samples) - block_length + 1, int(round(5.0 * source.sample_rate))):
        raw_block = PcmAudio(np.asarray(source.samples[start : start + block_length], dtype=np.float64), source.sample_rate)
        block = normalize_peak(raw_block, 0.90)
        pilot = pilot_encoder.encode(block, "2026-10-10")
        try:
            attribution_encoder.embed(block, handle)
            attribution_capacity = "ok"
        except FourFrameCapacityError:
            attribution_capacity = "FourFrameCapacityError"
        rows.append(
            {
                "start_seconds": start / source.sample_rate,
                "pilot_embedded_frames": pilot.embedded_frame_count,
                "pilot_skipped_frames": pilot.skipped_frame_count,
                "pilot_snr_db": round(pilot.signal_to_noise_db, 2),
                "v2_attribution_capacity": attribution_capacity,
            }
        )
    return tuple(rows)


def _apply_level(audio: PcmAudio, level: DistortionLevel) -> PcmAudio:
    """Apply one recorded-audio proxy severity to this track."""

    transformed = resample_audio(resample_audio(audio, level.resample_hz), audio.sample_rate)
    transformed = low_pass_filter(transformed, level.low_pass_hz)
    transformed = add_reverberation(transformed, level.reverb_decay_seconds, level.reverb_mix, seed=20261010)
    transformed = add_white_noise(transformed, level.noise_snr_db, seed=20261010)
    return normalize_peak(transformed, level.target_peak)


def _rank_track(audio: PcmAudio, context: TrackContext, top_window_count: int) -> tuple[WindowScore, ...]:
    """Rank top candidate block windows for the real-track fixture."""

    block_length = len(context.embeddings[0].audio.samples)
    exact_starts = {index * block_length for index in range(len(context.embeddings))}
    stride = block_length // 2
    scores = tuple(
        WindowScore(
            start / audio.sample_rate,
            _pilot_window_score(context.encoder, _window(audio, start, block_length), context.embeddings[0].carrier_plan),
            start in exact_starts,
        )
        for start in range(0, len(audio.samples) - block_length + 1, stride)
    )
    return tuple(sorted(scores, key=lambda score: score.pilot_score, reverse=True)[:top_window_count])


def _recover(context: TrackContext, watermarked: PcmAudio, source: PcmAudio) -> tuple[object, object, object, float]:
    """Run rank-and-pool verification for one attacked pair."""

    ranked = _rank_track(watermarked, context, len(context.embeddings))
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


def _level_result(index: int, level: DistortionLevel, context: TrackContext) -> tuple[LevelResult, PcmAudio]:
    """Evaluate one severity level and return the attacked watermarked audio."""

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


def run(source_path: Path = SOURCE_PATH) -> dict[str, object]:
    """Run the recorded-proxy sweep on the supplied WAV file."""

    try:
        context = _track_context(source_path)
    except ValueError as error:
        source = read_pcm16_wav(source_path)
        return {
            "goal": "find the strongest recorded-proxy level recovered on the requested WAV",
            "source_path": str(source_path),
            "source_duration_seconds": source.duration_seconds,
            "used_duration_seconds": 0.0,
            "block_count": 0,
            "capacity_audit": list(_capacity_audit(source_path)),
            "highest_recovered": None,
            "clean_artifact_path": None,
            "distorted_artifact_path": None,
            "recommendation": f"cannot run attribution robustness sweep: {error}",
        }
    output_dir = Path(__file__).parent
    clean_path = output_dir / "onclassical_clean_watermarked_reference.wav"
    write_pcm16_wav(clean_path, context.watermarked_song)
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
        artifact_path = output_dir / f"onclassical_{best.name}_recovered_example.wav"
        write_pcm16_wav(artifact_path, audio_by_name[best.name])
    return {
        "goal": "find the strongest recorded-proxy level recovered on the requested WAV",
        "source_path": str(source_path),
        "source_duration_seconds": read_pcm16_wav(source_path).duration_seconds,
        "used_duration_seconds": context.watermarked_song.duration_seconds,
        "block_count": len(context.embeddings),
        "source_starts_seconds": context.source_starts_seconds,
        "levels": [asdict(level) for level in _levels()],
        "results": [asdict(result) for result in results],
        "highest_recovered": asdict(best) if best is not None else None,
        "clean_artifact_path": str(clean_path),
        "distorted_artifact_path": str(artifact_path) if artifact_path is not None else None,
        "recommendation": _recommendation(best),
    }


def _recommendation(best: LevelResult | None) -> str:
    """Return a concise recommendation from the real-track sweep."""

    if best is None:
        return "the requested track did not pass any recorded-proxy level with current pooling"
    return f"use {best.name} as the measured listening upper bound for this requested track"


def main() -> None:
    """Print the real-track recorded-proxy sweep."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
