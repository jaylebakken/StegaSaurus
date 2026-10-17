"""Run iteration 011: smoke-test repeated block watermarking on synthetic songs.

Goal: move the block-voting schema from an analytical model to an audio-bearing
fixture. The experiment embeds the same claimed handle into independent
30-second blocks, concatenates those blocks into longer synthetic songs, and
recovers from exact block windows.

Toy flow:
    block covers -> per-block embed -> concatenate -> exact window recovery
        -> any-block and two-block voting

This is not localization yet: the verifier receives exact block windows. It
tests whether repeated independent blocks are compatible with the current
claimed-plan recovery path before adding a window prefilter.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from time import perf_counter

import numpy as np

from ....pilot import PcmAudio, SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioWatermarkConfig
from ...non_oracle_reconstruction.iteration_005_contrastive_pilot_calibration.run import ContrastivePilotCalibratedExperiment
from ...non_oracle_reconstruction.iteration_019_registry_handle_parity_tradeoff.run import _profile
from ...non_oracle_reconstruction.iteration_021_coarse_hypothesis_bank.run import _allocation
from ...transport_optimization.iteration_006_duration_stability_bounds.run import _cover_variant, _trial_offset_seconds
from ..iteration_004_staged_recovery_controller.run import ControllerStage, _run_controller


@dataclass(frozen=True, slots=True)
class SongPlan:
    """Describe one repeated-block synthetic song."""

    name: str
    block_count: int


@dataclass(frozen=True, slots=True)
class BlockSmokeResult:
    """Record repeated-block recovery and voting outcomes for one song."""

    song_name: str
    block_count: int
    recovered_blocks: int
    any_block_accepted: bool
    two_block_accepted: bool
    elapsed_ms: float
    error: str | None


def _plans() -> tuple[SongPlan, ...]:
    """Return 30-second, 2.5-minute, and 5-minute block plans."""

    return (
        SongPlan("thirty_seconds", 1),
        SongPlan("two_and_half_minutes", 5),
        SongPlan("five_minutes", 10),
    )


def _encoder() -> tuple[bytes, SpectralAudioPilot, ContrastivePilotCalibratedExperiment]:
    """Create the fixed pilot and encoder used by the blind-recovery track."""

    config = SpectralPilotConfig(minimum_frequency_hz=500.0, maximum_frequency_hz=3800.0, relative_difference=0.95)
    pilot = SpectralAudioPilot(b"audio-pilot-test-key", config, AudioWatermarkConfig(attribution_token_bytes=4, parity_symbols=16))
    return _allocation().handle(), pilot, ContrastivePilotCalibratedExperiment(pilot, 0.01, _profile())


def _stage() -> tuple[ControllerStage, ...]:
    """Return exact received-duration recovery for exact block windows."""

    return (ControllerStage("received_only", (0.0,), "exact block window"),)


def _block_cover(index: int) -> PcmAudio:
    """Return one deterministic 30-second synthetic block cover."""

    return _cover_variant(30, 7900 + index, _trial_offset_seconds(1800 + index))


def _song(plan: SongPlan) -> BlockSmokeResult:
    """Embed independent blocks, concatenate them, and recover exact windows."""

    started = perf_counter()
    handle, pilot, encoder = _encoder()
    embeddings = tuple(encoder.embed(_block_cover(index), handle) for index in range(plan.block_count))
    samples = np.concatenate([embedding.audio.samples for embedding in embeddings])
    song = PcmAudio(np.asarray(samples, dtype=np.float64), embeddings[0].audio.sample_rate)
    recovered = 0
    block_length = len(embeddings[0].audio.samples)
    for index, embedding in enumerate(embeddings):
        start = index * block_length
        window = PcmAudio(song.samples[start : start + block_length], song.sample_rate)
        vote = _run_controller(window, encoder, embedding.carrier_plan, _stage(), (embedding, handle))
        measurement = vote.measurement or {}
        recovered += int(vote.accepted and bool(measurement.get("token_matches_input", False)))
    elapsed_ms = (perf_counter() - started) * 1000.0
    return BlockSmokeResult(plan.name, plan.block_count, recovered, recovered >= 1, recovered >= 2, elapsed_ms, None)


def _safe_song(plan: SongPlan) -> BlockSmokeResult:
    """Run one repeated-block smoke result and keep failures visible."""

    try:
        return _song(plan)
    except Exception as error:
        return BlockSmokeResult(plan.name, plan.block_count, 0, False, False, 0.0, f"{type(error).__name__}: {error}")


def run() -> dict[str, object]:
    """Run the repeated-block audio smoke test."""

    plans = _plans()
    results = tuple(_safe_song(plan) for plan in plans)
    return {
        "goal": "smoke-test repeated 30-second block watermarking across song lengths",
        "decoder_received_oracle_map": False,
        "decoder_received_exact_block_windows": True,
        "plans": [asdict(plan) for plan in plans],
        "results": [asdict(result) for result in results],
    }


def main() -> None:
    """Print the repeated-block audio smoke test."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
