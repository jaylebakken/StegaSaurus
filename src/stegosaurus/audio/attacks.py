"""Expose reproducible evaluation transformations in research reading order.

Choose the narrowest component that matches the question:

    `attack_signal`  - transparent PCM transformations such as noise or filters
    `attack_codec`   - a named FFmpeg-backed MP3 round trip
    `attack_models`  - declared entropy bounds and replayable recipe records
    `attack_profile` - recipe sampling and ordered stochastic application

Toy example:
    recipe = EntropicAttackProfile().sample(audio.sample_rate, seed=42)
    attacked = EntropicAttackProfile().apply(audio, recipe)

Every attack result is conditional on its named parameters, source audio, and
tools. These utilities support measurement; they do not establish robustness
beyond the evaluations that explicitly record their outcomes.
"""

from .attack_codec import AudioToolUnavailable, mp3_round_trip
from .attack_models import EntropicAttackConfig, EntropicAttackRecipe
from .attack_profile import EntropicAttackProfile
from .attack_signal import (
    add_reverberation,
    add_white_noise,
    concatenate_audio,
    low_pass_filter,
    normalize_peak,
    resample_audio,
    time_scale_audio,
    trim_audio,
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
