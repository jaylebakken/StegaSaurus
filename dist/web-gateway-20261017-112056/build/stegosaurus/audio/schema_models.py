"""Define the plain data contract for audio watermark decisions.

Background: the spectral layer observes uncertain frame bits, while this layer
only records configuration and results. Keeping these objects separate makes it
clear that statistical presence detection and attribution recovery are distinct.

Toy example:
    config = AudioWatermarkConfig(minimum_detection_frames=64)
    # A detector later returns AudioDetectionResult; no DSP occurs here.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import math

from .transport_models import ChannelRecovery

class AudioDetectionStatus(str, Enum):
    """Enumerate confidence states for the keyed statistical audio detector."""

    VERIFIED = "verified"
    INCONCLUSIVE = "inconclusive"
    ABSENT = "absent"


@dataclass(frozen=True, slots=True)
class AudioWatermarkConfig:
    """Configure token transport and statistical detection thresholds for audio frames."""

    attribution_token_bytes: int = 8
    parity_symbols: int = 8
    minimum_detection_frames: int = 32
    verification_p_value: float = 1e-4
    inconclusive_p_value: float = 0.05

    def __post_init__(self) -> None:
        """Validate fixed token length, Reed--Solomon parity, and ordered thresholds."""

        integer_fields = (
            ("attribution_token_bytes", self.attribution_token_bytes),
            ("parity_symbols", self.parity_symbols),
            ("minimum_detection_frames", self.minimum_detection_frames),
        )
        if any(isinstance(value, bool) or not isinstance(value, int) for _, value in integer_fields):
            raise TypeError("audio schema count settings must be integers")
        probability_fields = (self.verification_p_value, self.inconclusive_p_value)
        if any(
            isinstance(value, bool) or not isinstance(value, (int, float)) or not math.isfinite(value)
            for value in probability_fields
        ):
            raise TypeError("audio detection p-value thresholds must be finite numbers")
        if not 1 <= self.attribution_token_bytes <= 247:
            raise ValueError("attribution_token_bytes must be between 1 and 247")
        if not 1 <= self.parity_symbols < 255:
            raise ValueError("parity_symbols must be between 1 and 254")
        if self.attribution_token_bytes + self.parity_symbols > 255:
            raise ValueError("audio attribution codeword exceeds the Reed--Solomon limit")
        if self.minimum_detection_frames < 1:
            raise ValueError("minimum_detection_frames must be positive")
        if not 0 < self.verification_p_value <= self.inconclusive_p_value <= 1:
            raise ValueError("audio detection p-value thresholds are not ordered")


@dataclass(frozen=True, slots=True)
class AudioDetectionResult:
    """Report synchronized frame agreement, corrected significance, and a decision."""

    epoch: str
    observed_frames: int
    matching_frames: int
    tail_probability: float
    status: AudioDetectionStatus
    uncorrected_tail_probability: float | None = None
    p_value_multiplier: int = 1

    @property
    def matching_rate(self) -> float | None:
        """Return the keyed-pattern agreement rate when synchronized frames exist."""

        if not self.observed_frames:
            return None
        return self.matching_frames / self.observed_frames


@dataclass(frozen=True, slots=True)
class AudioAttributionResult:
    """Represent opaque-token recovery and its full channel diagnostics."""

    token: bytes | None
    channel_recovery: ChannelRecovery

    @property
    def recovered(self) -> bool:
        """Return whether a complete fixed-length attribution token was recovered."""

        return self.token is not None

