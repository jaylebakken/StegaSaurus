"""Expose reproducible evaluation transformations in research reading order.

Choose the narrowest grouped implementation module when extending behavior:

    `attack_core.signal`  - transparent PCM transformations
    `attack_core.codec`   - named external-tool round trips
    `attack_core.models`  - declared entropy bounds and recipe records
    `attack_core.profile` - recipe sampling and stochastic application

Toy example:
    recipe = EntropicAttackProfile().sample(audio.sample_rate, seed=42)
    attacked = EntropicAttackProfile().apply(audio, recipe)

Every attack result is conditional on its named parameters, source audio, and
tools. These utilities support measurement; they do not establish robustness
beyond the evaluations that explicitly record their outcomes.
"""

from .attack_core import (
    AudioToolUnavailable,
    EntropicAttackConfig,
    EntropicAttackProfile,
    EntropicAttackRecipe,
    add_reverberation,
    add_white_noise,
    concatenate_audio,
    low_pass_filter,
    normalize_peak,
    resample_audio,
    time_scale_audio,
    trim_audio,
    mp3_round_trip,
)

__all__ = [
    "AudioToolUnavailable",
    "EntropicAttackConfig",
    "EntropicAttackProfile",
    "EntropicAttackRecipe",
    "add_reverberation",
    "add_white_noise",
    "concatenate_audio",
    "low_pass_filter",
    "mp3_round_trip",
    "normalize_peak",
    "resample_audio",
    "time_scale_audio",
    "trim_audio",
]
