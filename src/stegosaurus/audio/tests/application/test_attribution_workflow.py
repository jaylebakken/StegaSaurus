"""Test the V4 known-song attribution workflow.

These application checks cover the clean-file leak path promoted from the blind
recovery experiments: register a song, create recipient/export watermarked
copies, localize a clean suspicious excerpt, and identify the matching export.
They do not claim recorded-audio, codec, or unknown-song robustness.
"""

from __future__ import annotations

import numpy as np

from stegosaurus.audio.attribution_workflow import KnownSongAttributionWorkflow, build_song_fingerprint_index, localize_excerpt
from stegosaurus.audio.demo_samples import music_like_sample
from stegosaurus.audio.pilot import PcmAudio


def _crop(audio: PcmAudio, start_seconds: float, duration_seconds: float) -> PcmAudio:
    """Return one copied crop from a waveform."""

    start = int(round(start_seconds * audio.sample_rate))
    count = int(round(duration_seconds * audio.sample_rate))
    return PcmAudio(np.array(audio.samples[start : start + count], copy=True), audio.sample_rate)


def _handle(index: int) -> bytes:
    """Return a deterministic four-byte test handle."""

    return (0xB1000000 + index).to_bytes(4, "big")


def test_song_fingerprint_index_localizes_clean_excerpt() -> None:
    """Find useful source blocks in a clean off-grid excerpt."""

    source = music_like_sample(150)
    index = build_song_fingerprint_index(source)
    excerpt = _crop(source, 37.25, 90.0)

    candidates, elapsed_ms = localize_excerpt(excerpt, index, top_count=3)

    assert candidates
    assert elapsed_ms >= 0
    assert candidates[0].registry_block_index in {2, 3, 4}


def test_known_song_workflow_identifies_matching_clean_export() -> None:
    """Recover the leaked export from a clean suspicious excerpt."""

    workflow = KnownSongAttributionWorkflow(b"v4-workflow-application-test")
    song = workflow.register_song("application workflow song", music_like_sample(150))
    exports = tuple(workflow.create_export(song.song_id, f"export_{index:02d}", _handle(index)) for index in range(3))
    leaked_export, leaked_audio = exports[1]
    excerpt = _crop(leaked_audio, 37.25, 90.0)

    result = workflow.verify_excerpt(song.song_id, excerpt)

    assert result.accepted
    assert result.matched_export_id == leaked_export.export_id
    assert result.matched_recipient_label == leaked_export.recipient_label
    assert result.ranked_exports[0].export_id == leaked_export.export_id
    assert sum(export.accepted for export in result.ranked_exports) == 1


def test_registry_child_export_uses_one_visible_watermark() -> None:
    """Recover a child export without also accepting its registry parent."""

    workflow = KnownSongAttributionWorkflow(b"v4-registry-chain-application-test")
    song = workflow.register_song("registry chain song", music_like_sample(150))
    parent, _ = workflow.create_export(song.song_id, "parent", _handle(10))
    child, child_audio = workflow.create_child_export(song.song_id, "child", _handle(11), parent.export_id)
    excerpt = _crop(child_audio, 37.25, 90.0)

    result = workflow.verify_excerpt(song.song_id, excerpt)
    lineage = workflow.catalog.export_lineage(child.export_id)

    assert result.accepted
    assert result.matched_export_id == child.export_id
    assert sum(export.accepted for export in result.ranked_exports) == 1
    assert tuple(export.export_id for export in lineage) == (parent.export_id, child.export_id)
