"""Run iteration 040: distressed block-redundancy sweep.

This experiment checks whether shorter registry block profiles harden the
remaining light recorded-proxy crop case. Each profile uses a parent, visible
child, sibling, and unrelated export, all generated from the clean master.
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
from .models import BlockProfileResult


OUTPUT_PATH = Path(__file__).with_name("results.json")


def _handle(index: int) -> bytes:
    """Return a deterministic four-byte handle."""

    return (0xE1000000 + index).to_bytes(4, "big")


def _crop(audio: PcmAudio) -> PcmAudio:
    """Return the shared 90-second arbitrary crop."""

    start = int(round(37.25 * audio.sample_rate))
    count = int(round(90.0 * audio.sample_rate))
    return PcmAudio(np.array(audio.samples[start : start + count], copy=True), audio.sample_rate)


def _light_proxy(audio: PcmAudio) -> PcmAudio:
    """Apply the named light recorded-proxy distress profile."""

    transformed = resample_audio(resample_audio(audio, 12000), audio.sample_rate)
    transformed = low_pass_filter(transformed, 3800.0)
    transformed = add_reverberation(transformed, 0.080, 0.10, seed=20261011)
    transformed = add_white_noise(transformed, 35.0, seed=20261011)
    return normalize_peak(transformed, 0.85)


def _profile(source: PcmAudio, block_seconds: float) -> BlockProfileResult:
    """Run one block-duration profile."""

    workflow = KnownSongAttributionWorkflow(b"distressed-block-redundancy")
    song = workflow.register_song("block profile source", source, block_seconds=block_seconds)
    parent, _ = workflow.create_export(song.song_id, "parent", _handle(0))
    child, child_audio = workflow.create_child_export(song.song_id, "child", _handle(1), parent.export_id)
    workflow.create_child_export(song.song_id, "sibling", _handle(2), parent.export_id)
    workflow.create_export(song.song_id, "unrelated", _handle(99))
    verification = workflow.verify_excerpt_with_fallbacks(song.song_id, _light_proxy(_crop(child_audio)))
    ranked = verification.ranked_exports
    best = ranked[0]
    second = ranked[1]
    accepted = tuple(result for result in ranked if result.accepted)
    accepted_label = accepted[0].recipient_label if len(accepted) == 1 else None
    false_accepts = sum(result.recipient_label != "child" for result in accepted)
    status = (
        "pass"
        if accepted_label == "child" and false_accepts == 0
        else "child_near_miss"
        if best.recipient_label == "child"
        else "wrong_record_ranked_first"
    )
    return BlockProfileResult(
        block_seconds,
        best.recipient_label,
        best.pooled_rs_cost,
        second.recipient_label,
        second.pooled_rs_cost,
        accepted_label,
        false_accepts,
        status,
    )


def run() -> dict[str, object]:
    """Run the block-duration sweep."""

    source = music_like_sample(150)
    results = tuple(_profile(source, block_seconds) for block_seconds in (30.0, 15.0))
    manifest = {
        "goal": "test whether shorter blocks separate light proxy crop evidence",
        "results": [asdict(result) for result in results],
        "pass_count": sum(result.status == "pass" for result in results),
        "recommendation": _recommendation(results),
    }
    OUTPUT_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def _recommendation(results: tuple[BlockProfileResult, ...]) -> str:
    """Return the product-profile recommendation."""

    passing = tuple(result for result in results if result.status == "pass")
    if passing:
        best = min(passing, key=lambda result: result.block_seconds)
        return f"promote {best.block_seconds:g}s blocks for distressed crop profile validation"
    return "shorter blocks did not safely recover the light proxy crop in this sweep"


def main() -> None:
    """Print the block-redundancy manifest."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()

