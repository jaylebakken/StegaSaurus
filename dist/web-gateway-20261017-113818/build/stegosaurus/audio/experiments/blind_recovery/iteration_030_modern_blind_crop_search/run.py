"""Run iteration 030: retained-record blind crop search for modern samples.

Goal: replace the oracle surviving-block geometry from iteration 029 with an
expensive retained-record window search. The experiment assumes registry
candidates are available for the selected song, but the crop offset and retained
block alignment are unknown.

Toy flow:
    watermarked song -> off-grid crop -> slide 30 s windows
        -> try retained block records against each window -> rank evidence
        -> pool top candidates -> compare source and wrong-record controls

This is a maximum-cost fallback experiment. It is not the final cheap pilot
prefilter; instead it measures whether a registry-backed search can find enough
evidence without being handed the original crop geometry.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from time import perf_counter

import numpy as np

from ....attribution import BlockAttributionCodec
from ....attribution_core import AttributionStatus
from ....attribution_core.models import AttributionVerification
from ....pilot import PcmAudio, read_pcm16_wav


SAMPLES_DIR = Path("samples")
OUTPUT_PATH = Path(__file__).with_name("results.json")
TARGET_FILES = ("10. Lovers Rock.wav",)
BLOCK_SECONDS = 30.0
STRIDE_SECONDS = 10.0
TOP_WINDOW_COUNT = 3
CROP_SECONDS = (60.0, 90.0)
CROP_START_FRACTIONS = (0.37,)


@dataclass(frozen=True, slots=True)
class RankedWindow:
    """Record one candidate window selected by retained-record search."""

    start_seconds: float
    matched_block_index: int
    recovered: bool
    rs_cost: int
    carrier_erasures: int
    known_bit_errors: int


@dataclass(frozen=True, slots=True)
class SearchOutcome:
    """Summarize one crop search for a watermarked or control signal."""

    control_name: str
    crop_seconds: float
    crop_start_seconds: float
    expected_recovered: bool
    recovered: bool
    pooled_rs_cost: int
    top_recovered_windows: int
    searched_windows: int
    elapsed_ms: float
    gate_passed: bool


@dataclass(frozen=True, slots=True)
class TrackSearchSummary:
    """Summarize blind crop search behavior for one modern sample."""

    source_file: str
    embedded_blocks: int
    controls_passed: bool
    watermarked_recovered: int
    watermarked_trials: int
    minimum_recovered_crop_seconds: float | None


def _crop(audio: PcmAudio, start_seconds: float, duration_seconds: float) -> PcmAudio:
    """Return a copied crop from a longer audio signal."""

    start = int(round(start_seconds * audio.sample_rate))
    count = int(round(duration_seconds * audio.sample_rate))
    return PcmAudio(np.array(audio.samples[start : start + count], copy=True), audio.sample_rate)


def _window(audio: PcmAudio, start_sample: int, sample_count: int) -> PcmAudio:
    """Return one candidate search window."""

    return PcmAudio(np.array(audio.samples[start_sample : start_sample + sample_count], copy=True), audio.sample_rate)


def _starts(audio: PcmAudio, crop_seconds: float) -> tuple[float, ...]:
    """Return deterministic off-grid crop starts."""

    maximum_start = max(0.0, audio.duration_seconds - crop_seconds)
    return tuple(round(maximum_start * fraction, 3) for fraction in CROP_START_FRACTIONS)


def _best_record_match(codec: BlockAttributionCodec, window: PcmAudio, records: tuple[object, ...]) -> tuple[int, AttributionVerification]:
    """Return the retained block record with the lowest claim RS cost."""

    scored = tuple((index, codec._codec.verify(window, record)) for index, record in enumerate(records))
    return min(scored, key=lambda item: (item[1].claim_rs_cost, item[1].carrier_erasures, item[1].known_bit_errors))


def _rank_windows(codec: BlockAttributionCodec, audio: PcmAudio, records: tuple[object, ...], block_samples: int) -> tuple[tuple[RankedWindow, AttributionVerification], ...]:
    """Rank sliding windows by best retained-record verification evidence."""

    stride = max(1, int(round(STRIDE_SECONDS * audio.sample_rate)))
    ranked: list[tuple[RankedWindow, AttributionVerification]] = []
    for start in range(0, len(audio.samples) - block_samples + 1, stride):
        block_index, verification = _best_record_match(codec, _window(audio, start, block_samples), records)
        ranked.append(
            (
                RankedWindow(
                    start / audio.sample_rate,
                    block_index,
                    verification.recovered,
                    verification.claim_rs_cost,
                    verification.carrier_erasures,
                    verification.known_bit_errors,
                ),
                verification,
            )
        )
    return tuple(sorted(ranked, key=lambda item: (item[0].rs_cost, item[0].carrier_erasures, item[0].known_bit_errors))[:TOP_WINDOW_COUNT])


def _search(
    codec: BlockAttributionCodec,
    audio: PcmAudio,
    records: tuple[object, ...],
    handle: bytes,
    crop_seconds: float,
    crop_start_seconds: float,
    expected_recovered: bool,
    control_name: str,
    block_samples: int,
) -> tuple[SearchOutcome, tuple[RankedWindow, ...]]:
    """Search one cropped signal and pool top retained-record candidates."""

    crop = _crop(audio, crop_start_seconds, crop_seconds)
    started = perf_counter()
    ranked = _rank_windows(codec, crop, records, block_samples)
    pooled = codec._pool(handle, [verification for _, verification in ranked])
    elapsed_ms = (perf_counter() - started) * 1000.0
    recovered = pooled.status is AttributionStatus.RECOVERED and pooled.claim_rs_cost <= 16
    outcome = SearchOutcome(
        control_name,
        crop_seconds,
        crop_start_seconds,
        expected_recovered,
        recovered,
        pooled.claim_rs_cost,
        sum(window.recovered for window, _ in ranked),
        max(0, ((len(crop.samples) - block_samples) // max(1, int(round(STRIDE_SECONDS * crop.sample_rate)))) + 1),
        elapsed_ms,
        recovered is expected_recovered,
    )
    return outcome, tuple(window for window, _ in ranked)


def _audit_track(path: Path) -> tuple[TrackSearchSummary, tuple[SearchOutcome, ...], dict[str, list[dict[str, object]]]]:
    """Embed one target track and run watermarked plus negative-control crop searches."""

    source = read_pcm16_wav(path)
    codec = BlockAttributionCodec(b"modern-blind-crop-search")
    wrong_codec = BlockAttributionCodec(b"modern-blind-crop-search-wrong")
    handle = bytes.fromhex("A1B2C3D4")
    embedding = codec.embed(source, handle, block_seconds=BLOCK_SECONDS)
    wrong_embedding = wrong_codec.embed(source, handle, block_seconds=BLOCK_SECONDS)
    records = embedding.record.block_records
    block_samples = embedding.record.block_sample_count
    outcomes: list[SearchOutcome] = []
    windows: dict[str, list[dict[str, object]]] = {}
    for crop_seconds in CROP_SECONDS:
        for start_seconds in _starts(embedding.audio, crop_seconds):
            cases = (
                ("watermarked", embedding.audio, codec, records, handle, True),
                ("source_control", source, codec, records, handle, False),
                ("wrong_record_control", embedding.audio, wrong_codec, wrong_embedding.record.block_records, handle, False),
            )
            for name, audio, case_codec, case_records, case_handle, expected in cases:
                outcome, ranked = _search(case_codec, audio, case_records, case_handle, crop_seconds, start_seconds, expected, name, block_samples)
                outcomes.append(outcome)
                key = f"{path.name}|{name}|{crop_seconds}|{start_seconds}"
                windows[key] = [asdict(window) for window in ranked]
    watermarked = tuple(outcome for outcome in outcomes if outcome.control_name == "watermarked")
    recovered_lengths = tuple(outcome.crop_seconds for outcome in watermarked if outcome.recovered)
    summary = TrackSearchSummary(
        path.name,
        len(records),
        all(outcome.gate_passed for outcome in outcomes),
        sum(outcome.recovered for outcome in watermarked),
        len(watermarked),
        min(recovered_lengths) if recovered_lengths else None,
    )
    return summary, tuple(outcomes), windows


def run(samples_dir: Path = SAMPLES_DIR) -> dict[str, object]:
    """Run the modern retained-record blind crop search suite."""

    paths = tuple(path for name in TARGET_FILES if (path := samples_dir / name).exists())
    audits = tuple(_audit_track(path) for path in paths)
    manifest = {
        "goal": "test maximum-cost registry-backed crop search without oracle crop geometry",
        "scope": "known song registry records available, unknown crop offset",
        "block_seconds": BLOCK_SECONDS,
        "stride_seconds": STRIDE_SECONDS,
        "top_window_count": TOP_WINDOW_COUNT,
        "summaries": [asdict(summary) for summary, _, _ in audits],
        "outcomes": {summary.source_file: [asdict(outcome) for outcome in outcomes] for summary, outcomes, _ in audits},
        "top_windows": {key: value for _, _, windows in audits for key, value in windows.items()},
    }
    OUTPUT_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def main() -> None:
    """Print the retained-record blind crop search manifest."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
