"""Create deterministic, license-free audio fixtures for the manual Tkinter lab.

The lab needs a cover long enough for the bounded v1 claimed-handle profile,
but it should not ship recordings or imply that its fixtures represent real
music or speech. These synthetic signals are simply energetic test covers:

    named fixture -> normalized mono ``PcmAudio`` -> encode or transform

They deliberately live outside the encoder so manual UI data does not affect
the attribution algorithm or its measured evaluation boundaries.
"""

from __future__ import annotations

import numpy as np

from .pilot import PcmAudio


DEFAULT_DURATION_SECONDS = 30
DEFAULT_SAMPLE_RATE = 16000


def music_like_sample(duration_seconds: int = DEFAULT_DURATION_SECONDS) -> PcmAudio:
    """Return a deterministic harmonic cover with modulation and low-amplitude noise."""

    positions = _positions(duration_seconds)
    modulation = 0.5 + 0.5 * np.sin(2 * np.pi * 0.11 * positions)
    samples = (
        0.18 * np.sin(2 * np.pi * 110 * positions)
        + 0.12 * np.sin(2 * np.pi * 220 * positions + 0.25 * modulation)
        + 0.10 * np.sin(2 * np.pi * 330 * positions)
        + 0.08 * np.sin(2 * np.pi * (700 + 80 * modulation) * positions)
        + 0.06 * np.sin(2 * np.pi * (1400 + 140 * modulation) * positions)
        + 0.025 * np.random.default_rng(31).normal(size=len(positions))
    )
    return PcmAudio(np.asarray(samples, dtype=np.float64), DEFAULT_SAMPLE_RATE)


def speech_like_sample(duration_seconds: int = DEFAULT_DURATION_SECONDS) -> PcmAudio:
    """Return a deterministic voiced, syllable-shaped synthetic test cover."""

    positions = _positions(duration_seconds)
    syllable_envelope = 0.12 + 0.88 * np.maximum(0.0, np.sin(2 * np.pi * 2.7 * positions)) ** 1.7
    pitch = 130 + 24 * np.sin(2 * np.pi * 0.18 * positions)
    samples = syllable_envelope * (
        0.20 * np.sin(2 * np.pi * pitch * positions)
        + 0.10 * np.sin(2 * np.pi * 2 * pitch * positions)
        + 0.06 * np.sin(2 * np.pi * 3 * pitch * positions)
        + 0.05 * np.sin(2 * np.pi * (900 + 120 * np.sin(2 * np.pi * 0.4 * positions)) * positions)
    )
    samples += 0.018 * np.random.default_rng(47).normal(size=len(positions))
    return PcmAudio(np.asarray(samples, dtype=np.float64), DEFAULT_SAMPLE_RATE)


def _positions(duration_seconds: int) -> np.ndarray:
    """Validate a whole-second fixture duration and return its sample-time axis."""

    if isinstance(duration_seconds, bool) or not isinstance(duration_seconds, int) or duration_seconds < 1:
        raise ValueError("duration_seconds must be a positive integer")
    sample_count = DEFAULT_SAMPLE_RATE * duration_seconds
    return np.arange(sample_count, dtype=np.float64) / DEFAULT_SAMPLE_RATE
