"""Run iteration 021: stress the current waterfall with attack families.

Goal: test whether the V3 waterfall shape has a plausible launching point for
arbitrary off-grid crops, codec round trips, and recorded-audio-like processing.
The experiment keeps the same core order: pilot window ranking, independent
block evidence, then cross-block pooling.

Toy flow:
    held-out watermarked song -> named attack -> rank windows -> pool top five
        -> compare watermarked, unwatermarked, and wrong-secret controls

These attacks are proxies with named parameters. The results guide what to
implement next; they do not claim broad codec or recorded-audio robustness.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from time import perf_counter
from typing import Callable

import numpy as np

from ....attack_core.codec import AudioToolUnavailable
from ....attacks import add_reverberation, add_white_noise, low_pass_filter, mp3_round_trip, normalize_peak, resample_audio, trim_audio
from ....pilot import PcmAudio
from ..iteration_018_pooling_control_gate.run import _evidence_for_scores, _pool_records, _wrong_encoder
from ..iteration_019_held_out_pooling_controls.run import TrialContext, _held_out_song, _rank_fixture, CropFixture


@dataclass(frozen=True, slots=True)
class AttackScenario:
    """Declare one robustness stressor and its expected release family."""

    name: str
    family: str
    description: str
    transform: Callable[[PcmAudio], PcmAudio]


@dataclass(frozen=True, slots=True)
class AttackControl:
    """Record one control result under an attack scenario."""

    scenario_name: str
    family: str
    control_name: str
    expected_recovered: bool
    pooled_recovered: bool
    pooled_rs_cost: int | None
    exact_starts: int
    token_returning_blocks: int
    elapsed_ms: float
    gate_passed: bool
    skipped_reason: str | None


@dataclass(frozen=True, slots=True)
class ScenarioSummary:
    """Summarize controls for one attack scenario."""

    scenario_name: str
    family: str
    controls: int
    passed_controls: int
    watermarked_recovered: bool
    minimum_negative_rs_cost: int | None
    status: str


def _scenarios() -> tuple[AttackScenario, ...]:
    """Return the first robustness matrix for arbitrary crop, codec, and recording proxies."""

    return (
        AttackScenario(
            "off_grid_dual_crop_7p3_11p7",
            "arbitrary_crop",
            "crop 7.3 seconds from the front and 11.7 seconds from the tail",
            lambda audio: trim_audio(audio, 7.3, audio.duration_seconds - 11.7),
        ),
        AttackScenario(
            "mp3_96k_round_trip",
            "codec",
            "encode and decode with the existing deterministic 96 kbps MP3 round trip",
            lambda audio: mp3_round_trip(audio, 96),
        ),
        AttackScenario(
            "recorded_audio_proxy_light",
            "recorded_audio_proxy",
            "resample, low-pass, add light room response, add 35 dB noise, and normalize",
            _recorded_audio_proxy,
        ),
    )


def _recorded_audio_proxy(audio: PcmAudio) -> PcmAudio:
    """Apply a deterministic light proxy for speaker-microphone degradation."""

    transformed = resample_audio(resample_audio(audio, 12000), audio.sample_rate)
    transformed = low_pass_filter(transformed, 3800.0)
    transformed = add_reverberation(transformed, 0.080, 0.10, seed=20261010)
    transformed = add_white_noise(transformed, 35.0, seed=20261010)
    return normalize_peak(transformed, 0.85)


def _skip_controls(scenario: AttackScenario, reason: str) -> tuple[AttackControl, ...]:
    """Return skipped control rows when an optional attack tool is unavailable."""

    return tuple(
        AttackControl(scenario.name, scenario.family, name, expected, False, None, 0, 0, 0.0, False, reason)
        for name, expected in (
            ("watermarked_top5", True),
            ("unwatermarked_top5", False),
            ("wrong_secret_top5", False),
        )
    )


def _control(
    scenario: AttackScenario,
    name: str,
    expected: bool,
    pool: object,
    elapsed_ms: float,
) -> AttackControl:
    """Convert one pooled result into an attack-control outcome."""

    recovered = bool(pool.pooled_recovered and pool.pooled_rs_cost <= 16)
    return AttackControl(
        scenario.name,
        scenario.family,
        name,
        expected,
        recovered,
        pool.pooled_rs_cost,
        pool.exact_starts,
        pool.blocks_returning_token,
        elapsed_ms,
        recovered is expected,
        None,
    )


def _run_scenario(context: TrialContext, scenario: AttackScenario) -> tuple[AttackControl, ...]:
    """Run one attack scenario through top-five pooling controls."""

    try:
        watermarked = scenario.transform(context.watermarked_song)
        source = scenario.transform(context.source_song)
    except AudioToolUnavailable as error:
        return _skip_controls(scenario, str(error))
    ranked = _rank_fixture(watermarked, context.encoder, context.embeddings[0], CropFixture("attacked", 0.0, 0.0), 5)
    block_length = len(context.embeddings[0].audio.samples)
    started = perf_counter()
    watermarked_records = _evidence_for_scores(watermarked, context.encoder, context.embeddings[0].carrier_plan, context.handle, ranked, block_length)
    unwatermarked_records = _evidence_for_scores(source, context.encoder, context.embeddings[0].carrier_plan, context.handle, ranked, block_length)
    wrong_encoder = _wrong_encoder()
    wrong_plan = wrong_encoder._pilot.schema.plan_attribution(context.handle)
    wrong_records = _evidence_for_scores(watermarked, wrong_encoder, wrong_plan, context.handle, ranked, block_length)
    elapsed_ms = (perf_counter() - started) * 1000.0
    pools = (
        _pool_records("watermarked_top5", watermarked_records, context.encoder, context.embeddings[0].carrier_plan, context.handle),
        _pool_records("unwatermarked_top5", unwatermarked_records, context.encoder, context.embeddings[0].carrier_plan, context.handle),
        _pool_records("wrong_secret_top5", wrong_records, wrong_encoder, wrong_plan, context.handle),
    )
    return (
        _control(scenario, "watermarked_top5", True, pools[0], elapsed_ms),
        _control(scenario, "unwatermarked_top5", False, pools[1], elapsed_ms),
        _control(scenario, "wrong_secret_top5", False, pools[2], elapsed_ms),
    )


def _summarize(scenario: AttackScenario, controls: tuple[AttackControl, ...]) -> ScenarioSummary:
    """Summarize one scenario in release-planning terms."""

    if any(control.skipped_reason for control in controls):
        return ScenarioSummary(scenario.name, scenario.family, len(controls), 0, False, None, "tool_unavailable")
    watermarked = next(control for control in controls if control.expected_recovered)
    negative_costs = tuple(control.pooled_rs_cost for control in controls if not control.expected_recovered and control.pooled_rs_cost is not None)
    if watermarked.gate_passed and all(control.gate_passed for control in controls):
        status = "candidate_launching_point"
    elif watermarked.pooled_recovered:
        status = "unsafe_negative_control"
    else:
        status = "unworkable_without_new_recovery_stage"
    return ScenarioSummary(
        scenario.name,
        scenario.family,
        len(controls),
        sum(control.gate_passed for control in controls),
        watermarked.pooled_recovered,
        min(negative_costs) if negative_costs else None,
        status,
    )


def run() -> dict[str, object]:
    """Run the attack robustness matrix against one held-out fixture."""

    context = _held_out_song(0)
    controls: list[AttackControl] = []
    for scenario in _scenarios():
        controls.extend(_run_scenario(context, scenario))
    control_rows = tuple(controls)
    summaries = tuple(
        _summarize(scenario, tuple(control for control in control_rows if control.scenario_name == scenario.name))
        for scenario in _scenarios()
    )
    return {
        "goal": "find launch points or blockers for arbitrary crop, codec, and recorded-audio robustness",
        "controls_passed": all(control.gate_passed for control in control_rows if control.skipped_reason is None),
        "summaries": [asdict(summary) for summary in summaries],
        "controls": [asdict(control) for control in control_rows],
        "recommendation": _recommendation(summaries),
    }


def _recommendation(summaries: tuple[ScenarioSummary, ...]) -> str:
    """Return a concise implementation recommendation from scenario statuses."""

    candidates = tuple(summary.family for summary in summaries if summary.status == "candidate_launching_point")
    blockers = tuple(summary.family for summary in summaries if summary.status == "unworkable_without_new_recovery_stage")
    if candidates and blockers:
        return f"implement candidates first: {', '.join(candidates)}; keep blocked families experimental: {', '.join(blockers)}"
    if candidates:
        return f"implementation launch point exists for: {', '.join(candidates)}"
    return "no attacked family has a safe implementation launching point with the current waterfall"


def main() -> None:
    """Print the attack robustness matrix."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
