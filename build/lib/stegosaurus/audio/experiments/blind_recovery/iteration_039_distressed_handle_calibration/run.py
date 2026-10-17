"""Run iteration 039: distressed handle calibration.

This experiment searches deterministic handle families for the remaining
light-recorded-proxy failure from iteration 038. Each trial registers a parent,
child, sibling, and unrelated export. The child export is cropped and distorted,
then verified with the current strict deep-phase recovery path.

Passing requires the child to be the unique accepted claim. A useful near miss
requires the child to rank first with a positive RS-cost gap over the next
registry record.
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
from .models import HandleTrial


OUTPUT_PATH = Path(__file__).with_name("results.json")


def _handle(value: int) -> bytes:
    """Return a four-byte handle from an integer value."""

    return value.to_bytes(4, "big")


def _light_proxy(audio: PcmAudio) -> PcmAudio:
    """Apply the named light recorded-proxy distress profile."""

    transformed = resample_audio(resample_audio(audio, 12000), audio.sample_rate)
    transformed = low_pass_filter(transformed, 3800.0)
    transformed = add_reverberation(transformed, 0.080, 0.10, seed=20261011)
    transformed = add_white_noise(transformed, 35.0, seed=20261011)
    return normalize_peak(transformed, 0.85)


def _crop(audio: PcmAudio, start_seconds: float = 37.25, duration_seconds: float = 90.0) -> PcmAudio:
    """Return one copied suspicious excerpt."""

    start = int(round(start_seconds * audio.sample_rate))
    count = int(round(duration_seconds * audio.sample_rate))
    return PcmAudio(np.array(audio.samples[start : start + count], copy=True), audio.sample_rate)


def _trial(source: PcmAudio, trial_index: int) -> HandleTrial:
    """Run one handle-family trial against the current fallback workflow."""

    base = 0xD0000000 + trial_index * 0x00010000
    workflow = KnownSongAttributionWorkflow(b"distressed-handle-calibration")
    song = workflow.register_song("calibration source", source)
    parent, _ = workflow.create_export(song.song_id, "parent", _handle(base + 0x101))
    child, child_audio = workflow.create_child_export(song.song_id, "child", _handle(base + 0xA53), parent.export_id)
    sibling, _ = workflow.create_child_export(song.song_id, "sibling", _handle(base + 0x5AC), parent.export_id)
    unrelated, _ = workflow.create_export(song.song_id, "unrelated", _handle(base + 0xF0F))
    verification = workflow.verify_excerpt_with_fallbacks(song.song_id, _light_proxy(_crop(child_audio)))
    ranked = verification.ranked_exports
    best = ranked[0]
    second = ranked[1]
    accepted = tuple(result for result in ranked if result.accepted)
    unique_child = len(accepted) == 1 and accepted[0].recipient_label == "child"
    status = (
        "unique_child_recovered"
        if unique_child
        else "child_separated_near_miss"
        if best.recipient_label == "child" and best.pooled_rs_cost < second.pooled_rs_cost
        else "ambiguous_child_evidence"
        if best.recipient_label == "child"
        else "wrong_record_ranked_first"
    )
    return HandleTrial(
        trial_index,
        parent.handle.hex(),
        child.handle.hex(),
        sibling.handle.hex(),
        unrelated.handle.hex(),
        best.recipient_label,
        best.pooled_rs_cost,
        second.recipient_label,
        second.pooled_rs_cost,
        second.pooled_rs_cost - best.pooled_rs_cost,
        unique_child,
        status,
    )


def run(trial_count: int = 2) -> dict[str, object]:
    """Run deterministic handle-family calibration trials."""

    source = music_like_sample(150)
    trials = tuple(_trial(source, index) for index in range(trial_count))
    manifest = {
        "goal": "test whether handle issuance can screen for distressed crop separability",
        "trial_count": trial_count,
        "trials": [asdict(trial) for trial in trials],
        "unique_child_recoveries": sum(trial.accepted_unique_child for trial in trials),
        "child_first_trials": sum(trial.best_label == "child" for trial in trials),
        "maximum_child_gap": max((trial.rs_gap for trial in trials if trial.best_label == "child"), default=0),
        "recommendation": _recommendation(trials),
    }
    OUTPUT_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def _recommendation(trials: tuple[HandleTrial, ...]) -> str:
    """Return the handle-calibration recommendation."""

    if any(trial.accepted_unique_child for trial in trials):
        return "promote calibrated handle issuance for distressed exports"
    if any(trial.status == "child_separated_near_miss" for trial in trials):
        return "add margin-aware near-miss policy before accepting distressed exports"
    return "handle choice alone did not separate the light recorded-proxy failure"


def main() -> None:
    """Print the handle-calibration manifest."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

