"""Run iteration 031: shared registry-audio crop prefilter.

Goal: test the workflow assumption that a known-song registry can localize a
leaked excerpt before any recipient-specific watermark record is checked. This
prefilter is intentionally shared across all embedding records for a song: it
compares cheap audio fingerprints from the suspicious crop against fingerprints
from the registered source song, then returns candidate windows for expensive
attribution.

Toy flow:
    selected registry song + suspicious crop -> spectral-energy fingerprints
        -> coarse window rank -> fine phase refinement -> top candidate windows
        -> measure whether candidates land near useful original block starts

This does not verify a watermark. It measures whether local audio similarity can
reduce the search space that many embedding records would otherwise repeat.
"""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from time import perf_counter

import numpy as np

from ....attribution import BlockAttributionCodec
from ....pilot import PcmAudio, read_pcm16_wav
from .models import PrefilterCandidate, PrefilterTrial, TrackPrefilterSummary


SAMPLES_DIR = Path("samples")
OUTPUT_PATH = Path(__file__).with_name("results.json")
TARGET_FILES = ("08. Gutta Bitch.wav", "10. Lovers Rock.wav", "19. Get Low.wav")
BLOCK_SECONDS = 30.0
CROP_SECONDS = (60.0, 90.0, 120.0)
CROP_START_FRACTIONS = (0.17, 0.37, 0.53)
COARSE_STRIDE_SECONDS = 5.0
FINE_RADIUS_SECONDS = 3.0
FINE_STRIDE_SECONDS = 0.5
TOP_COARSE_COUNT = 5
TOP_FINAL_COUNT = 5
HIT_TOLERANCE_SECONDS = 1.0
BANDS_HZ = (80.0, 160.0, 320.0, 640.0, 1280.0, 2560.0, 5000.0)


def _crop(audio: PcmAudio, start_seconds: float, duration_seconds: float) -> PcmAudio:
    """Return one copied crop from a longer signal."""

    start = int(round(start_seconds * audio.sample_rate))
    count = int(round(duration_seconds * audio.sample_rate))
    return PcmAudio(np.array(audio.samples[start : start + count], copy=True), audio.sample_rate)


def _window(audio: PcmAudio, start_seconds: float, seconds: float) -> PcmAudio:
    """Return one fixed-duration window from an audio object."""

    start = int(round(start_seconds * audio.sample_rate))
    count = int(round(seconds * audio.sample_rate))
    return PcmAudio(np.array(audio.samples[start : start + count], copy=True), audio.sample_rate)


def _fingerprint(audio: PcmAudio) -> np.ndarray:
    """Return a normalized log-band energy fingerprint for a candidate window."""

    samples = audio.samples * np.hanning(len(audio.samples))
    spectrum = np.abs(np.fft.rfft(samples)) ** 2
    frequencies = np.fft.rfftfreq(len(samples), 1.0 / audio.sample_rate)
    edges = (0.0, *BANDS_HZ, audio.sample_rate / 2)
    energies = []
    for lower, upper in zip(edges[:-1], edges[1:]):
        mask = (frequencies >= lower) & (frequencies < upper)
        energies.append(float(np.log1p(np.mean(spectrum[mask])) if np.any(mask) else 0.0))
    vector = np.asarray(energies, dtype=np.float64)
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm else vector


def _score(left: np.ndarray, right: np.ndarray) -> float:
    """Return cosine similarity between two normalized fingerprints."""

    return float(np.dot(left, right))


def _registry_blocks(audio: PcmAudio, block_seconds: float) -> tuple[np.ndarray, ...]:
    """Return source-song block fingerprints shared by all embedding records."""

    full_blocks = int(audio.duration_seconds // block_seconds)
    return tuple(_fingerprint(_window(audio, index * block_seconds, block_seconds)) for index in range(full_blocks))


def _starts(audio: PcmAudio, crop_seconds: float) -> tuple[float, ...]:
    """Return deterministic crop starts for the localization study."""

    maximum_start = max(0.0, audio.duration_seconds - crop_seconds)
    return tuple(round(maximum_start * fraction, 3) for fraction in CROP_START_FRACTIONS)


def _useful_boundaries(crop_start: float, crop_seconds: float, block_count: int) -> tuple[float, ...]:
    """Return crop-local starts for complete original blocks inside the crop."""

    boundaries = []
    for index in range(block_count):
        absolute = index * BLOCK_SECONDS
        local = absolute - crop_start
        if 0 <= local and local + BLOCK_SECONDS <= crop_seconds:
            boundaries.append(local)
    return tuple(boundaries)


def _candidate(
    crop: PcmAudio,
    registry_fingerprints: tuple[np.ndarray, ...],
    start_seconds: float,
    useful: tuple[float, ...],
) -> PrefilterCandidate:
    """Score one crop-local candidate against all registry block fingerprints."""

    fingerprint = _fingerprint(_window(crop, start_seconds, BLOCK_SECONDS))
    scores = tuple(_score(fingerprint, registry) for registry in registry_fingerprints)
    block_index = int(np.argmax(scores))
    error = min((abs(start_seconds - boundary) for boundary in useful), default=float("inf"))
    return PrefilterCandidate(
        round(start_seconds, 3),
        block_index,
        block_index * BLOCK_SECONDS,
        scores[block_index],
        error,
        error <= HIT_TOLERANCE_SECONDS,
    )


def _refine(
    crop: PcmAudio,
    registry_fingerprints: tuple[np.ndarray, ...],
    coarse_start: float,
    useful: tuple[float, ...],
) -> tuple[PrefilterCandidate, ...]:
    """Search fine offsets around one coarse prefilter winner."""

    starts = np.arange(coarse_start - FINE_RADIUS_SECONDS, coarse_start + FINE_RADIUS_SECONDS + 0.001, FINE_STRIDE_SECONDS)
    valid = tuple(float(start) for start in starts if 0 <= start and start + BLOCK_SECONDS <= crop.duration_seconds)
    return tuple(_candidate(crop, registry_fingerprints, start, useful) for start in valid)


def _trial(path: Path, audio: PcmAudio, registry_fingerprints: tuple[np.ndarray, ...], crop_seconds: float, crop_start: float) -> tuple[PrefilterTrial, tuple[PrefilterCandidate, ...]]:
    """Run one shared audio-prefilter crop localization trial."""

    crop = _crop(audio, crop_start, crop_seconds)
    useful = _useful_boundaries(crop_start, crop_seconds, len(registry_fingerprints))
    stride = COARSE_STRIDE_SECONDS
    coarse_starts = np.arange(0.0, crop.duration_seconds - BLOCK_SECONDS + 0.001, stride)
    started = perf_counter()
    coarse = tuple(_candidate(crop, registry_fingerprints, float(start), useful) for start in coarse_starts)
    top_coarse = tuple(sorted(coarse, key=lambda item: item.score, reverse=True)[:TOP_COARSE_COUNT])
    refined = tuple(candidate for coarse_candidate in top_coarse for candidate in _refine(crop, registry_fingerprints, coarse_candidate.crop_window_start_seconds, useful))
    final = tuple(sorted(refined or coarse, key=lambda item: item.score, reverse=True)[:TOP_FINAL_COUNT])
    elapsed_ms = (perf_counter() - started) * 1000.0
    hits = tuple(candidate for candidate in final if candidate.useful_boundary_hit)
    trial = PrefilterTrial(
        path.name,
        crop_seconds,
        crop_start,
        len(coarse),
        len(useful),
        bool(final and final[0].useful_boundary_hit),
        bool(hits),
        min((candidate.nearest_boundary_error_seconds for candidate in final), default=None),
        elapsed_ms,
    )
    return trial, final


def _audit(path: Path) -> tuple[TrackPrefilterSummary, tuple[PrefilterTrial, ...], dict[str, list[dict[str, object]]]]:
    """Audit shared registry-audio localization for one song."""

    audio = read_pcm16_wav(path)
    codec = BlockAttributionCodec(b"registry-audio-prefilter")
    embedding = codec.embed(audio, bytes.fromhex("A1B2C3D4"), block_seconds=BLOCK_SECONDS)
    registry = _registry_blocks(audio, BLOCK_SECONDS)
    trials_and_candidates = tuple(
        _trial(path, embedding.audio, registry, crop_seconds, start)
        for crop_seconds in CROP_SECONDS
        for start in _starts(embedding.audio, crop_seconds)
    )
    trials = tuple(item[0] for item in trials_and_candidates)
    candidates = {
        f"{trial.source_file}|{trial.crop_seconds}|{trial.crop_start_seconds}": [asdict(candidate) for candidate in final]
        for trial, final in trials_and_candidates
    }
    elapsed = tuple(trial.elapsed_ms for trial in trials)
    summary = TrackPrefilterSummary(
        path.name,
        len(embedding.record.block_records),
        len(trials),
        sum(trial.top1_hit for trial in trials),
        sum(trial.top5_hit for trial in trials),
        float(np.median(elapsed)) if elapsed else 0.0,
        _note(trials),
    )
    return summary, trials, candidates


def _note(trials: tuple[PrefilterTrial, ...]) -> str:
    """Return a concise workflow interpretation for a track."""

    hit_rate = sum(trial.top5_hit for trial in trials) / len(trials) if trials else 0.0
    if hit_rate >= 0.8:
        return "shared song-level prefilter is viable for registry fanout"
    if hit_rate >= 0.5:
        return "prefilter is promising but needs stronger features"
    return "log-band prefilter is too weak by itself"


def run(samples_dir: Path = SAMPLES_DIR) -> dict[str, object]:
    """Run the registry-audio prefilter analysis and write JSON results."""

    paths = tuple(path for name in TARGET_FILES if (path := samples_dir / name).exists())
    audits = tuple(_audit(path) for path in paths)
    manifest = {
        "goal": "test a shared song-level prefilter before many embedding-record checks",
        "scope": "known song source audio is available in the user registry",
        "block_seconds": BLOCK_SECONDS,
        "top_final_count": TOP_FINAL_COUNT,
        "summaries": [asdict(summary) for summary, _, _ in audits],
        "trials": {summary.source_file: [asdict(trial) for trial in trials] for summary, trials, _ in audits},
        "top_candidates": {key: value for _, _, candidates in audits for key, value in candidates.items()},
    }
    OUTPUT_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def main() -> None:
    """Print the registry-audio prefilter analysis."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
