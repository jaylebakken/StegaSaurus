"""Define the bounded v1 spectral-attribution contract and its diagnostics.

Version 1 is a **claimed-handle verifier**. The encoder embeds a four-byte
opaque registry handle with sixteen Reed--Solomon parity symbols and preserves a
private frame map in an ``AttributionRecord``. A verifier receives that record
after a claimant supplies a handle; it then proves or rejects that specific
claim. This is deliberately different from blind watermark discovery.

Pseudocode:
    registry handle + PCM -> embedded PCM + retained carrier-frame map
    claimed handle + retained map + received PCM -> recovered | mismatch | unrecoverable

The profile reflects named synthetic experiments only. It is not a claim about
recorded audio, arbitrary crops, codecs, DSP, or perceptual transparency.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from ..pilot import PcmAudio
from ..schema import AudioAttributionResult
from ..transport import CarrierBit, CarrierPlan


class AttributionStatus(str, Enum):
    """Classify a claimed-handle verification outcome without hiding decoder uncertainty."""

    RECOVERED = "recovered"
    MISMATCH = "mismatch"
    UNRECOVERABLE = "unrecoverable"


@dataclass(frozen=True, slots=True)
class SpectralAttributionConfig:
    """Freeze the v1 profile selected by the non-oracle allocation experiments."""

    handle_bytes: int = 4
    parity_symbols: int = 16
    replica_count: int = 4
    minimum_combined_confidence: float = 0.01
    minimum_frequency_hz: float = 500.0
    maximum_frequency_hz: float = 3800.0
    relative_difference: float = 0.95

    def __post_init__(self) -> None:
        """Reject unvalidated profile changes instead of silently treating them as v1 evidence."""

        expected_values = (4, 16, 4, 0.01, 500.0, 3800.0, 0.95)
        actual_values = (
            self.handle_bytes,
            self.parity_symbols,
            self.replica_count,
            self.minimum_combined_confidence,
            self.minimum_frequency_hz,
            self.maximum_frequency_hz,
            self.relative_difference,
        )
        if actual_values != expected_values:
            raise ValueError("v1 attribution uses the fixed 4-byte, 16-parity evaluated profile")


@dataclass(frozen=True, slots=True)
class AttributionRecord:
    """Store the private carrier map required to verify one asserted opaque handle."""

    handle: bytes
    carrier_plan: CarrierPlan
    replica_frame_indices: tuple[tuple[int, ...], ...]
    sample_rate: int

    def __post_init__(self) -> None:
        """Validate the private claimed-handle verification record before registry retention."""

        if len(self.handle) != 4:
            raise ValueError("v1 attribution records require a four-byte handle")
        if self.sample_rate < 1:
            raise ValueError("record sample_rate must be positive")
        if len(self.replica_frame_indices) != 4:
            raise ValueError("v1 attribution records require four replica frame maps")
        carrier_count = len(self.carrier_plan.carrier_bits)
        if any(len(frame_map) != carrier_count for frame_map in self.replica_frame_indices):
            raise ValueError("each replica frame map must match the carrier plan")


@dataclass(frozen=True, slots=True)
class AttributionEmbedding:
    """Return watermarked PCM plus the private record a registry must retain for a claim."""

    audio: PcmAudio
    record: AttributionRecord
    signal_to_noise_db: float


@dataclass(frozen=True, slots=True)
class AttributionVerification:
    """Report claim-aware handle verification, carrier evidence, and generic channel diagnostics."""

    status: AttributionStatus
    claimed_handle: bytes
    recovered_handle: bytes | None
    observed_carrier_bits: tuple[CarrierBit, ...]
    combined_scores: tuple[float | None, ...]
    known_bit_errors: int
    carrier_erasures: int
    claim_symbol_errors: int
    claim_symbol_erasures: int
    claim_rs_cost: int
    recovery: AudioAttributionResult | None
    error: str | None

    @property
    def recovered(self) -> bool:
        """Return whether the supplied handle passed the claim-aware Reed--Solomon budget check."""

        return self.status is AttributionStatus.RECOVERED
