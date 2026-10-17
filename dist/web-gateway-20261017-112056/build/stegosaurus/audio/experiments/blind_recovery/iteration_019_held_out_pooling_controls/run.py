"""Run iteration 019: held-out controls for pooled block recovery.

Goal: repeat the V3 pooling gate away from the single fixed fixture used by
iteration 018. The experiment varies the synthetic cover seeds, applies clean
and bounded crop fixtures, and checks that pooled evidence still separates
watermarked audio from unwatermarked and wrong-secret controls.

Toy flow:
    held-out repeated song -> optional edge crop -> pilot-ranked windows
        -> pool top windows -> compare watermarked, unwatermarked, wrong secret

This remains a synthetic release-gate experiment. It supports V3 planning for
block-distress handling and does not claim arbitrary crop length, codec, or
recorded-audio robustness.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from time import perf_counter

import numpy as np

from ....pilot import PcmAudio
from ...transport_optimization.iteration_006_duration_stability_bounds.run import _cover_variant, _trial_offset_seconds
from ..iteration_012_window_prefilter_smoke.run import _encoder, _pilot_window_score, _window
from ..iteration_018_pooling_control_gate.run import _evidence_for_scores, _pool_records, _wrong_encoder
from ..iteration_012_window_prefilter_smoke.run import WindowScore


@dataclass(frozen=True, slots=True)
class CropFixture:
    """Declare one received-song edge crop for held-out validation."""

    name: str
    leading_seconds: float
    trailing_seconds: float


@dataclass(frozen=True, slots=True)
class ControlOutcome:
    """Record one expected pooled recovery result."""

    trial_index: int
    fixture_name: str
    control_name: str
    expected_recovered: bool
    pooled_recovered: bool
    pooled_rs_cost: int
    exact_starts: int
    token_returning_blocks: int
    elapsed_ms: float
    gate_passed: bool


@dataclass(frozen=True, slots=True)
class TrialSummary:
    """Summarize one held-out synthetic song across all fixtures."""

    trial_index: int
    controls: int
    passed_controls: int
    maximum_watermarked_rs_cost: int
    minimum_negative_rs_cost: int


@dataclass(frozen=True, slots=True)
class TrialContext:
    """Hold one reusable held-out song and its attribution plan."""

    handle: bytes
    encoder: object
    embeddings: tuple[object, ...]
    watermarked_song: PcmAudio
    source_song: PcmAudio


def _held_out_covers(trial_index: int, block_count: int) -> tuple[PcmAudio, ...]:
    """Create deterministic but separately seeded cover blocks."""

    return tuple(
        _cover_variant(30, 9100 + trial_index * 100 + index, _trial_offset_seconds(2300 + trial_index * 100 + index))
        for index in range(block_count)
    )


def _held_out_song(trial_index: int, block_count: int = 5) -> TrialContext:
    """Build one held-out source and watermarked repeated-block song."""

    handle, _, encoder = _encoder()
    covers = _held_out_covers(trial_index, block_count)
    embeddings = tuple(encoder.embed(cover, handle) for cover in covers)
    watermarked = PcmAudio(np.asarray(np.concatenate([embedding.audio.samples for embedding in embeddings]), dtype=np.float64), covers[0].sample_rate)
    source = PcmAudio(np.asarray(np.concatenate([cover.samples for cover in covers]), dtype=np.float64), covers[0].sample_rate)
    return TrialContext(handle, encoder, embeddings, watermarked, source)


def _fixtures() -> tuple[CropFixture, ...]:
    """Return the default received-song fixtures for the release gate."""

    return (
        CropFixture("clean", 0.0, 0.0),
        CropFixture("dual_15s_crop", 15.0, 15.0),
    )


def _crop(audio: PcmAudio, fixture: CropFixture) -> PcmAudio:
    """Apply one edge crop while preserving sample rate metadata."""

    lead = int(round(fixture.leading_seconds * audio.sample_rate))
    trail = int(round(fixture.trailing_seconds * audio.sample_rate))
    end = len(audio.samples) - trail if trail else len(audio.samples)
    if lead >= end:
        raise ValueError("crop fixture removes the entire song")
    return PcmAudio(np.asarray(audio.samples[lead:end], dtype=np.float64), audio.sample_rate)


def _rank_fixture(
    song: PcmAudio,
    encoder: object,
    embedding: object,
    fixture: CropFixture,
    top_window_count: int,
) -> tuple[WindowScore, ...]:
    """Rank candidate windows for a cropped fixture."""

    block_length = len(embedding.audio.samples)
    leading = int(round(fixture.leading_seconds * song.sample_rate))
    exact_starts = {index * block_length - leading for index in range(5)}
    stride = block_length // 2
    scores = tuple(
        WindowScore(
            start / song.sample_rate,
            _pilot_window_score(encoder, _window(song, start, block_length), embedding.carrier_plan),
            start in exact_starts,
        )
        for start in range(0, len(song.samples) - block_length + 1, stride)
    )
    return tuple(sorted(scores, key=lambda score: score.pilot_score, reverse=True)[:top_window_count])


def _control(
    trial_index: int,
    fixture: CropFixture,
    name: str,
    expected: bool,
    pool: object,
    elapsed_ms: float,
) -> ControlOutcome:
    """Convert one pooled scenario into a release-gate outcome."""

    recovered = bool(pool.pooled_recovered and pool.pooled_rs_cost <= 16)
    return ControlOutcome(
        trial_index,
        fixture.name,
        name,
        expected,
        recovered,
        pool.pooled_rs_cost,
        pool.exact_starts,
        pool.blocks_returning_token,
        elapsed_ms,
        recovered is expected,
    )


def _run_fixture(trial_index: int, context: TrialContext, fixture: CropFixture) -> tuple[ControlOutcome, ...]:
    """Run watermarked, overlap, unwatermarked, and wrong-secret controls."""

    watermarked = _crop(context.watermarked_song, fixture)
    source = _crop(context.source_song, fixture)
    ranked = _rank_fixture(watermarked, context.encoder, context.embeddings[0], fixture, 5)
    block_length = len(context.embeddings[0].audio.samples)
    started = perf_counter()
    watermarked_records = _evidence_for_scores(watermarked, context.encoder, context.embeddings[0].carrier_plan, context.handle, ranked, block_length)
    unwatermarked_records = _evidence_for_scores(source, context.encoder, context.embeddings[0].carrier_plan, context.handle, ranked, block_length)
    wrong_encoder = _wrong_encoder()
    wrong_plan = wrong_encoder._pilot.schema.plan_attribution(context.handle)
    wrong_records = _evidence_for_scores(watermarked, wrong_encoder, wrong_plan, context.handle, ranked, block_length)
    pools = (
        _pool_records("watermarked_top5", watermarked_records, context.encoder, context.embeddings[0].carrier_plan, context.handle),
        _pool_records("unwatermarked_top5", unwatermarked_records, context.encoder, context.embeddings[0].carrier_plan, context.handle),
        _pool_records("wrong_secret_top5", wrong_records, wrong_encoder, wrong_plan, context.handle),
    )
    elapsed = (perf_counter() - started) * 1000.0
    return (
        _control(trial_index, fixture, "watermarked_top5", True, pools[0], elapsed),
        _control(trial_index, fixture, "unwatermarked_top5", False, pools[1], elapsed),
        _control(trial_index, fixture, "wrong_secret_top5", False, pools[2], elapsed),
    )


def _summarize(trial_index: int, controls: tuple[ControlOutcome, ...]) -> TrialSummary:
    """Summarize gate outcomes for one held-out trial."""

    watermarked_costs = tuple(control.pooled_rs_cost for control in controls if control.expected_recovered)
    negative_costs = tuple(control.pooled_rs_cost for control in controls if not control.expected_recovered)
    return TrialSummary(
        trial_index,
        len(controls),
        sum(control.gate_passed for control in controls),
        max(watermarked_costs),
        min(negative_costs),
    )


def run(trial_count: int = 1) -> dict[str, object]:
    """Run held-out pooling controls for clean and bounded-crop fixtures."""

    all_controls: list[ControlOutcome] = []
    for trial_index in range(trial_count):
        context = _held_out_song(trial_index)
        for fixture in _fixtures():
            all_controls.extend(_run_fixture(trial_index, context, fixture))
    controls = tuple(all_controls)
    summaries = tuple(_summarize(index, tuple(control for control in controls if control.trial_index == index)) for index in range(trial_count))
    return {
        "goal": "validate V3 pooling controls on held-out synthetic songs and bounded crops",
        "trial_count": trial_count,
        "fixtures": [asdict(fixture) for fixture in _fixtures()],
        "controls_passed": all(control.gate_passed for control in controls),
        "summaries": [asdict(summary) for summary in summaries],
        "controls": [asdict(control) for control in controls],
        "recommendation": "keep pooling in the V3 core only with control gates; keep arbitrary crop recovery experimental",
    }


def main() -> None:
    """Print the held-out pooling control experiment."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
