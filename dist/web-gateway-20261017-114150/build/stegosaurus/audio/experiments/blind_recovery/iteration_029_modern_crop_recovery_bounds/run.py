"""Run iteration 029: modern-production arbitrary crop recovery bounds.

Goal: estimate whether dense pop and rap productions can support recovery from
unknown leading and trailing truncation. This first pass measures an oracle
geometry upper bound: after embedding the current repeated-block attribution
profile, it crops excerpts at multiple starts and lengths, then verifies the
complete original blocks that survive inside each excerpt.

Toy flow:
    modern samples -> embed repeated blocks -> crop excerpts
        -> keep complete original blocks inside crop -> pooled verification
        -> minimum recoverable excerpt duration by track

This is not yet a fully blind decoder. It answers whether enough attribution
evidence remains after truncation; a later phase-bank or pilot-localization
stage must learn how to find the same surviving blocks without oracle geometry.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path

import numpy as np

from ....attacks import normalize_peak
from ....attribution import BlockAttributionCodec
from ....attribution_core import BlockAttributionRecord
from ....attribution_core.repetition import AttributionCapacityError
from ....pilot import PcmAudio, read_pcm16_wav


SAMPLES_DIR = Path("samples")
OUTPUT_PATH = Path(__file__).with_name("results.json")
BLOCK_SECONDS = 30.0
MODERN_SAMPLE_NAMES = (
    "03. King of Sorrow.wav",
    "08. Gutta Bitch.wav",
    "10. Cry Me a River.wav",
    "10. Lovers Rock.wav",
    "19. Get Low.wav",
)
CROP_SECONDS = (15.0, 30.0, 45.0, 60.0, 90.0, 120.0)
CROP_START_FRACTIONS = (0.0, 0.20, 0.40, 0.60)


@dataclass(frozen=True, slots=True)
class CropTrial:
    """Record one truncated-excerpt recovery attempt."""

    crop_seconds: float
    start_seconds: float
    surviving_complete_blocks: int
    recovered: bool
    block_votes: int
    pooled_rs_cost: int
    status: str


@dataclass(frozen=True, slots=True)
class TrackCropSummary:
    """Summarize crop tolerance for one dense modern-production sample."""

    source_file: str
    duration_seconds: float
    preflight: str
    embedded_blocks: int
    minimum_recoverable_crop_seconds: float | None
    recoverable_trial_count: int
    total_trial_count: int
    notes: str


def _embed(codec: BlockAttributionCodec, audio: PcmAudio, handle: bytes) -> tuple[str, object]:
    """Embed raw audio, then retry one whole-song peak normalization if needed."""

    try:
        return "raw", codec.embed(audio, handle, block_seconds=BLOCK_SECONDS)
    except AttributionCapacityError:
        return "whole_song_peak_normalized", codec.embed(normalize_peak(audio, 0.90), handle, block_seconds=BLOCK_SECONDS)


def _crop(audio: PcmAudio, start_seconds: float, duration_seconds: float) -> PcmAudio:
    """Return one contiguous crop from a watermarked sample."""

    start_sample = int(round(start_seconds * audio.sample_rate))
    sample_count = int(round(duration_seconds * audio.sample_rate))
    return PcmAudio(np.array(audio.samples[start_sample : start_sample + sample_count], copy=True), audio.sample_rate)


def _surviving_record(record: BlockAttributionRecord, crop_start: int, crop_stop: int) -> tuple[BlockAttributionRecord | None, int]:
    """Return retained records for complete original blocks contained in a crop."""

    first_block = (crop_start + record.block_sample_count - 1) // record.block_sample_count
    last_block = crop_stop // record.block_sample_count - 1
    if last_block < first_block:
        return None, 0
    records = record.block_records[first_block : last_block + 1]
    return (
        BlockAttributionRecord(
            record.handle,
            record.block_sample_count,
            record.sample_rate,
            records,
            len(records) * record.block_sample_count,
        ),
        first_block * record.block_sample_count - crop_start,
    )


def _aligned_survivor_audio(crop: PcmAudio, offset_samples: int, record: BlockAttributionRecord) -> PcmAudio:
    """Return the complete surviving block range from inside the crop."""

    sample_count = len(record.block_records) * record.block_sample_count
    return PcmAudio(np.array(crop.samples[offset_samples : offset_samples + sample_count], copy=True), crop.sample_rate)


def _starts(audio: PcmAudio, crop_seconds: float) -> tuple[float, ...]:
    """Return deterministic crop starts spread across a track."""

    maximum_start = max(0.0, audio.duration_seconds - crop_seconds)
    return tuple(round(maximum_start * fraction, 3) for fraction in CROP_START_FRACTIONS)


def _trial(codec: BlockAttributionCodec, embedding: object, crop_seconds: float, start_seconds: float) -> CropTrial:
    """Run one oracle-surviving-block crop trial."""

    crop = _crop(embedding.audio, start_seconds, crop_seconds)
    crop_start = int(round(start_seconds * embedding.audio.sample_rate))
    crop_stop = crop_start + len(crop.samples)
    survivor_record, offset = _surviving_record(embedding.record, crop_start, crop_stop)
    if survivor_record is None:
        return CropTrial(crop_seconds, start_seconds, 0, False, 0, 32, "no_complete_original_blocks")
    survivor_audio = _aligned_survivor_audio(crop, offset, survivor_record)
    verification = codec.verify(survivor_audio, survivor_record)
    return CropTrial(
        crop_seconds,
        start_seconds,
        len(survivor_record.block_records),
        verification.recovered,
        verification.recovered_block_count,
        verification.pooled_verification.claim_rs_cost,
        "recovered" if verification.recovered else "not_recovered",
    )


def _audit_track(path: Path, codec: BlockAttributionCodec, handle: bytes) -> tuple[TrackCropSummary, tuple[CropTrial, ...]]:
    """Embed one modern sample and run the crop-duration grid."""

    audio = read_pcm16_wav(path)
    preflight, embedding = _embed(codec, audio, handle)
    trials = tuple(
        _trial(codec, embedding, crop_seconds, start_seconds)
        for crop_seconds in CROP_SECONDS
        if crop_seconds < embedding.audio.duration_seconds
        for start_seconds in _starts(embedding.audio, crop_seconds)
    )
    recovered_crop_lengths = tuple(trial.crop_seconds for trial in trials if trial.recovered)
    summary = TrackCropSummary(
        path.name,
        embedding.audio.duration_seconds,
        preflight,
        len(embedding.record.block_records),
        min(recovered_crop_lengths) if recovered_crop_lengths else None,
        sum(trial.recovered for trial in trials),
        len(trials),
        _notes(recovered_crop_lengths),
    )
    return summary, trials


def _notes(recovered_crop_lengths: tuple[float, ...]) -> str:
    """Name the practical interpretation of one crop tolerance result."""

    if not recovered_crop_lengths:
        return "current profile needs more surviving evidence or stronger search"
    if min(recovered_crop_lengths) <= 30.0:
        return "one complete surviving block can be enough under oracle geometry"
    return "recovery needs multiple surviving block opportunities"


def run(samples_dir: Path = SAMPLES_DIR) -> dict[str, object]:
    """Run the modern crop recovery bound suite and write JSON results."""

    codec = BlockAttributionCodec(b"modern-crop-bound-secret")
    handle = bytes.fromhex("A1B2C3D4")
    paths = tuple(path for name in MODERN_SAMPLE_NAMES if (path := samples_dir / name).exists())
    audits = tuple(_audit_track(path, codec, handle) for path in paths)
    manifest = {
        "goal": "estimate crop tolerance for dense modern pop/rap-style samples",
        "scope": "oracle surviving-block upper bound, not full blind geometry recovery",
        "block_seconds": BLOCK_SECONDS,
        "crop_seconds": CROP_SECONDS,
        "summaries": [asdict(summary) for summary, _ in audits],
        "trials": {summary.source_file: [asdict(trial) for trial in trials] for summary, trials in audits},
    }
    OUTPUT_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def main() -> None:
    """Print the modern crop recovery bound manifest."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
