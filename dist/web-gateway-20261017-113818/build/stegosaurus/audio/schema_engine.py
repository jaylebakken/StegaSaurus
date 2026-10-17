"""Coordinate secret-keyed detector bits and protected attribution transport.

Intent: this carrier-agnostic policy layer derives expected detector bits,
applies a corrected significance test, and delegates opaque token protection
to transport. An audio DSP implementation supplies the frame observations.

Toy flow:
    schema = AudioWatermarkSchema(secret)
    expected = schema.detection_bits("2026-10-09", frame_count=64)
    result = schema.detect("2026-10-09", observed_bits)

This module does not embed audio and makes no robustness claim by itself.
"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date, datetime
import hashlib
import hmac
import math

from .ecc import ReedSolomonCodec
from .schema_models import (
    AudioAttributionResult,
    AudioDetectionResult,
    AudioDetectionStatus,
    AudioWatermarkConfig,
)
from .transport import CarrierBit, CarrierPlan, KeyedBitInterleaver, ReedSolomonChannel

class AudioWatermarkSchema:
    """Coordinate secret-keyed audio detection frames and opaque-token attribution bits."""

    def __init__(
        self,
        master_secret: bytes,
        config: AudioWatermarkConfig | None = None,
    ) -> None:
        """Initialize domain-separated detection and attribution keys from one master secret."""

        normalized_secret = self._normalize_bytes(master_secret, "master_secret")
        if not normalized_secret:
            raise ValueError("master_secret must not be empty")
        self._master_secret = normalized_secret
        self._config = config or AudioWatermarkConfig()
        self._channel = ReedSolomonChannel(
            ReedSolomonCodec(self._config.parity_symbols),
            KeyedBitInterleaver(self._derive_key(b"attribution")),
        )

    @property
    def attribution_token_bytes(self) -> int:
        """Return the exact opaque-token length accepted by the attribution channel."""

        return self._config.attribution_token_bytes

    @property
    def attribution_carrier_bits(self) -> int:
        """Return the exact carrier-bit count required for one attribution token."""

        return self._channel.carrier_bit_count(self.attribution_token_bytes)

    def detection_bits(
        self,
        frame_count: int,
        epoch: date | datetime | str,
        frame_offset: int = 0,
    ) -> tuple[int, ...]:
        """Return epoch-keyed expected bits for synchronized audio frame positions."""

        if frame_count < 0:
            raise ValueError("frame_count must not be negative")
        if frame_offset < 0:
            raise ValueError("frame_offset must not be negative")
        epoch_key = self._derive_key(b"detection|" + self._normalize_epoch(epoch).encode("ascii"))
        return tuple(
            hmac.new(
                epoch_key,
                (frame_offset + frame_index).to_bytes(8, "big"),
                hashlib.sha256,
            ).digest()[0]
            & 1
            for frame_index in range(frame_count)
        )

    def detect(
        self,
        observed_frame_bits: Sequence[CarrierBit],
        epoch: date | datetime | str,
        frame_offset: int = 0,
        p_value_multiplier: int = 1,
    ) -> AudioDetectionResult:
        """Score synchronized frame agreement with optional multiple-offset correction."""

        if isinstance(p_value_multiplier, bool) or not isinstance(p_value_multiplier, int):
            raise TypeError("p_value_multiplier must be an integer")
        if p_value_multiplier < 1:
            raise ValueError("p_value_multiplier must be positive")
        observed_bits = self._validate_frame_bits(observed_frame_bits)
        expected_bits = self.detection_bits(len(observed_bits), epoch, frame_offset)
        confident_pairs = tuple(
            (expected_bit, observed_bit)
            for expected_bit, observed_bit in zip(expected_bits, observed_bits)
            if observed_bit is not None
        )
        matching_frames = sum(expected_bit == observed_bit for expected_bit, observed_bit in confident_pairs)
        uncorrected_tail_probability = self._binomial_tail_probability(
            len(confident_pairs),
            matching_frames,
        )
        tail_probability = self._adjust_tail_probability(
            uncorrected_tail_probability,
            p_value_multiplier,
        )
        return AudioDetectionResult(
            self._normalize_epoch(epoch),
            len(confident_pairs),
            matching_frames,
            tail_probability,
            self._status_for(len(confident_pairs), tail_probability),
            uncorrected_tail_probability,
            p_value_multiplier,
        )

    def plan_attribution(self, token: bytes) -> CarrierPlan:
        """Encode one fixed-length opaque ledger token into audio carrier bits."""

        normalized_token = self._normalize_bytes(token, "token")
        if len(normalized_token) != self._config.attribution_token_bytes:
            raise ValueError("token length does not match the configured audio schema")
        return self._channel.plan(normalized_token)

    def recover_attribution(self, observed_carrier_bits: Sequence[CarrierBit]) -> AudioAttributionResult:
        """Recover the fixed-length token from observed audio attribution carrier bits."""

        recovery = self._channel.recover(
            observed_carrier_bits,
            self._config.attribution_token_bytes,
        )
        return AudioAttributionResult(recovery.payload, recovery)

    def _derive_key(self, label: bytes) -> bytes:
        """Derive a domain-separated keyed-material value from the master secret."""

        return hmac.new(self._master_secret, b"stegosaurus-audio-v1|" + label, hashlib.sha256).digest()

    @staticmethod
    def _normalize_epoch(epoch: date | datetime | str) -> str:
        """Normalize a date, datetime, or ISO date string into a stable daily epoch."""

        if isinstance(epoch, datetime):
            return epoch.date().isoformat()
        if isinstance(epoch, date):
            return epoch.isoformat()
        try:
            return date.fromisoformat(epoch).isoformat()
        except (TypeError, ValueError) as error:
            raise ValueError("epoch must be a date, datetime, or ISO date string") from error

    @staticmethod
    def _validate_frame_bits(frame_bits: Sequence[CarrierBit]) -> tuple[CarrierBit, ...]:
        """Validate binary or missing synchronized frame observations."""

        normalized_bits = tuple(frame_bits)
        if any(bit is not None and (type(bit) is not int or bit not in (0, 1)) for bit in normalized_bits):
            raise ValueError("audio frame bits must contain 0, 1, or None")
        return normalized_bits

    @staticmethod
    def _binomial_tail_probability(trials: int, successes: int) -> float:
        """Return the one-sided null probability of at least successes random matches."""

        if trials < 0 or not 0 <= successes <= trials:
            raise ValueError("binomial successes must be between zero and trials")
        if successes == 0:
            return 1.0
        if successes > trials // 2:
            return AudioWatermarkSchema._sum_binomial_tail(trials, successes)
        lower_tail = AudioWatermarkSchema._sum_binomial_lower_tail(trials, successes - 1)
        return min(1.0, max(0.0, 1.0 - lower_tail))

    @staticmethod
    def _adjust_tail_probability(tail_probability: float, multiplier: int) -> float:
        """Apply a Bonferroni multiplier without overflowing for large search counts."""

        if not tail_probability or multiplier == 1:
            return tail_probability
        if multiplier > 1.0 / tail_probability:
            return 1.0
        return tail_probability * multiplier

    @staticmethod
    def _sum_binomial_tail(trials: int, first_successes: int) -> float:
        """Sum a high-side fair-binomial tail from its largest probability mass."""

        log_probability = AudioWatermarkSchema._log_binomial_probability(trials, first_successes)
        probability = math.exp(log_probability)
        total = probability
        for successes in range(first_successes, trials):
            probability *= (trials - successes) / (successes + 1)
            total += probability
        return min(1.0, total)

    @staticmethod
    def _sum_binomial_lower_tail(trials: int, last_successes: int) -> float:
        """Sum a low-side fair-binomial tail from its largest probability mass."""

        if last_successes < 0:
            return 0.0
        log_probability = AudioWatermarkSchema._log_binomial_probability(trials, last_successes)
        probability = math.exp(log_probability)
        total = probability
        for successes in range(last_successes, 0, -1):
            probability *= successes / (trials - successes + 1)
            total += probability
        return min(1.0, total)

    @staticmethod
    def _log_binomial_probability(trials: int, successes: int) -> float:
        """Return the log probability of a fair-binomial success count."""

        return (
            math.lgamma(trials + 1)
            - math.lgamma(successes + 1)
            - math.lgamma(trials - successes + 1)
            - trials * math.log(2)
        )

    @staticmethod
    def _normalize_bytes(value: bytes, field_name: str) -> bytes:
        """Accept explicit bytes-like secret material while rejecting accidental coercions."""

        if not isinstance(value, (bytes, bytearray, memoryview)):
            raise TypeError(f"{field_name} must be bytes-like")
        return bytes(value)

    def _status_for(self, observed_frames: int, tail_probability: float) -> AudioDetectionStatus:
        """Classify frame evidence using configured count and p-value thresholds."""

        if observed_frames < self._config.minimum_detection_frames:
            return AudioDetectionStatus.INCONCLUSIVE
        if tail_probability <= self._config.verification_p_value:
            return AudioDetectionStatus.VERIFIED
        if tail_probability <= self._config.inconclusive_p_value:
            return AudioDetectionStatus.INCONCLUSIVE
        return AudioDetectionStatus.ABSENT
