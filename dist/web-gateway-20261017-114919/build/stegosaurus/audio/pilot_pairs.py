"""Choose keyed frequency-bin pairs and apply energy-preserving pair modulation.

Each frame derives pseudorandom bin pairs from the secret. A positive or
negative spreading chip determines which member becomes relatively stronger.
The pair total is preserved before phase is restored, which is a safeguard, not
a perceptual-quality guarantee.
"""

from __future__ import annotations

import hashlib
import hmac
import math

import numpy as np

from .pilot_types import AudioSamples


class SpectralPairMixin:
    """Provide secret-keyed pair selection and differential magnitude helpers."""

    def _pair_bins(self, lower_bin: int, upper_bin: int, frame_index: int) -> tuple[tuple[int, int], ...]:
        """Derive unique secret-keyed coefficient pairs for one frame within allowed bounds."""

        available_bin_count = upper_bin - lower_bin + 1
        pairs: list[tuple[int, int]] = []
        used_bins: set[int] = set()
        counter = 0
        while len(pairs) < self._config.pairs_per_frame:
            digest = hmac.new(
                self._carrier_secret,
                frame_index.to_bytes(8, "big") + counter.to_bytes(4, "big"),
                hashlib.sha256,
            ).digest()
            first_bin = lower_bin + int.from_bytes(digest[:8], "big") % available_bin_count
            second_bin = lower_bin + int.from_bytes(digest[8:16], "big") % available_bin_count
            counter += 1
            if first_bin == second_bin or first_bin in used_bins or second_bin in used_bins:
                continue
            used_bins.update((first_bin, second_bin))
            pairs.append((first_bin, second_bin))
        return tuple(pairs)

    def _pair_chip(self, frame_index: int, pair_index: int) -> float:
        """Return the secret pseudorandom plus-or-minus chip assigned to one pair."""

        digest = hmac.new(
            self._carrier_secret,
            b"chip|" + frame_index.to_bytes(8, "big") + pair_index.to_bytes(4, "big"),
            hashlib.sha256,
        ).digest()
        return 1.0 if digest[0] & 1 else -1.0

    @staticmethod
    def _modulated_pair_magnitudes(
        first_magnitude: float,
        second_magnitude: float,
        log_ratio_shift: float,
    ) -> tuple[float, float]:
        """Shift a pair log ratio while preserving its combined magnitude energy."""

        combined_magnitude = first_magnitude + second_magnitude
        if not combined_magnitude:
            return 0.0, 0.0
        minimum_magnitude = np.finfo(np.float64).tiny
        ratio = max(first_magnitude, minimum_magnitude) / max(second_magnitude, minimum_magnitude)
        shifted_ratio = ratio * math.exp(log_ratio_shift)
        second_result = combined_magnitude / (1.0 + shifted_ratio)
        return combined_magnitude - second_result, second_result

    @staticmethod
    def _with_magnitude(value: complex, magnitude: float) -> complex:
        """Return a complex value with preserved phase and a supplied non-negative magnitude."""

        if not magnitude:
            return 0j
        if not value:
            return complex(magnitude, 0.0)
        return value / abs(value) * magnitude
