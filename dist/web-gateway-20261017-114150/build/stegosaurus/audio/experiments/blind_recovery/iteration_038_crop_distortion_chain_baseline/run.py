"""Run iteration 038: crop-plus-distortion chain baseline.

This suite measures the current product path against the combined condition the
next hardening work must handle:

    registry-only parent/child exports + arbitrary crop + synthetic distress

The test matrix uses one parent, two children, and one unrelated export record.
Each visible audio file contains only one active watermark because child exports
are generated from the clean master. The verifier must therefore recover the
visible event without accepting its parent or sibling.
"""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

import numpy as np

from ....attacks import add_reverberation, add_white_noise, low_pass_filter, normalize_peak, resample_audio
from ....attribution_workflow import KnownSongAttributionWorkflow
from ....demo_samples import music_like_sample
from ....pilot import PcmAudio
from .models import ScenarioResult


OUTPUT_PATH = Path(__file__).with_name("results.json")
TARGET_FILE = "music_like_sample_150s"


def _handle(index: int) -> bytes:
    """Return one deterministic export handle."""

    return (0xC1000000 + index).to_bytes(4, "big")


def _crop(audio: PcmAudio, start_seconds: float, duration_seconds: float) -> PcmAudio:
    """Return one copied suspicious excerpt."""

    start = int(round(start_seconds * audio.sample_rate))
    count = int(round(duration_seconds * audio.sample_rate))
    return PcmAudio(np.array(audio.samples[start : start + count], copy=True), audio.sample_rate)


def _distress(audio: PcmAudio, name: str) -> PcmAudio:
    """Apply one named deterministic distress profile."""

    if name == "clean":
        return audio
    if name == "peak_normalized":
        return normalize_peak(audio, 0.85)
    if name == "light_recorded_proxy":
        transformed = resample_audio(resample_audio(audio, 12000), audio.sample_rate)
        transformed = low_pass_filter(transformed, 3800.0)
        transformed = add_reverberation(transformed, 0.080, 0.10, seed=20261011)
        transformed = add_white_noise(transformed, 35.0, seed=20261011)
        return normalize_peak(transformed, 0.85)
    if name == "moderate_recorded_proxy":
        transformed = resample_audio(resample_audio(audio, 9000), audio.sample_rate)
        transformed = low_pass_filter(transformed, 3000.0)
        transformed = add_reverberation(transformed, 0.120, 0.18, seed=20261011)
        transformed = add_white_noise(transformed, 28.0, seed=20261011)
        return normalize_peak(transformed, 0.85)
    raise ValueError(f"unsupported distress profile: {name}")


def _status(result: ScenarioResult) -> str:
    """Classify one workflow result."""

    if result.matched_expected and result.false_accept_count == 0:
        return "pass"
    if result.false_accept_count > 0:
        return "ambiguous_or_false_accept"
    if result.correct_rank == 1:
        return "decode_failure_after_localization"
    if result.correct_rank is not None:
        return "ranking_degraded"
    return "not_found"


def run() -> dict[str, object]:
    """Run the current crop-plus-distortion workflow baseline."""

    source = music_like_sample(150)
    workflow = KnownSongAttributionWorkflow(b"crop-distortion-chain-baseline")
    song = workflow.register_song(TARGET_FILE, source)
    parent, parent_audio = workflow.create_export(song.song_id, "parent", _handle(0))
    child_a, child_a_audio = workflow.create_child_export(song.song_id, "child_a", _handle(1), parent.export_id)
    child_b, _child_b_audio = workflow.create_child_export(song.song_id, "child_b", _handle(2), parent.export_id)
    workflow.create_export(song.song_id, "unrelated", _handle(99))
    visible = {
        "parent": parent_audio,
        "child_a": child_a_audio,
        "child_b": child_a_audio,
    }
    scenarios = (
        ("parent", "clean", 37.25, 90.0),
        ("child_a", "clean", 37.25, 90.0),
        ("child_a", "peak_normalized", 37.25, 90.0),
        ("child_a", "light_recorded_proxy", 37.25, 90.0),
    )
    results = []
    for label, distress, start, duration in scenarios:
        excerpt = _distress(_crop(visible[label], start, duration), distress)
        verification = workflow.verify_excerpt_with_fallbacks(song.song_id, excerpt)
        ranked = verification.ranked_exports
        correct = next((item for item in ranked if item.recipient_label == label), None)
        accepted = tuple(item for item in ranked if item.accepted)
        result = ScenarioResult(
            f"{label}_{distress}_{start:g}s_{duration:g}s",
            label,
            distress,
            start,
            duration,
            verification.accepted,
            verification.matched_recipient_label,
            verification.matched_recipient_label == label,
            sum(item.recipient_label != label for item in accepted),
            None if correct is None else correct.rank,
            None if correct is None else correct.pooled_rs_cost,
            None if not ranked else ranked[0].recipient_label,
            None if not ranked else ranked[0].pooled_rs_cost,
            tuple(candidate.registry_block_index for candidate in verification.candidates),
            "pending",
        )
        results.append(result.__class__(**{**asdict(result), "status": _status(result)}))
    manifest = {
        "goal": "measure parent-child visible watermark recovery under crop plus distress",
        "source_file": TARGET_FILE,
        "outcomes": [asdict(result) for result in results],
        "pass_count": sum(result.status == "pass" for result in results),
        "scenario_count": len(results),
        "recommendation": _recommendation(tuple(results)),
    }
    OUTPUT_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def _recommendation(results: tuple[ScenarioResult, ...]) -> str:
    """Return the next hardening recommendation."""

    failures = tuple(result for result in results if result.status != "pass")
    if not failures:
        return "baseline passes; promote combined crop-distortion tests to application coverage"
    localized = sum(result.status == "decode_failure_after_localization" for result in failures)
    ranking = sum(result.status == "ranking_degraded" for result in failures)
    return f"harden decode waterfall for {localized} localized failures and prefilter/ranking for {ranking} ranking failures"


def main() -> None:
    """Print the crop-plus-distortion baseline manifest."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

