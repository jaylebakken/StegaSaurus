"""Define the small records passed between attribution transport stages.

Carrier bits are deliberately tri-state: ``0`` and ``1`` are decisions, while
``None`` is an erasure. This lets uncertainty reach Reed--Solomon decoding
instead of being silently converted into a confident wrong bit.
"""

from __future__ import annotations

from dataclasses import dataclass

from .ecc import ErrorCorrectionError, ReedSolomonCodec


CarrierBit = int | None
_DEFAULT_SYNC_PATTERN = (1, 0, 1, 1, 0, 0, 1, 0)


@dataclass(frozen=True, slots=True)
class CarrierPlan:
    """Represent protected payload metadata and the required ordered carrier bits."""

    payload_length: int
    codeword_length: int
    carrier_bits: tuple[int, ...]


@dataclass(frozen=True, slots=True)
class FrameRecovery:
    """Represent deframed bits plus synchronization and length observations."""

    data_bits: tuple[CarrierBit, ...]
    synchronization_mismatches: int
    extra_carrier_bits: int


@dataclass(frozen=True, slots=True)
class SyncScanRecovery:
    """Represent scan-based deframing after local carrier insertion or deletion drift."""

    data_bits: tuple[CarrierBit, ...]
    synchronization_mismatches: int
    extra_carrier_bits: int
    frame_starts: tuple[int | None, ...]


@dataclass(frozen=True, slots=True)
class ChannelRecovery:
    """Represent a decoded payload or a recoverable-channel failure report."""

    payload: bytes | None
    corrected_positions: tuple[int, ...]
    erasure_positions: tuple[int, ...]
    synchronization_mismatches: int
    extra_carrier_bits: int
    error: str | None


@dataclass(frozen=True, slots=True)
class CodewordObservation:
    """Represent reconstructed Reed--Solomon bytes before error-correction decoding."""

    codeword: bytes
    erasure_positions: tuple[int, ...]
    synchronization_mismatches: int
    extra_carrier_bits: int

