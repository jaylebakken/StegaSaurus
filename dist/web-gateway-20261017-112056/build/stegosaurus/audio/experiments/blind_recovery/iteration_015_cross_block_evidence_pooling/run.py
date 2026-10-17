"""Run iteration 015: pool carrier evidence across repeated blocks.

Goal: test the next recovery tool after block-voting experiments showed that
high-pilot exact-looking block failures are not rescued by geometry fallback.
Because every repeated block carries the same handle, a verifier can combine
carrier evidence by carrier position before making one Reed--Solomon decision.

Toy flow:
    rank windows -> reconstruct each exact-looking block -> collect scores
        -> pool signed carrier evidence across top-K blocks -> RS recover once

The fixture remains synthetic and claimed-plan. This is a research bridge from
block voting to a v2 pooled decoder, not a claim of arbitrary blind recovery.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json

from ....pilot import PcmAudio
from ..iteration_001_geometry_dependency_audit.run import GeometryAssumptionEdgeModeDecoder
from ..iteration_012_window_prefilter_smoke.run import _window
from ..iteration_013_block_waterfall_controller.run import _rank_windows, _song


@dataclass(frozen=True, slots=True)
class BlockEvidence:
    """Record one ranked block's hard recovery and reusable carrier evidence."""

    start_seconds: float
    is_exact_block_start: bool
    pilot_score: float
    block_recovered: bool
    known_bit_errors: int
    carrier_erasures: int
    rs_error_cost: int | None
    combined_scores: tuple[float | None, ...]


@dataclass(frozen=True, slots=True)
class BlockSummary:
    """Record block evidence without serializing every carrier score."""

    start_seconds: float
    is_exact_block_start: bool
    pilot_score: float
    token_returned: bool
    known_bit_errors: int
    carrier_erasures: int
    rs_error_cost: int | None


@dataclass(frozen=True, slots=True)
class PoolingResult:
    """Record one top-K pooled Reed--Solomon decision."""

    name: str
    top_window_count: int
    exact_starts: int
    blocks_returning_token: int
    pooled_recovered: bool
    pooled_known_bit_errors: int
    pooled_carrier_erasures: int
    pooled_symbol_errors: int
    pooled_symbol_erasures: int
    pooled_rs_cost: int


def _block_evidence(song: PcmAudio, encoder: object, embedding: object, handle: bytes, top_count: int) -> tuple[BlockEvidence, ...]:
    """Recover ranked windows and retain carrier scores even when RS recovery fails."""

    ranked, _ = _rank_windows(song, encoder, embedding, top_count)
    block_length = len(embedding.audio.samples)
    records: list[BlockEvidence] = []
    for score in ranked:
        start = int(round(score.start_seconds * song.sample_rate))
        audio = _window(song, start, block_length)
        decoder = GeometryAssumptionEdgeModeDecoder(encoder, audio.duration_seconds)
        decision = decoder.reconstruct(audio, embedding.carrier_plan)
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


def _combine_scores(scores: tuple[float | None, ...]) -> float | None:
    """Combine repeated block scores with the existing absolute-score weighting rule."""

    available = tuple(score for score in scores if score is not None)
    total_weight = sum(abs(score) for score in available)
    if not total_weight:
        return None
    return sum(score * abs(score) for score in available) / total_weight


def _pool(records: tuple[BlockEvidence, ...], encoder: object, embedding: object, handle: bytes, name: str) -> PoolingResult:
    """Pool top-K carrier evidence and recover one shared attribution handle."""

    carrier_count = len(embedding.carrier_plan.carrier_bits)
    pooled_scores = tuple(
        _combine_scores(tuple(record.combined_scores[index] for record in records))
        for index in range(carrier_count)
    )
    observed_bits = tuple(None if score is None or abs(score) < 0.01 else int(score >= 0) for score in pooled_scores)
    recovery = encoder._pilot.schema.recover_attribution(observed_bits)
    expected = encoder._pilot.schema._channel.inspect_carrier_bits(
        embedding.carrier_plan.carrier_bits,
        embedding.carrier_plan.payload_length,
    )
    observed = encoder._pilot.schema._channel.inspect_carrier_bits(observed_bits, embedding.carrier_plan.payload_length)
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
        sum(bit is not None and bit != target for target, bit in zip(embedding.carrier_plan.carrier_bits, observed_bits)),
        sum(bit is None for bit in observed_bits),
        symbol_errors,
        symbol_erasures,
        2 * symbol_errors + symbol_erasures,
    )


def run() -> dict[str, object]:
    """Run cross-block pooling against top-three, top-five, and top-seven windows."""

    handle, _, encoder, embeddings, song = _song()
    records = _block_evidence(song, encoder, embeddings[0], handle, 7)
    pools = (
        _pool(records[:3], encoder, embeddings[0], handle, "top3_pool"),
        _pool(records[:5], encoder, embeddings[0], handle, "top5_pool"),
        _pool(records[:7], encoder, embeddings[0], handle, "top7_pool"),
    )
    return {
        "goal": "test cross-block carrier evidence pooling before RS recovery",
        "block_records": [
            asdict(
                BlockSummary(
                    record.start_seconds,
                    record.is_exact_block_start,
                    record.pilot_score,
                    record.block_recovered,
                    record.known_bit_errors,
                    record.carrier_erasures,
                    record.rs_error_cost,
                )
            )
            for record in records
        ],
        "pooling_results": [asdict(pool) for pool in pools],
        "recommendation": "promote pooled carrier evidence as the block-distress fallback before geometry search",
    }


def main() -> None:
    """Print the cross-block evidence pooling experiment."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

