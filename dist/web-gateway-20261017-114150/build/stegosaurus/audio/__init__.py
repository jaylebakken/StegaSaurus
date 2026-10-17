"""Expose audio schemas and directional PCM-WAV pilot entry points.

The package root exposes carrier-agnostic schema types without requiring optional
audio dependencies. ``encoder`` and ``detector`` expose the distinct WAV
encoding and presence-detection flows when the project is installed with its
``audio`` extra. The lower-level ``pilot`` module remains available for legacy
combined callers.
"""

from .schema import (
    AudioAttributionResult,
    AudioDetectionResult,
    AudioDetectionStatus,
    AudioWatermarkConfig,
    AudioWatermarkSchema,
)

__all__ = [
    "AudioAttributionResult",
    "AudioDetectionResult",
    "AudioDetectionStatus",
    "AudioWatermarkConfig",
    "AudioWatermarkSchema",
]
