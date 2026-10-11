"""Run iteration 027: audit sample WAV capacity for producer workflow.

Goal: measure whether the current repeated-block attribution process can embed
into real tracks from the local ``samples`` folder without asking a music
producer to hunt for excerpts or change arrangement. The primary result is raw
sequential 30-second block capacity. A whole-song peak-normalized retry is
reported only as a diagnostic because a global gain pass is less invasive than
editing per-block levels.

Toy flow:
    samples/*.wav -> split into complete 30s blocks
        -> try product BlockAttributionCodec per block
        -> summarize raw capacity and whole-song level-normalized capacity

This measures embedding capacity only. It does not test distortion recovery,
recorded audio, or arbitrary crop robustness.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path

import numpy as np

from ....attacks import normalize_peak
from ....attribution import BlockAttributionCodec
from ....attribution_core.repetition import AttributionCapacityError
from ....pilot import PcmAudio, read_pcm16_wav


SAMPLES_DIR = Path("samples")
BLOCK_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class BlockCapacity:
    """Record whether one complete block can be embedded."""

    block_index: int
    start_seconds: float
    raw_capacity: bool
    raw_snr_db: float | None
    normalized_song_capacity: bool
    normalized_song_snr_db: float | None
    error: str | None


@dataclass(frozen=True, slots=True)
class SampleCapacity:
    """Summarize producer-facing attribution capacity for one sample file."""

    file_name: str
    sample_rate: int | None
    duration_seconds: float | None
    complete_blocks: int
    raw_capacity_blocks: int
    normalized_song_capacity_blocks: int
    raw_whole_song_embeddable: bool
    normalized_song_embeddable: bool
    median_raw_snr_db: float | None
    minimum_raw_snr_db: float | None
    workflow_status: str
    error: str | None


def _block(audio: PcmAudio, block_index: int, block_sample_count: int) -> PcmAudio:
    """Return one complete 30-second block."""

    start = block_index * block_sample_count
    return PcmAudio(np.asarray(audio.samples[start : start + block_sample_count], dtype=np.float64), audio.sample_rate)


def _try_embed(codec: BlockAttributionCodec, audio: PcmAudio, handle: bytes) -> tuple[bool, float | None, str | None]:
    """Try to embed one block and return capacity, SNR, and concise failure."""

    try:
        embedding = codec.embed(audio, handle, block_seconds=audio.duration_seconds)
    except AttributionCapacityError as error:
        return False, None, type(error).__name__
    except ValueError as error:
        return False, None, str(error)
    return True, embedding.block_signal_to_noise_db[0], None


def _audit_file(path: Path, codec: BlockAttributionCodec, handle: bytes) -> tuple[SampleCapacity, tuple[BlockCapacity, ...]]:
    """Audit one WAV file by complete 30-second blocks."""

    try:
        audio = read_pcm16_wav(path)
    except Exception as error:
        return (
            SampleCapacity(path.name, None, None, 0, 0, 0, False, False, None, None, "unreadable", f"{type(error).__name__}: {error}"),
            (),
        )
    block_sample_count = int(round(BLOCK_SECONDS * audio.sample_rate))
    complete_blocks = len(audio.samples) // block_sample_count
    normalized_audio = normalize_peak(audio, 0.90)
    records: list[BlockCapacity] = []
    for index in range(complete_blocks):
        block = _block(audio, index, block_sample_count)
        raw_ok, raw_snr, raw_error = _try_embed(codec, block, handle)
        normalized = _block(normalized_audio, index, block_sample_count)
        normalized_ok, normalized_snr, normalized_error = _try_embed(codec, normalized, handle)
        records.append(
            BlockCapacity(
                index,
                index * BLOCK_SECONDS,
                raw_ok,
                raw_snr,
                normalized_ok,
                normalized_snr,
                None if raw_ok else raw_error or normalized_error,
            )
        )
    raw_snrs = tuple(record.raw_snr_db for record in records if record.raw_snr_db is not None)
    raw_ok_count = sum(record.raw_capacity for record in records)
    normalized_ok_count = sum(record.normalized_song_capacity for record in records)
    summary = SampleCapacity(
        path.name,
        audio.sample_rate,
        audio.duration_seconds,
        complete_blocks,
        raw_ok_count,
        normalized_ok_count,
        complete_blocks > 0 and raw_ok_count == complete_blocks,
        complete_blocks > 0 and normalized_ok_count == complete_blocks,
        float(np.median(raw_snrs)) if raw_snrs else None,
        min(raw_snrs) if raw_snrs else None,
        _workflow_status(complete_blocks, raw_ok_count, normalized_ok_count),
        None,
    )
    return summary, tuple(records)


def _workflow_status(complete_blocks: int, raw_ok_count: int, normalized_ok_count: int) -> str:
    """Classify capacity from a producer workflow perspective."""

    if complete_blocks == 0:
        return "too_short"
    if raw_ok_count == complete_blocks:
        return "producer_ready_raw"
    if normalized_ok_count == complete_blocks:
        return "requires_whole_song_level_preprocessing"
    if raw_ok_count:
        return "partial_song_only"
    return "not_embeddable_current_profile"


def run(samples_dir: Path = SAMPLES_DIR) -> dict[str, object]:
    """Run the sample capacity audit."""

    codec = BlockAttributionCodec(b"sample-capacity-audit-secret")
    handle = bytes.fromhex("A1B2C3D4")
    paths = tuple(sorted(samples_dir.glob("*.wav")))
    audits = tuple(_audit_file(path, codec, handle) for path in paths)
    summaries = tuple(audit[0] for audit in audits)
    blocks = {summary.file_name: [asdict(record) for record in records] for summary, records in audits}
    return {
        "goal": "measure whether sample WAVs can be watermarked without producer-hostile preprocessing",
        "samples_dir": str(samples_dir),
        "block_seconds": BLOCK_SECONDS,
        "summary": {
            "files": len(summaries),
            "producer_ready_raw": sum(summary.workflow_status == "producer_ready_raw" for summary in summaries),
            "requires_whole_song_level_preprocessing": sum(summary.workflow_status == "requires_whole_song_level_preprocessing" for summary in summaries),
            "partial_song_only": sum(summary.workflow_status == "partial_song_only" for summary in summaries),
            "not_embeddable_current_profile": sum(summary.workflow_status == "not_embeddable_current_profile" for summary in summaries),
        },
        "samples": [asdict(summary) for summary in summaries],
        "blocks": blocks,
    }


def main() -> None:
    """Print the sample capacity audit."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
