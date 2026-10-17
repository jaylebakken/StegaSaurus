"""Perform STFT conversion, frequency-range selection, and basic signal metrics.

The STFT turns a waveform into overlapping time frames and frequency bins. The
pilot modulates selected complex-spectrum bins, then reconstructs PCM through
the matching inverse transform. These helpers intentionally expose that bridge
so a reader can distinguish audio representation from watermark policy.
"""

from __future__ import annotations

import math

import numpy as np
from scipy import signal

from .pilot_types import AudioSamples, PcmAudio


class SpectralTransformMixin:
    """Provide the waveform-to-STFT conversion and reusable spectral metrics."""

    def _stft(self, audio: PcmAudio) -> tuple[AudioSamples, AudioSamples]:
        """Return one-sided complex STFT frames using the configured overlap geometry."""

        frequencies, _, spectrum = signal.stft(
            audio.samples,
            fs=audio.sample_rate,
            window="hann",
            nperseg=self._config.frame_size,
            noverlap=self._config.frame_size - self._config.hop_size,
            boundary="zeros",
            padded=True,
        )
        return frequencies, spectrum

    def _inverse_stft(self, spectrum: AudioSamples, source_audio: PcmAudio) -> AudioSamples:
        """Invert an STFT, restore source length, and avoid output clipping by uniform scaling."""

        _, reconstructed_samples = signal.istft(
            spectrum,
            fs=source_audio.sample_rate,
            window="hann",
            nperseg=self._config.frame_size,
            noverlap=self._config.frame_size - self._config.hop_size,
            input_onesided=True,
            boundary=True,
        )
        if len(reconstructed_samples) < len(source_audio.samples):
            reconstructed_samples = np.pad(
                reconstructed_samples,
                (0, len(source_audio.samples) - len(reconstructed_samples)),
            )
        reconstructed_samples = reconstructed_samples[: len(source_audio.samples)]
        peak = float(np.max(np.abs(reconstructed_samples)))
        if peak > 1.0:
            reconstructed_samples = reconstructed_samples / peak
        return np.asarray(reconstructed_samples, dtype=np.float64)

    def _frequency_bin_range(self, frequencies: AudioSamples) -> tuple[int, int]:
        """Return inclusive transform-bin bounds constrained by the configured frequency range."""

        lower_bin = int(np.searchsorted(frequencies, self._config.minimum_frequency_hz, side="left"))
        upper_bin = int(np.searchsorted(frequencies, self._config.maximum_frequency_hz, side="right")) - 1
        if upper_bin - lower_bin + 1 < self._config.pairs_per_frame * 2:
            raise ValueError("configured frequency range cannot supply enough coefficient pairs")
        return lower_bin, upper_bin


    @staticmethod
    def _frame_rms(frame_spectrum: AudioSamples) -> float:
        """Return the RMS magnitude proxy used to reject quiet spectral frames."""

        return float(math.sqrt(np.mean(np.abs(frame_spectrum) ** 2)))

    @staticmethod
    def _signal_to_noise_db(signal_samples: AudioSamples, noise_samples: AudioSamples) -> float:
        """Return signal-to-noise ratio in decibels, including an exact no-noise case."""

        signal_power = float(np.mean(signal_samples**2))
        noise_power = float(np.mean(noise_samples**2))
        if not noise_power:
            return math.inf
        if not signal_power:
            return -math.inf
        return 10 * math.log10(signal_power / noise_power)
