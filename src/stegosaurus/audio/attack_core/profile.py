"""Sample and apply fully recorded stochastic attack recipes.

Pseudocode:
    root seed -> declared parameter ranges -> recipe with child seeds
    recipe + PCM -> ordered signal/codec operations -> transformed PCM

Replay depends on preserving the recipe, source PCM, and external codec version.
This component broadens a declared test distribution; it cannot prove resilience
outside that distribution.
"""

from __future__ import annotations

from numbers import Integral

import numpy as np

from .codec import mp3_round_trip
from .models import EntropicAttackConfig, EntropicAttackRecipe
from .signal import (
    add_reverberation,
    add_white_noise,
    low_pass_filter,
    normalize_peak,
    resample_audio,
    time_scale_audio,
    trim_audio,
)
from ..pilot import PcmAudio

class EntropicAttackProfile:
    """Sample and apply replayable, bounded stochastic audio-processing attack chains."""

    def __init__(self, config: EntropicAttackConfig | None = None) -> None:
        """Initialize the profile with explicit distributions or conservative default bounds."""

        self._config = config or EntropicAttackConfig()

    @property
    def config(self) -> EntropicAttackConfig:
        """Return the immutable distribution configuration used for future recipes."""

        return self._config

    def sample(self, sample_rate: int, seed: int) -> EntropicAttackRecipe:
        """Sample one audio-rate-aware recipe from a supplied integer replay seed."""

        self._validate_seed(seed)
        if isinstance(sample_rate, bool) or not isinstance(sample_rate, Integral) or sample_rate < 1:
            raise ValueError("sample_rate must be a positive integer")
        random_generator = np.random.default_rng(seed)
        candidate_rates = tuple(rate for rate in self._config.resample_rates if rate != sample_rate)
        resample_rate = (
            self._sample_choice(random_generator, candidate_rates)
            if candidate_rates and self._sample_event(random_generator, self._config.resample_probability)
            else None
        )
        maximum_cutoff = min(self._config.low_pass_cutoff_hz_range[1], sample_rate * 0.45)
        minimum_cutoff = min(self._config.low_pass_cutoff_hz_range[0], maximum_cutoff)
        low_pass_cutoff_hz = (
            self._sample_float(random_generator, (minimum_cutoff, maximum_cutoff))
            if minimum_cutoff < maximum_cutoff
            and self._sample_event(random_generator, self._config.low_pass_probability)
            else None
        )
        reverb_enabled = self._sample_event(random_generator, self._config.reverb_probability)
        reverb_mix = (
            self._sample_float(random_generator, self._config.reverb_mix_range) if reverb_enabled else None
        )
        reverb_decay_seconds = (
            self._sample_float(random_generator, self._config.reverb_decay_seconds_range)
            if reverb_enabled
            else None
        )
        reverb_seed = self._sample_seed(random_generator) if reverb_enabled else None
        speed_factor = (
            self._sample_float(random_generator, self._config.speed_factor_range)
            if self._sample_event(random_generator, self._config.time_scale_probability)
            else 1.0
        )
        leading_trim_seconds = (
            self._sample_float(random_generator, self._config.leading_trim_seconds_range)
            if self._sample_event(random_generator, self._config.leading_trim_probability)
            else 0.0
        )
        mp3_bitrate_kbps = (
            self._sample_choice(random_generator, self._config.mp3_bitrates_kbps)
            if self._sample_event(random_generator, self._config.mp3_probability)
            else None
        )
        return EntropicAttackRecipe(
            seed,
            resample_rate,
            low_pass_cutoff_hz,
            reverb_mix,
            reverb_decay_seconds,
            reverb_seed,
            speed_factor,
            leading_trim_seconds,
            mp3_bitrate_kbps,
            self._sample_float(random_generator, self._config.noise_snr_db_range),
            self._sample_seed(random_generator),
            self._sample_float(random_generator, self._config.target_peak_range),
        )

    def sample_many(self, sample_rate: int, trial_count: int, seed: int) -> tuple[EntropicAttackRecipe, ...]:
        """Derive distinct replay recipes for a fixed number of trials from one root seed."""

        self._validate_seed(seed)
        if isinstance(trial_count, bool) or not isinstance(trial_count, Integral) or trial_count < 1:
            raise ValueError("trial_count must be a positive integer")
        random_generator = np.random.default_rng(seed)
        return tuple(
            self.sample(sample_rate, self._sample_seed(random_generator))
            for _ in range(trial_count)
        )

    def apply(self, audio: PcmAudio, recipe: EntropicAttackRecipe) -> PcmAudio:
        """Apply one recorded recipe in a fixed order and return its transformed waveform."""

        if not isinstance(recipe, EntropicAttackRecipe):
            raise TypeError("recipe must be an EntropicAttackRecipe")
        transformed_audio = audio
        if recipe.resample_rate is not None:
            transformed_audio = resample_audio(transformed_audio, recipe.resample_rate)
            transformed_audio = resample_audio(transformed_audio, audio.sample_rate)
        if recipe.low_pass_cutoff_hz is not None:
            transformed_audio = low_pass_filter(transformed_audio, recipe.low_pass_cutoff_hz)
        if recipe.reverb_mix is not None:
            transformed_audio = add_reverberation(
                transformed_audio,
                recipe.reverb_decay_seconds or 0.0,
                recipe.reverb_mix,
                recipe.reverb_seed or 0,
            )
        if recipe.speed_factor != 1.0:
            transformed_audio = time_scale_audio(transformed_audio, recipe.speed_factor)
        if recipe.leading_trim_seconds:
            transformed_audio = self._trim_leading_audio(transformed_audio, recipe.leading_trim_seconds)
        transformed_audio = add_white_noise(transformed_audio, recipe.noise_snr_db, recipe.noise_seed)
        transformed_audio = normalize_peak(transformed_audio, recipe.target_peak)
        if recipe.mp3_bitrate_kbps is not None:
            transformed_audio = mp3_round_trip(transformed_audio, recipe.mp3_bitrate_kbps)
        return transformed_audio

    @staticmethod
    def _trim_leading_audio(audio: PcmAudio, trim_seconds: float) -> PcmAudio:
        """Trim a bounded leading interval while always retaining at least one audio sample."""

        maximum_trim = max(0.0, audio.duration_seconds - 1 / audio.sample_rate)
        effective_trim = min(trim_seconds, maximum_trim)
        if not effective_trim:
            return audio
        return trim_audio(audio, effective_trim, audio.duration_seconds)

    @staticmethod
    def _sample_event(random_generator: np.random.Generator, probability: float) -> bool:
        """Return a Bernoulli decision from one configured probability."""

        return bool(random_generator.random() < probability)

    @staticmethod
    def _sample_float(random_generator: np.random.Generator, bounds: tuple[float, float]) -> float:
        """Sample one inclusive-endpoint-compatible finite float from an ordered range."""

        lower_bound, upper_bound = bounds
        if lower_bound == upper_bound:
            return lower_bound
        return float(random_generator.uniform(lower_bound, upper_bound))

    @staticmethod
    def _sample_choice(random_generator: np.random.Generator, choices: tuple[int, ...]) -> int:
        """Sample one integer choice while preserving the declared option type."""

        return int(random_generator.choice(choices))

    @staticmethod
    def _sample_seed(random_generator: np.random.Generator) -> int:
        """Derive one nonnegative 63-bit child seed for a nested stochastic component."""

        return int(random_generator.integers(0, np.iinfo(np.int64).max, dtype=np.int64))

    @staticmethod
    def _validate_seed(seed: int) -> None:
        """Require a nonnegative integer seed so every recipe remains replayable."""

        if isinstance(seed, bool) or not isinstance(seed, Integral) or seed < 0:
            raise ValueError("seed must be a nonnegative integer")

