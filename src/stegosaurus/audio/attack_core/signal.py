"""Apply transparent deterministic waveform transformations for evaluation.

Each function names one transformation and keeps its parameters visible to the
caller. These utilities are test fixtures, not a statement that the pilot
survives unlisted parameters or real-world production processing chains.

Toy example:
    attacked = low_pass_filter(normalize_peak(audio), cutoff_hz=4000)
"""

from __future__ import annotations

from fractions import Fraction
import math
from numbers import Integral, Real

import numpy as np
from scipy import signal

from ..pilot import PcmAudio

def resample_audio(audio: PcmAudio, destination_sample_rate: int) -> PcmAudio:
    """Resample mono audio through integer-ratio polyphase filtering where possible."""

    if isinstance(destination_sample_rate, bool) or not isinstance(destination_sample_rate, Integral):
        raise TypeError("destination_sample_rate must be an integer")
    if destination_sample_rate < 1:
        raise ValueError("destination_sample_rate must be positive")
    if destination_sample_rate == audio.sample_rate:
        return audio
    divisor = int(np.gcd(audio.sample_rate, destination_sample_rate))
    resampled = signal.resample_poly(
        audio.samples,
        destination_sample_rate // divisor,
        audio.sample_rate // divisor,
    )
    return PcmAudio(np.asarray(resampled, dtype=np.float64), destination_sample_rate)


def normalize_peak(audio: PcmAudio, target_peak: float = 0.90) -> PcmAudio:
    """Scale audio to a requested nonzero peak while preserving waveform shape."""

    target_peak = _finite_float(target_peak, "target_peak")
    if not 0 < target_peak <= 1:
        raise ValueError("target_peak must be greater than zero and at most one")
    peak = float(np.max(np.abs(audio.samples)))
    if not peak:
        return audio
    return PcmAudio(audio.samples * (target_peak / peak), audio.sample_rate)


def low_pass_filter(audio: PcmAudio, cutoff_hz: float) -> PcmAudio:
    """Apply a zero-phase fourth-order Butterworth low-pass filter to mono audio."""

    cutoff_hz = _finite_float(cutoff_hz, "cutoff_hz")
    nyquist_hz = audio.sample_rate / 2
    if not 0 < cutoff_hz < nyquist_hz:
        raise ValueError("cutoff_hz must be within the open Nyquist interval")
    filter_sections = signal.butter(4, cutoff_hz / nyquist_hz, btype="low", output="sos")
    padding_length = min(15, len(audio.samples) - 1)
    filtered = signal.sosfiltfilt(filter_sections, audio.samples, padlen=padding_length)
    return PcmAudio(np.asarray(filtered, dtype=np.float64), audio.sample_rate)


def add_white_noise(audio: PcmAudio, noise_snr_db: float, seed: int = 0) -> PcmAudio:
    """Add deterministic white noise at a requested signal-to-noise ratio in decibels."""

    noise_snr_db = _finite_float(noise_snr_db, "noise_snr_db")
    if not -300 <= noise_snr_db <= 300:
        raise ValueError("noise_snr_db must be between -300 and 300")
    if isinstance(seed, bool) or not isinstance(seed, Integral):
        raise TypeError("seed must be an integer")
    signal_power = float(np.mean(audio.samples**2))
    if not signal_power:
        return audio
    noise_power = signal_power / (10 ** (noise_snr_db / 10))
    random_generator = np.random.default_rng(seed)
    noise = random_generator.normal(0.0, np.sqrt(noise_power), len(audio.samples))
    return PcmAudio(np.asarray(audio.samples + noise, dtype=np.float64), audio.sample_rate)


def trim_audio(audio: PcmAudio, start_seconds: float, end_seconds: float) -> PcmAudio:
    """Return a contiguous sample range specified by non-negative start and end seconds."""

    start_seconds = _finite_float(start_seconds, "start_seconds")
    end_seconds = _finite_float(end_seconds, "end_seconds")
    if not 0 <= start_seconds < end_seconds <= audio.duration_seconds:
        raise ValueError("trim bounds must be ordered within audio duration")
    start_index = round(start_seconds * audio.sample_rate)
    end_index = round(end_seconds * audio.sample_rate)
    if end_index <= start_index:
        raise ValueError("trim bounds must contain at least one sample")
    return PcmAudio(np.array(audio.samples[start_index:end_index], copy=True), audio.sample_rate)


def concatenate_audio(parts: tuple[PcmAudio, ...]) -> PcmAudio:
    """Concatenate mono audio parts that share one sample rate into a single waveform."""

    if not parts:
        raise ValueError("parts must not be empty")
    sample_rate = parts[0].sample_rate
    if any(part.sample_rate != sample_rate for part in parts):
        raise ValueError("all concatenated audio parts must use the same sample rate")
    return PcmAudio(np.concatenate(tuple(part.samples for part in parts)), sample_rate)


def time_scale_audio(audio: PcmAudio, speed_factor: float) -> PcmAudio:
    """Change playback speed while preserving sample rate through rational resampling."""

    speed_factor = _finite_float(speed_factor, "speed_factor")
    if not 0.5 <= speed_factor <= 2.0:
        raise ValueError("speed_factor must be between 0.5 and 2.0")
    if speed_factor == 1:
        return audio
    ratio = Fraction(1 / speed_factor).limit_denominator(1000)
    transformed = signal.resample_poly(audio.samples, ratio.numerator, ratio.denominator)
    return PcmAudio(np.asarray(transformed, dtype=np.float64), audio.sample_rate)


def _finite_float(value: Real, name: str) -> float:
    """Return one finite real-valued attack parameter or raise a clear type error."""

    if isinstance(value, bool) or not isinstance(value, Real):
        raise TypeError(f"{name} must be a real number")
    converted = float(value)
    if not np.isfinite(converted):
        raise ValueError(f"{name} must be finite")
    return converted



def add_reverberation(audio: PcmAudio, decay_seconds: float, mix: float, seed: int = 0) -> PcmAudio:
    """Mix a deterministic, decaying synthetic room response into a mono waveform."""

    decay_seconds = _finite_float(decay_seconds, "decay_seconds")
    mix = _finite_float(mix, "mix")
    if not 0.001 <= decay_seconds <= 2.0:
        raise ValueError("decay_seconds must be between 0.001 and 2.0")
    if not 0 <= mix <= 1:
        raise ValueError("mix must be between zero and one")
    if isinstance(seed, bool) or not isinstance(seed, Integral):
        raise TypeError("seed must be an integer")
    if not mix:
        return audio
    response_length = max(2, round(decay_seconds * audio.sample_rate))
    sample_positions = np.arange(response_length, dtype=np.float64)
    decay_envelope = np.exp(-5 * sample_positions / response_length)
    random_generator = np.random.default_rng(seed)
    impulse_response = random_generator.normal(0.0, 1.0, response_length) * decay_envelope
    impulse_response[0] += 1.0
    impulse_response /= np.sum(np.abs(impulse_response))
    wet_samples = signal.fftconvolve(audio.samples, impulse_response, mode="full")[: len(audio.samples)]
    source_power = float(np.mean(audio.samples**2))
    wet_power = float(np.mean(wet_samples**2))
    if source_power and wet_power:
        wet_samples *= math.sqrt(source_power / wet_power)
    mixed_samples = (1 - mix) * audio.samples + mix * wet_samples
    return PcmAudio(np.asarray(mixed_samples, dtype=np.float64), audio.sample_rate)
