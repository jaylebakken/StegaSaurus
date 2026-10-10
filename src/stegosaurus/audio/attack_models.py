"""Describe replayable stochastic attack settings without transforming audio.

An entropic recipe records every sampled parameter and child seed. Separating
configuration from execution makes a benchmark result reproducible instead of
being an opaque random draw.

Toy example:
    recipe = EntropicAttackProfile().sample(sample_rate=16000, seed=7)
    print(recipe.name)
"""

from __future__ import annotations

from dataclasses import dataclass
from numbers import Integral, Real

import numpy as np

from .attack_signal import _finite_float

@dataclass(frozen=True, slots=True)
class EntropicAttackConfig:
    """Configure bounded, realistic parameter distributions for replayable audio attacks.

    The defaults model ordinary processing rather than an unconstrained adversary:
    sample-rate conversion, moderate bandwidth limits, light room response,
    additive noise, level changes, small timing changes, optional leading crop,
    and occasional MP3 transcoding. Every sampled value is retained in the
    resulting recipe so the word "entropy" never means an unreproducible test.
    """

    resample_probability: float = 0.70
    resample_rates: tuple[int, ...] = (8000, 12000, 16000, 22050, 44100, 48000)
    low_pass_probability: float = 0.35
    low_pass_cutoff_hz_range: tuple[float, float] = (3200.0, 7000.0)
    reverb_probability: float = 0.40
    reverb_mix_range: tuple[float, float] = (0.05, 0.22)
    reverb_decay_seconds_range: tuple[float, float] = (0.04, 0.20)
    time_scale_probability: float = 0.25
    speed_factor_range: tuple[float, float] = (0.97, 1.03)
    leading_trim_probability: float = 0.25
    leading_trim_seconds_range: tuple[float, float] = (0.0, 0.12)
    mp3_probability: float = 0.50
    mp3_bitrates_kbps: tuple[int, ...] = (64, 96, 128)
    noise_snr_db_range: tuple[float, float] = (24.0, 42.0)
    target_peak_range: tuple[float, float] = (0.65, 0.95)

    def __post_init__(self) -> None:
        """Validate all attack probabilities, choices, and continuous parameter ranges."""

        for name, probability in (
            ("resample_probability", self.resample_probability),
            ("low_pass_probability", self.low_pass_probability),
            ("reverb_probability", self.reverb_probability),
            ("time_scale_probability", self.time_scale_probability),
            ("leading_trim_probability", self.leading_trim_probability),
            ("mp3_probability", self.mp3_probability),
        ):
            self._validate_probability(probability, name)
        self._validate_integer_choices(self.resample_rates, "resample_rates", 1, None)
        self._validate_integer_choices(self.mp3_bitrates_kbps, "mp3_bitrates_kbps", 8, 320)
        self._validate_range(self.low_pass_cutoff_hz_range, "low_pass_cutoff_hz_range", 1.0, None)
        self._validate_range(self.reverb_mix_range, "reverb_mix_range", 0.0, 1.0)
        self._validate_range(
            self.reverb_decay_seconds_range,
            "reverb_decay_seconds_range",
            0.001,
            None,
        )
        self._validate_range(self.speed_factor_range, "speed_factor_range", 0.5, 2.0)
        self._validate_range(
            self.leading_trim_seconds_range,
            "leading_trim_seconds_range",
            0.0,
            None,
        )
        self._validate_range(self.noise_snr_db_range, "noise_snr_db_range", -300.0, 300.0)
        self._validate_range(self.target_peak_range, "target_peak_range", np.finfo(float).tiny, 1.0)

    @staticmethod
    def _validate_probability(value: Real, name: str) -> None:
        """Require one finite probability in the inclusive zero-to-one interval."""

        probability = _finite_float(value, name)
        if not 0 <= probability <= 1:
            raise ValueError(f"{name} must be between zero and one")

    @staticmethod
    def _validate_integer_choices(
        values: tuple[int, ...],
        name: str,
        minimum: int,
        maximum: int | None,
    ) -> None:
        """Require a non-empty tuple of unique bounded integer attack choices."""

        if not values:
            raise ValueError(f"{name} must not be empty")
        if any(isinstance(value, bool) or not isinstance(value, Integral) for value in values):
            raise TypeError(f"{name} must contain integers")
        if any(value < minimum or maximum is not None and value > maximum for value in values):
            upper_description = str(maximum) if maximum is not None else "infinity"
            raise ValueError(f"{name} must contain values between {minimum} and {upper_description}")
        if len(set(values)) != len(values):
            raise ValueError(f"{name} must not repeat values")

    @staticmethod
    def _validate_range(
        values: tuple[float, float],
        name: str,
        minimum: float,
        maximum: float | None,
    ) -> None:
        """Require an ordered finite numeric range within configured inclusive bounds."""

        if not isinstance(values, tuple) or len(values) != 2:
            raise TypeError(f"{name} must be a two-value tuple")
        lower_bound = _finite_float(values[0], name)
        upper_bound = _finite_float(values[1], name)
        if lower_bound > upper_bound:
            raise ValueError(f"{name} must be ordered")
        if lower_bound < minimum or maximum is not None and upper_bound > maximum:
            upper_description = str(maximum) if maximum is not None else "infinity"
            raise ValueError(f"{name} must remain between {minimum} and {upper_description}")


@dataclass(frozen=True, slots=True)
class EntropicAttackRecipe:
    """Record every sampled effect and seed needed to replay one stochastic attack trial."""

    seed: int
    resample_rate: int | None
    low_pass_cutoff_hz: float | None
    reverb_mix: float | None
    reverb_decay_seconds: float | None
    reverb_seed: int | None
    speed_factor: float
    leading_trim_seconds: float
    mp3_bitrate_kbps: int | None
    noise_snr_db: float
    noise_seed: int
    target_peak: float

    @property
    def name(self) -> str:
        """Return a stable benchmark label containing the root replay seed."""

        return f"entropy-{self.seed:016x}"
