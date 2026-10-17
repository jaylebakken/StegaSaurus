"""Run iteration 041: robust 15-second profile baseline.

The suite validates the candidate robust profile against the compact target
matrix:

    parent/child visibility + arbitrary crop + clean/normalized/proxy distress

The profile uses registry-only parent-child exports and 15-second repeated
blocks. The light recorded-proxy transform is a named synthetic profile, not a
claim about real microphones, rooms, codecs, or platforms.
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
from .models import RobustScenario


OUTPUT_PATH = Path(__file__).with_name("results.json")
BLOCK_SECONDS = 15.0


def _handle(index: int) -> bytes:
    """Return a deterministic four-byte export handle."""

    return (0xE3000000 + index).to_bytes(4, "big")


def _crop(audio: PcmAudio) -> PcmAudio:
    """Return the shared off-grid suspicious crop."""

    start = int(round(37.25 * audio.sample_rate))
    count = int(round(90.0 * audio.sample_rate))
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
    raise ValueError(f"unsupported distress profile: {name}")


def run() -> dict[str, object]:
    """Run the robust-profile baseline suite."""

    source = music_like_sample(150)
    workflow = KnownSongAttributionWorkflow(b"robust-profile-baseline")
    song = workflow.register_song("robust profile source", source, block_seconds=BLOCK_SECONDS)
    parent, parent_audio = workflow.create_export(song.song_id, "parent", _handle(0))
    workflow.create_child_export(song.song_id, "sibling", _handle(2), parent.export_id)
    workflow.create_export(song.song_id, "unrelated", _handle(99))
    child, child_audio = workflow.create_child_export(song.song_id, "child", _handle(1), parent.export_id)
    visible = {
        "parent": parent_audio,
        "child": child_audio,
    }
    scenarios = (
        ("parent_clean_crop", "parent", "clean"),
        ("parent_peak_normalized_crop", "parent", "peak_normalized"),
        ("parent_light_recorded_proxy_crop", "parent", "light_recorded_proxy"),
        ("child_clean_crop", "child", "clean"),
        ("child_peak_normalized_crop", "child", "peak_normalized"),
        ("child_light_recorded_proxy_crop", "child", "light_recorded_proxy"),
    )
    results = tuple(_scenario(workflow, song.song_id, visible[label], name, label, distress) for name, label, distress in scenarios)
    manifest = {
        "goal": "validate robust 15-second parent-child crop-distortion baseline",
        "block_seconds": BLOCK_SECONDS,
        "results": [asdict(result) for result in results],
        "pass_count": sum(result.status == "pass" for result in results),
        "scenario_count": len(results),
        "recommendation": _recommendation(results),
    }
    OUTPUT_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def _scenario(
    workflow: KnownSongAttributionWorkflow,
    song_id: str,
    audio: PcmAudio,
    scenario: str,
    expected_label: str,
    distress: str,
) -> RobustScenario:
    """Verify one robust-profile scenario."""

    verification = workflow.verify_excerpt_with_fallbacks(song_id, _distress(_crop(audio), distress))
    ranked = verification.ranked_exports
    accepted = tuple(result for result in ranked if result.accepted)
    false_accept_count = sum(result.recipient_label != expected_label for result in accepted)
    accepted_label = accepted[0].recipient_label if len(accepted) == 1 else None
    status = "pass" if accepted_label == expected_label and false_accept_count == 0 else "fail"
    return RobustScenario(
        scenario,
        expected_label,
        distress,
        accepted_label,
        ranked[0].recipient_label,
        ranked[0].pooled_rs_cost,
        false_accept_count,
        status,
    )


def _recommendation(results: tuple[RobustScenario, ...]) -> str:
    """Return the robust-profile recommendation."""

    if all(result.status == "pass" for result in results):
        return "promote 15s robust profile into the application workflow"
    return "keep hardening before productizing the robust profile"


def main() -> None:
    """Print the robust-profile baseline manifest."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

