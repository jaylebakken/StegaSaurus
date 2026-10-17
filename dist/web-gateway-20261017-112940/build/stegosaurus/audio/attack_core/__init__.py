"""Group audio attack and distortion helpers by task.

The public ``stegosaurus.audio.attacks`` facade re-exports these objects. This
package keeps codec round-trips, deterministic signal transforms, attack recipe
records, and randomized attack profiles together.
"""

from __future__ import annotations

from .codec import AudioToolUnavailable, mp3_round_trip
from .models import EntropicAttackConfig, EntropicAttackRecipe
from .profile import EntropicAttackProfile
from .signal import (
    add_white_noise,
    add_reverberation,
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
    "add_white_noise",
    "add_reverberation",
    "concatenate_audio",
    "low_pass_filter",
    "mp3_round_trip",
    "normalize_peak",
    "resample_audio",
    "time_scale_audio",
    "trim_audio",
]

