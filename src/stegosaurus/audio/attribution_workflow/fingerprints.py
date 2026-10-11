"""Localize clean suspicious excerpts against registered source audio.

This module implements the shared song-level prefilter measured in the V4
experiments. The source song is fingerprinted by block. A suspicious excerpt is
searched with coarse windows and fine refinement, producing a small candidate
set that can be reused for every recipient/export record under the song.

The fingerprint is intentionally simple log-band energy. It is a clean-file
localizer, not a robust audio fingerprint for recorded or platform-transcoded
audio.
"""

from __future__ import annotations

from time import perf_counter

import numpy as np

from .models import LocalizationCandidate, SongFingerprintIndex, as_vector
from ..pilot import PcmAudio


BANDS_HZ = (80.0, 160.0, 320.0, 640.0, 1280.0, 2560.0, 5000.0)


def build_song_fingerprint_index(audio: PcmAudio, block_seconds: float = 30.0) -> SongFingerprintIndex:
    """Build source block fingerprints for a registered song."""

    if block_seconds <= 0:
        raise ValueError("block_seconds must be positive")
    full_blocks = int(audio.duration_seconds // block_seconds)
    if full_blocks < 1:
        raise ValueError("song must contain at least one complete fingerprint block")
    fingerprints = tuple(tuple(_fingerprint(_window(audio, index * block_seconds, block_seconds))) for index in range(full_blocks))
    return SongFingerprintIndex(block_seconds, fingerprints)


def localize_excerpt(
    excerpt: PcmAudio,
    index: SongFingerprintIndex,
    top_count: int = 5,
    coarse_stride_seconds: float = 5.0,
    fine_radius_seconds: float = 3.0,
    fine_stride_seconds: float = 0.5,
) -> tuple[tuple[LocalizationCandidate, ...], float]:
    """Return localized candidate windows and elapsed milliseconds."""

    _validate_search(excerpt, index, top_count, coarse_stride_seconds, fine_radius_seconds, fine_stride_seconds)
    started = perf_counter()
    coarse_starts = np.arange(0.0, excerpt.duration_seconds - index.block_seconds + 0.001, coarse_stride_seconds)
    coarse = tuple(_candidate(excerpt, index, float(start)) for start in coarse_starts)
    top_coarse = tuple(sorted(coarse, key=lambda item: item.score, reverse=True)[:top_count])
    refined = tuple(
        candidate
        for coarse_candidate in top_coarse
        for candidate in _refine(excerpt, index, coarse_candidate.crop_window_start_seconds, fine_radius_seconds, fine_stride_seconds)
    )
    candidates = _unique_by_block(tuple(sorted(refined or coarse, key=lambda item: item.score, reverse=True)), top_count)
    return candidates, (perf_counter() - started) * 1000.0


def _validate_search(
    excerpt: PcmAudio,
    index: SongFingerprintIndex,
    top_count: int,
    coarse_stride_seconds: float,
    fine_radius_seconds: float,
    fine_stride_seconds: float,
) -> None:
    """Validate public localization parameters."""

    if excerpt.duration_seconds < index.block_seconds:
        raise ValueError("excerpt must contain at least one complete localization window")
    if top_count < 1:
        raise ValueError("top_count must be positive")
    if coarse_stride_seconds <= 0 or fine_radius_seconds < 0 or fine_stride_seconds <= 0:
        raise ValueError("localization strides and radius must be positive")


def _candidate(excerpt: PcmAudio, index: SongFingerprintIndex, start_seconds: float) -> LocalizationCandidate:
    """Score one crop-local candidate against source block fingerprints."""

    vector = _fingerprint(_window(excerpt, start_seconds, index.block_seconds))
    scores = tuple(float(np.dot(vector, as_vector(source))) for source in index.fingerprints)
    block_index = int(np.argmax(scores))
    return LocalizationCandidate(round(start_seconds, 3), block_index, scores[block_index])


def _refine(
    excerpt: PcmAudio,
    index: SongFingerprintIndex,
    coarse_start: float,
    radius_seconds: float,
    stride_seconds: float,
) -> tuple[LocalizationCandidate, ...]:
    """Search fine offsets around one coarse candidate."""

    starts = np.arange(coarse_start - radius_seconds, coarse_start + radius_seconds + 0.001, stride_seconds)
    valid = tuple(float(start) for start in starts if 0 <= start and start + index.block_seconds <= excerpt.duration_seconds)
    return tuple(_candidate(excerpt, index, start) for start in valid)


def _unique_by_block(candidates: tuple[LocalizationCandidate, ...], top_count: int) -> tuple[LocalizationCandidate, ...]:
    """Keep high-scoring candidates with one winner per source block."""

    selected: list[LocalizationCandidate] = []
    seen: set[int] = set()
    for candidate in candidates:
        if candidate.registry_block_index in seen:
            continue
        selected.append(candidate)
        seen.add(candidate.registry_block_index)
        if len(selected) == top_count:
            break
    return tuple(selected)


def _window(audio: PcmAudio, start_seconds: float, seconds: float) -> PcmAudio:
    """Return a fixed-duration copied audio window."""

    start = int(round(start_seconds * audio.sample_rate))
    count = int(round(seconds * audio.sample_rate))
    return PcmAudio(np.array(audio.samples[start : start + count], copy=True), audio.sample_rate)


def _fingerprint(audio: PcmAudio) -> np.ndarray:
    """Return a normalized log-band energy vector."""

    samples = audio.samples * np.hanning(len(audio.samples))
    spectrum = np.abs(np.fft.rfft(samples)) ** 2
    frequencies = np.fft.rfftfreq(len(samples), 1.0 / audio.sample_rate)
    edges = (0.0, *BANDS_HZ, audio.sample_rate / 2)
    values = []
    for lower, upper in zip(edges[:-1], edges[1:]):
        mask = (frequencies >= lower) & (frequencies < upper)
        values.append(float(np.log1p(np.mean(spectrum[mask])) if np.any(mask) else 0.0))
    vector = np.asarray(values, dtype=np.float64)
    norm = float(np.linalg.norm(vector))
    return vector / norm if norm else vector
