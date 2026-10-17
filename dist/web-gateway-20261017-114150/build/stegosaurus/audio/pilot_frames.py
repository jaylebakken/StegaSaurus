"""Embed and score one STFT frame using repeated differential bin-pair evidence.

For each eligible frame, the encoder biases selected pair magnitudes according
to an expected keyed bit. The extractor sums signed pair differences into a
soft score, then emits a bit only when its magnitude clears a configured
confidence threshold. Low confidence intentionally becomes an erasure.
"""

from __future__ import annotations

import math

import numpy as np

from .pilot_types import AudioSamples


class SpectralFrameCarrierMixin:
    """Provide frame-local spectral embedding and soft extraction operations."""

    def _embed_frame(
        self,
        frame_spectrum: AudioSamples,
        expected_bit: int,
        lower_bin: int,
        upper_bin: int,
        frame_index: int,
    ) -> bool:
        """Apply a repeated signed pair relationship when enough masked spectral energy exists."""

        if self._frame_rms(frame_spectrum) < self._config.minimum_frame_rms:
            return False
        modified_spectrum = np.array(frame_spectrum, copy=True)
        desired_sign = 1.0 if expected_bit else -1.0
        usable_pair_count = 0
        for pair_index, (first_bin, second_bin) in enumerate(
            self._pair_bins(lower_bin, upper_bin, frame_index)
        ):
            first_magnitude = float(abs(modified_spectrum[first_bin]))
            second_magnitude = float(abs(modified_spectrum[second_bin]))
            pair_energy = first_magnitude + second_magnitude
            if pair_energy < self._config.minimum_pair_magnitude:
                continue
            chip = self._pair_chip(frame_index, pair_index)
            first_magnitude, second_magnitude = self._modulated_pair_magnitudes(
                first_magnitude,
                second_magnitude,
                desired_sign * chip * self._config.relative_difference,
            )
            modified_spectrum[first_bin] = self._with_magnitude(
                modified_spectrum[first_bin],
                first_magnitude,
            )
            modified_spectrum[second_bin] = self._with_magnitude(
                modified_spectrum[second_bin],
                second_magnitude,
            )
            usable_pair_count += 1
        if usable_pair_count < self._config.minimum_pairs_per_frame:
            return False
        frame_spectrum[:] = modified_spectrum
        return True

    def _extract_frame(
        self,
        frame_spectrum: AudioSamples,
        lower_bin: int,
        upper_bin: int,
        frame_index: int,
    ) -> tuple[int | None, float | None]:
        """Return a soft repeated-pair decision or an erasure for an unsuitable frame."""

        score, confidence = self._extract_frame_score(
            frame_spectrum,
            lower_bin,
            upper_bin,
            frame_index,
        )
        if score is None or confidence is None:
            return None, confidence
        if confidence < self._config.minimum_confidence:
            return None, confidence
        return int(score >= 0), confidence

    def _extract_frame_score(
        self,
        frame_spectrum: AudioSamples,
        lower_bin: int,
        upper_bin: int,
        frame_index: int,
    ) -> tuple[float | None, float | None]:
        """Return signed repeated-pair evidence and confidence before the hard-decision threshold."""

        if self._frame_rms(frame_spectrum) < self._config.minimum_frame_rms:
            return None, None
        pair_scores: list[float] = []
        for pair_index, (first_bin, second_bin) in enumerate(
            self._pair_bins(lower_bin, upper_bin, frame_index)
        ):
            first_magnitude = float(abs(frame_spectrum[first_bin]))
            second_magnitude = float(abs(frame_spectrum[second_bin]))
            pair_energy = first_magnitude + second_magnitude
            if pair_energy < self._config.minimum_pair_magnitude:
                continue
            chip = self._pair_chip(frame_index, pair_index)
            pair_scores.append(
                chip * math.log((first_magnitude + self._config.minimum_pair_magnitude) / (second_magnitude + self._config.minimum_pair_magnitude))
            )
        if len(pair_scores) < self._config.minimum_pairs_per_frame:
            return None, None
        score = sum(pair_scores) / len(pair_scores)
        return score, abs(score)
