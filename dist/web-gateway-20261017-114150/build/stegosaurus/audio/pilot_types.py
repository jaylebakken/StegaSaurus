"""Define PCM values, pilot configuration, observations, and PCM16 WAV I/O.

These types intentionally contain no watermark decisions. They make the
pipeline inspectable: WAV bytes become normalized mono samples, configuration
describes a conservative STFT carrier region, and result records preserve what
was embedded or observed.

Toy example:
    audio = read_pcm16_wav(Path("input.wav"))
    assert audio.duration_seconds > 0
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import TypeAlias
import wave

import numpy as np

from .schema import AudioDetectionResult


AudioSamples: TypeAlias = np.ndarray


@dataclass(frozen=True, slots=True)
class PcmAudio:
    """Represent normalized mono PCM audio samples and their sample rate."""

    samples: AudioSamples
    sample_rate: int

    def __post_init__(self) -> None:
        """Validate one-dimensional finite normalized sample data and a positive rate."""

        if self.sample_rate < 1:
            raise ValueError("sample_rate must be positive")
        if self.samples.ndim != 1:
            raise ValueError("samples must be one-dimensional mono audio")
        if not len(self.samples):
            raise ValueError("samples must not be empty")
        if not np.isfinite(self.samples).all():
            raise ValueError("samples must be finite")

    @property
    def duration_seconds(self) -> float:
        """Return the exact sample-derived duration in seconds."""

        return len(self.samples) / self.sample_rate


@dataclass(frozen=True, slots=True)
class SpectralPilotConfig:
    """Configure frame geometry, frequency range, and conservative pair modulation."""

    frame_size: int = 1024
    hop_size: int = 256
    minimum_frequency_hz: float = 500.0
    maximum_frequency_hz: float = 6000.0
    pairs_per_frame: int = 16
    minimum_pairs_per_frame: int = 8
    minimum_frame_rms: float = 0.002
    minimum_pair_magnitude: float = 0.00005
    relative_difference: float = 0.48
    minimum_confidence: float = 0.01
    maximum_sync_offset_frames: int = 32

    def __post_init__(self) -> None:
        """Validate transform geometry and bounded perceptual modulation parameters."""

        if self.frame_size < 32 or self.frame_size & (self.frame_size - 1):
            raise ValueError("frame_size must be a power of two and at least 32")
        if not 1 <= self.hop_size <= self.frame_size:
            raise ValueError("hop_size must be between 1 and frame_size")
        if not 0 <= self.minimum_frequency_hz < self.maximum_frequency_hz:
            raise ValueError("frequency bounds are not ordered")
        if self.pairs_per_frame < 1 or self.minimum_pairs_per_frame < 1:
            raise ValueError("pairs_per_frame must be positive")
        if self.minimum_pairs_per_frame > self.pairs_per_frame:
            raise ValueError("minimum_pairs_per_frame must not exceed pairs_per_frame")
        if self.minimum_frame_rms < 0 or self.minimum_pair_magnitude < 0:
            raise ValueError("minimum energy thresholds must not be negative")
        if not 0 < self.relative_difference < 1:
            raise ValueError("relative_difference must be between 0 and 1")
        if not 0 < self.minimum_confidence < 1:
            raise ValueError("minimum_confidence must be between 0 and 1")
        if self.maximum_sync_offset_frames < 0:
            raise ValueError("maximum_sync_offset_frames must not be negative")


@dataclass(frozen=True, slots=True)
class SpectralPilotEmbedding:
    """Report the watermarked audio and frame coverage from one embedding pass."""

    audio: PcmAudio
    expected_frame_bits: tuple[int, ...]
    embedded_frame_count: int
    skipped_frame_count: int
    signal_to_noise_db: float


@dataclass(frozen=True, slots=True)
class SpectralPilotExtraction:
    """Report frame observations, confidence values, and keyed detection outcome."""

    observed_frame_bits: tuple[int | None, ...]
    frame_confidences: tuple[float | None, ...]
    frame_offset: int
    synchronization_candidates: int
    detection: AudioDetectionResult


def read_pcm16_wav(path: Path) -> PcmAudio:
    """Read a PCM16 WAV file, downmix channels, and normalize samples to float64."""

    with wave.open(str(path), "rb") as source_wave:
        if source_wave.getsampwidth() != 2:
            raise ValueError("only PCM16 WAV input is supported by the audio pilot")
        channel_count = source_wave.getnchannels()
        if channel_count < 1:
            raise ValueError("WAV input must contain at least one channel")
        sample_rate = source_wave.getframerate()
        sample_data = np.frombuffer(source_wave.readframes(source_wave.getnframes()), dtype="<i2")
    if len(sample_data) % channel_count:
        raise ValueError("WAV sample data does not align with its channel count")
    channel_samples = sample_data.reshape((-1, channel_count)).astype(np.float64)
    mono_samples = np.mean(channel_samples, axis=1) / 32768.0
    return PcmAudio(mono_samples, sample_rate)


def write_pcm16_wav(path: Path, audio: PcmAudio) -> None:
    """Write normalized mono samples as a PCM16 WAV file with deterministic clipping."""

    normalized_samples = np.clip(audio.samples, -1.0, 1.0)
    pcm_samples = np.clip(
        np.rint(normalized_samples * 32768.0),
        -32768,
        32767,
    ).astype("<i2")
    with wave.open(str(path), "wb") as destination_wave:
        destination_wave.setnchannels(1)
        destination_wave.setsampwidth(2)
        destination_wave.setframerate(audio.sample_rate)
        destination_wave.writeframes(pcm_samples.tobytes())


