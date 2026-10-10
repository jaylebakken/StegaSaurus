"""Define named manual transformations for the Tkinter attribution lab.

The demo uses a fixed, visible set of transformations so button clicks are
replayable and easy to describe. These helpers are manual test inputs, not
claims of robustness against a transformation class.
"""

from __future__ import annotations

from .attacks import add_white_noise, low_pass_filter, mp3_round_trip, normalize_peak, resample_audio, trim_audio
from .pilot import PcmAudio


DISTORTION_NAMES = (
    "Normalize peak (0.85)",
    "White noise (30 dB)",
    "Low-pass filter (4 kHz)",
    "MP3 round trip (96 kbps)",
    "Resample 12 kHz round trip",
    "Leading crop (250 ms)",
)


def apply_demo_distortion(audio: PcmAudio, name: str) -> PcmAudio:
    """Apply one visible manual-test transformation using fixed parameters."""

    if name == "Normalize peak (0.85)":
        return normalize_peak(audio, 0.85)
    if name == "White noise (30 dB)":
        return add_white_noise(audio, 30.0, seed=20261009)
    if name == "Low-pass filter (4 kHz)":
        return low_pass_filter(audio, 4000.0)
    if name == "MP3 round trip (96 kbps)":
        return mp3_round_trip(audio, 96)
    if name == "Resample 12 kHz round trip":
        return resample_audio(resample_audio(audio, 12000), audio.sample_rate)
    if name == "Leading crop (250 ms)":
        return trim_audio(audio, 0.25, audio.duration_seconds)
    raise ValueError(f"unknown distortion: {name}")

