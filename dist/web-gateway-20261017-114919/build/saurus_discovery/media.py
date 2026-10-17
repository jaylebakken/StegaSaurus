"""Bound public media bytes before any discovery matching stage.

The worker accepts already-fetched bytes from an approved connector pipeline and
extracts conservative PCM WAV metadata for review and later fingerprinting. It
rejects oversize inputs, archive-like payloads, unsupported media, and audio
outside declared duration limits. It does not execute downloaded files, launch
codecs, or claim open-web recognition quality.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
from io import BytesIO
import wave


@dataclass(frozen=True, slots=True)
class MediaLimits:
    """Declare byte and duration budgets for one media worker job."""

    max_bytes: int = 25_000_000
    max_seconds: float = 180.0
    allowed_mime_types: tuple[str, ...] = ("audio/wav", "audio/x-wav")

    def __post_init__(self) -> None:
        """Validate positive worker limits."""

        if self.max_bytes < 1 or self.max_seconds <= 0:
            raise ValueError("media limits must be positive")
        if not self.allowed_mime_types:
            raise ValueError("allowed_mime_types must not be empty")


@dataclass(frozen=True, slots=True)
class DecodedMedia:
    """Summarize bounded public audio suitable for candidate matching."""

    mime_type: str
    content_digest: str
    sample_rate: int
    channel_count: int
    sample_width_bytes: int
    frame_count: int
    duration_seconds: float


def decode_public_media(payload: bytes, declared_mime_type: str, limits: MediaLimits | None = None) -> DecodedMedia:
    """Validate and decode bounded PCM WAV metadata from public media bytes."""

    active_limits = limits or MediaLimits()
    if len(payload) > active_limits.max_bytes:
        raise ValueError("media payload exceeds byte limit")
    if _looks_like_archive(payload):
        raise ValueError("archive media payloads are not accepted")
    sniffed = _sniff_mime(payload, declared_mime_type)
    if sniffed not in active_limits.allowed_mime_types:
        raise ValueError("media MIME type is not accepted")
    try:
        with wave.open(BytesIO(payload), "rb") as source:
            channel_count = source.getnchannels()
            sample_width = source.getsampwidth()
            sample_rate = source.getframerate()
            frame_count = source.getnframes()
    except wave.Error as error:
        raise ValueError(f"media payload is not a supported PCM WAV: {error}") from error
    if channel_count < 1 or sample_width != 2 or sample_rate < 1:
        raise ValueError("media WAV geometry is not supported")
    duration = frame_count / sample_rate
    if duration > active_limits.max_seconds:
        raise ValueError("media payload exceeds duration limit")
    return DecodedMedia(sniffed, hashlib.sha256(payload).hexdigest(), sample_rate, channel_count, sample_width, frame_count, duration)


def _sniff_mime(payload: bytes, declared_mime_type: str) -> str:
    """Trust only a small RIFF/WAVE signature, then normalize declared type."""

    if payload.startswith(b"RIFF") and payload[8:12] == b"WAVE":
        return "audio/wav"
    return declared_mime_type.lower().strip()


def _looks_like_archive(payload: bytes) -> bool:
    """Reject common archive signatures before media parsing."""

    return payload.startswith((b"PK\x03\x04", b"Rar!\x1a\x07\x00", b"7z\xbc\xaf\x27\x1c", b"\x1f\x8b"))
