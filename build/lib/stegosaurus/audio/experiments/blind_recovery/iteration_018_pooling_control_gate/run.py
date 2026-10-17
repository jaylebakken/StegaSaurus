"""Run iteration 018: control-test cross-block carrier pooling.

Goal: test the first V3 gate for promoting pooled block evidence. Iteration 015
showed that pooling recovers a clean repeated-block fixture; iteration 017 says
pooling must also reject wrong-secret and unwatermarked controls and remain
stable when non-block overlapping windows are included.

Toy flow:
    rank watermarked windows -> reuse starts for controls
        -> pool exact top-five, top-seven, unwatermarked, and wrong-secret

This is still a synthetic claimed-plan fixture. It validates one release gate;
it does not claim codec, recorded-audio, or arbitrary-crop robustness.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json

import numpy as np

from ....pilot import PcmAudio, SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioWatermarkConfig, CarrierPlan
from ...non_oracle_reconstruction.iteration_005_contrastive_pilot_calibration.run import ContrastivePilotCalibratedExperiment
from ...non_oracle_reconstruction.iteration_019_registry_handle_parity_tradeoff.run import _profile
from ..iteration_001_geometry_dependency_audit.run import GeometryAssumptionEdgeModeDecoder
from ..iteration_012_window_prefilter_smoke.run import WindowScore, _block_cover, _encoder, _window
from ..iteration_013_block_waterfall_controller.run import _rank_windows, _song
from ..iteration_015_cross_block_evidence_pooling.run import BlockEvidence, BlockSummary, PoolingResult, _combine_scores


@dataclass(frozen=True, slots=True)
class PoolingControlResult:
    """Record one pooling scenario and whether it satisfies the control gate."""

    name: str
    expected_recovered: bool
    pooled_recovered: bool
    pooled_rs_cost: int
    exact_starts: int
    token_returning_blocks: int
    gate_passed: bool


@dataclass(frozen=True, slots=True)
class _PlanContext:
    """Hold the carrier plan shape needed by the pooling helper."""

    carrier_plan: CarrierPlan


def _source_song(block_count: int = 5) -> PcmAudio:
    """Return the unwatermarked source song matching the watermarked fixture."""

    covers = tuple(_block_cover(index) for index in range(block_count))
    return PcmAudio(np.asarray(np.concatenate([cover.samples for cover in covers]), dtype=np.float64), covers[0].sample_rate)


def _wrong_encoder() -> ContrastivePilotCalibratedExperiment:
    """Return a same-profile encoder using the wrong carrier secret."""

    config = SpectralPilotConfig(minimum_frequency_hz=500.0, maximum_frequency_hz=3800.0, relative_difference=0.95)
    pilot = SpectralAudioPilot(b"wrong-audio-pilot-test-key", config, AudioWatermarkConfig(attribution_token_bytes=4, parity_symbols=16))
    return ContrastivePilotCalibratedExperiment(pilot, 0.01, _profile())


def _evidence_for_scores(
    audio: PcmAudio,
    encoder: object,
    carrier_plan: CarrierPlan,
    handle: bytes,
    scores: tuple[WindowScore, ...],
    block_length: int,
) -> tuple[BlockEvidence, ...]:
    """Collect reusable carrier evidence at already-ranked window starts."""

    records: list[BlockEvidence] = []
    for score in scores:
        start = int(round(score.start_seconds * audio.sample_rate))
        block = _window(audio, start, block_length)
        decoder = GeometryAssumptionEdgeModeDecoder(encoder, block.duration_seconds)
        decision = decoder.reconstruct(block, carrier_plan)
        hypothesis = decision.selected or decision.hypotheses[0]
        extraction = hypothesis.reconstruction.extraction
        recovery = extraction.recovery.channel_recovery
        rs_cost = None
        if extraction.recovery.token is not None:
            rs_cost = 2 * len(recovery.corrected_positions) + len(recovery.erasure_positions)
        records.append(
            BlockEvidence(
                score.start_seconds,
                score.is_exact_block_start,
                score.pilot_score,
                extraction.recovery.token == handle,
                extraction.known_bit_errors,
                extraction.carrier_erasures,
                rs_cost,
                extraction.combined_scores,
            )
        )
    return tuple(records)


def _pool_records(
    name: str,
    records: tuple[BlockEvidence, ...],
    encoder: object,
    carrier_plan: CarrierPlan,
    handle: bytes,
) -> PoolingResult:
    """Pool carrier scores from a control scenario."""

    carrier_count = len(carrier_plan.carrier_bits)
    pooled_scores = tuple(_combine_scores(tuple(record.combined_scores[index] for record in records)) for index in range(carrier_count))
    observed_bits = tuple(None if score is None or abs(score) < 0.01 else int(score >= 0) for score in pooled_scores)
    recovery = encoder._pilot.schema.recover_attribution(observed_bits)
    expected = encoder._pilot.schema._channel.inspect_carrier_bits(carrier_plan.carrier_bits, carrier_plan.payload_length)
    observed = encoder._pilot.schema._channel.inspect_carrier_bits(observed_bits, carrier_plan.payload_length)
    erasures = set(observed.erasure_positions)
    symbol_errors = sum(
        index not in erasures and expected.codeword[index] != observed.codeword[index]
        for index in range(len(expected.codeword))
    )
    symbol_erasures = len(erasures)
    return PoolingResult(
        name,
        len(records),
        sum(record.is_exact_block_start for record in records),
        sum(record.block_recovered for record in records),
        recovery.token == handle,
        sum(bit is not None and bit != target for target, bit in zip(carrier_plan.carrier_bits, observed_bits)),
        sum(bit is None for bit in observed_bits),
        symbol_errors,
        symbol_erasures,
        2 * symbol_errors + symbol_erasures,
    )


def _control(name: str, expected: bool, pool: PoolingResult) -> PoolingControlResult:
    """Convert a pooled result into a gate record."""

    recovered = pool.pooled_recovered and pool.pooled_rs_cost <= 16
    return PoolingControlResult(
        name,
        expected,
        recovered,
        pool.pooled_rs_cost,
        pool.exact_starts,
        pool.blocks_returning_token,
        recovered is expected,
    )


def run() -> dict[str, object]:
    """Run watermarked, unwatermarked, wrong-secret, and top-seven pooling controls."""

    handle, _, encoder, embeddings, song = _song()
    source = _source_song()
    ranked, _ = _rank_windows(song, encoder, embeddings[0], 7)
    block_length = len(embeddings[0].audio.samples)
    watermarked = _evidence_for_scores(song, encoder, embeddings[0].carrier_plan, handle, ranked, block_length)
    unwatermarked = _evidence_for_scores(source, encoder, embeddings[0].carrier_plan, handle, ranked, block_length)
    wrong_encoder = _wrong_encoder()
    wrong_plan = wrong_encoder._pilot.schema.plan_attribution(handle)
    wrong_secret = _evidence_for_scores(song, wrong_encoder, wrong_plan, handle, ranked, block_length)
    pools = (
        _pool_records("watermarked_top5", watermarked[:5], encoder, embeddings[0].carrier_plan, handle),
        _pool_records("watermarked_top7_with_overlaps", watermarked[:7], encoder, embeddings[0].carrier_plan, handle),
        _pool_records("unwatermarked_top5", unwatermarked[:5], encoder, embeddings[0].carrier_plan, handle),
        _pool_records("wrong_secret_top5", wrong_secret[:5], wrong_encoder, wrong_plan, handle),
    )
    controls = (
        _control("watermarked_top5", True, pools[0]),
        _control("watermarked_top7_with_overlaps", True, pools[1]),
        _control("unwatermarked_top5", False, pools[2]),
        _control("wrong_secret_top5", False, pools[3]),
    )
    return {
        "goal": "validate V3 cross-block pooling control gate",
        "controls_passed": all(control.gate_passed for control in controls),
        "controls": [asdict(control) for control in controls],
        "pools": [asdict(pool) for pool in pools],
        "watermarked_blocks": [
            asdict(BlockSummary(record.start_seconds, record.is_exact_block_start, record.pilot_score, record.block_recovered, record.known_bit_errors, record.carrier_erasures, record.rs_error_cost))
            for record in watermarked
        ],
    }


def main() -> None:
    """Print the pooling control-gate experiment."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

