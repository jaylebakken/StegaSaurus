"""Run iteration 012: smoke-test a pilot prefilter for repeated block windows.

Goal: replace exact block-window knowledge with a cheap ranked window prefilter.
The experiment embeds five independent 30-second blocks into a 2.5-minute
synthetic song, scores 30-second windows every 15 seconds using local-pilot
evidence, and runs full recovery only on the top windows.

Toy flow:
    repeated-block song -> sliding windows -> pilot-only scores
        -> top windows -> received-duration recovery -> block vote

This is still a smoke test. It uses a claimed carrier plan and synthetic block
boundaries; it does not claim arbitrary audio localization.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from statistics import median
from time import perf_counter

import numpy as np

from ....pilot import PcmAudio, SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioWatermarkConfig, CarrierPlan
from ...non_oracle_reconstruction.iteration_005_contrastive_pilot_calibration.run import ContrastivePilotCalibratedExperiment
from ...non_oracle_reconstruction.iteration_019_registry_handle_parity_tradeoff.run import _profile
from ...non_oracle_reconstruction.iteration_021_coarse_hypothesis_bank.run import _allocation
from ...transport_optimization.iteration_006_duration_stability_bounds.run import _cover_variant, _trial_offset_seconds
from ..iteration_004_staged_recovery_controller.run import ControllerStage, _run_controller


@dataclass(frozen=True, slots=True)
class WindowScore:
    """Record one sliding window score before recovery."""

    start_seconds: float
    pilot_score: float
    is_exact_block_start: bool


@dataclass(frozen=True, slots=True)
class PrefilterResult:
    """Record top-window recovery and localization behavior."""

    top_window_count: int
    exact_starts_in_top_windows: int
    recovered_windows: int
    any_block_accepted: bool
    two_block_accepted: bool
    prefilter_elapsed_ms: float
    recovery_elapsed_ms: float


def _encoder() -> tuple[bytes, SpectralAudioPilot, ContrastivePilotCalibratedExperiment]:
    """Create the fixed pilot and encoder used by the blind-recovery track."""

    config = SpectralPilotConfig(minimum_frequency_hz=500.0, maximum_frequency_hz=3800.0, relative_difference=0.95)
    pilot = SpectralAudioPilot(b"audio-pilot-test-key", config, AudioWatermarkConfig(attribution_token_bytes=4, parity_symbols=16))
    return _allocation().handle(), pilot, ContrastivePilotCalibratedExperiment(pilot, 0.01, _profile())


def _block_cover(index: int) -> PcmAudio:
    """Return one deterministic 30-second synthetic block cover."""

    return _cover_variant(30, 7900 + index, _trial_offset_seconds(1800 + index))


def _stage() -> tuple[ControllerStage, ...]:
    """Return exact-window received-duration recovery."""

    return (ControllerStage("received_only", (0.0,), "candidate window"),)


def _window(audio: PcmAudio, start_sample: int, length: int) -> PcmAudio:
    """Return one fixed-length window."""

    return PcmAudio(audio.samples[start_sample : start_sample + length], audio.sample_rate)


def _pilot_window_score(encoder: ContrastivePilotCalibratedExperiment, audio: PcmAudio, plan: CarrierPlan) -> float:
    """Score one window using local-pilot candidate margins without RS recovery."""

    frequencies, spectrum = encoder._pilot._stft(audio)
    lower_bin, upper_bin = encoder._pilot._frequency_bin_range(frequencies)
    maps = tuple(
        encoder._ranked_frame_maps(spectrum, frame_range, plan.carrier_bits, lower_bin, upper_bin)
        for frame_range in encoder._replica_ranges(spectrum.shape[1])
    )
    margins: list[float] = []
    for replica_index, replica_maps in enumerate(maps):
        for carrier_index in range(len(plan.carrier_bits)):
            scores = tuple(
                encoder.pilot_score_at_frame(spectrum, lower_bin, upper_bin, replica_maps[rank][carrier_index])
                for rank in range(encoder._candidate_rank_count)
            )
            sign = 1.0 if encoder.selection_pilot_bit(replica_index, carrier_index) else -1.0
            signed = tuple(float("-inf") if score is None else sign * score for score in scores)
            best = max(range(encoder._candidate_rank_count), key=lambda rank: (signed[rank], -rank))
            other = 1 - best
            if np.isfinite(signed[best]) and np.isfinite(signed[other]):
                margins.append(signed[best] - signed[other])
    return float(median(margins)) if margins else float("-inf")


def run(top_window_count: int = 5) -> dict[str, object]:
    """Run the sliding-window prefilter smoke test."""

    handle, pilot, encoder = _encoder()
    embeddings = tuple(encoder.embed(_block_cover(index), handle) for index in range(5))
    block_length = len(embeddings[0].audio.samples)
    samples = np.concatenate([embedding.audio.samples for embedding in embeddings])
    song = PcmAudio(np.asarray(samples, dtype=np.float64), embeddings[0].audio.sample_rate)
    exact_starts = {index * block_length for index in range(len(embeddings))}
    stride = block_length // 2
    started = perf_counter()
    scores = tuple(
        WindowScore(
            start / song.sample_rate,
            _pilot_window_score(encoder, _window(song, start, block_length), embeddings[0].carrier_plan),
            start in exact_starts,
        )
        for start in range(0, len(song.samples) - block_length + 1, stride)
    )
    prefilter_elapsed = (perf_counter() - started) * 1000.0
    top = tuple(sorted(scores, key=lambda score: score.pilot_score, reverse=True)[:top_window_count])
    recovered = 0
    started = perf_counter()
    for score in top:
        start = int(round(score.start_seconds * song.sample_rate))
        vote = _run_controller(_window(song, start, block_length), encoder, embeddings[0].carrier_plan, _stage(), (embeddings[0], handle))
        measurement = vote.measurement or {}
        recovered += int(vote.accepted and bool(measurement.get("token_matches_input", False)))
    recovery_elapsed = (perf_counter() - started) * 1000.0
    result = PrefilterResult(top_window_count, sum(score.is_exact_block_start for score in top), recovered, recovered >= 1, recovered >= 2, prefilter_elapsed, recovery_elapsed)
    return {
        "goal": "rank repeated-block candidate windows with a cheap local-pilot prefilter",
        "song_seconds": 150,
        "window_seconds": 30,
        "stride_seconds": 15,
        "result": asdict(result),
        "top_windows": [asdict(score) for score in top],
        "all_windows": [asdict(score) for score in scores],
    }


def main() -> None:
    """Print the window-prefilter smoke test."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
