"""Encode and verify repeated attribution blocks with pooled evidence.

Version 2 changes the unit of attribution from one whole-song carrier map to a
sequence of independent block-local watermarks. Each block carries the same
opaque registry handle, and verification can report both per-block votes and a
pooled Reed--Solomon decision across all block carrier scores.

Toy flow:
    song PCM -> 30 s chunks -> same handle embedded per chunk
    retained block records + received PCM -> block verifications
        -> score pooling by carrier index -> one pooled claim decision

This module is still a retained-record verifier. Blind window ranking and
non-oracle map reconstruction remain measured experiment paths until promoted
behind the same block record and pooling contracts.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .models import AttributionRecord, AttributionStatus, AttributionVerification, SpectralAttributionConfig
from .repetition import FourReplicaAttributionCodec
from ..pilot import PcmAudio, SpectralAudioPilot, SpectralPilotConfig
from ..schema import AudioWatermarkConfig
from ..transport import CarrierBit


@dataclass(frozen=True, slots=True)
class BlockAttributionRecord:
    """Retain the private records needed to verify a repeated-block attribution."""

    handle: bytes
    block_sample_count: int
    sample_rate: int
    block_records: tuple[AttributionRecord, ...]
    total_sample_count: int

    def __post_init__(self) -> None:
        """Validate repeated-block geometry and retained per-block records."""

        if len(self.handle) != 4:
            raise ValueError("v2 block attribution records require a four-byte handle")
        if self.block_sample_count < 1 or self.sample_rate < 1 or self.total_sample_count < 1:
            raise ValueError("block attribution sample counts must be positive")
        if not self.block_records:
            raise ValueError("block attribution requires at least one embedded block")
        if any(record.handle != self.handle for record in self.block_records):
            raise ValueError("all block records must carry the same handle")


@dataclass(frozen=True, slots=True)
class BlockAttributionEmbedding:
    """Return block-watermarked PCM and the retained v2 verification record."""

    audio: PcmAudio
    record: BlockAttributionRecord
    block_signal_to_noise_db: tuple[float, ...]


@dataclass(frozen=True, slots=True)
class BlockAttributionVerification:
    """Report per-block votes plus the pooled repeated-block attribution decision."""

    status: AttributionStatus
    claimed_handle: bytes
    recovered_handle: bytes | None
    block_verifications: tuple[AttributionVerification, ...]
    pooled_verification: AttributionVerification

    @property
    def recovered(self) -> bool:
        """Return whether pooled block evidence recovered the claimed handle."""

        return self.status is AttributionStatus.RECOVERED

    @property
    def recovered_block_count(self) -> int:
        """Return how many individual blocks independently recovered the claim."""

        return sum(verification.recovered for verification in self.block_verifications)


class BlockAttributionCodec:
    """Embed and verify one handle across repeated fixed-duration audio blocks."""

    def __init__(self, master_secret: bytes, config: SpectralAttributionConfig | None = None) -> None:
        """Initialize the v2 block codec from the fixed v1 spectral profile."""

        self._config = config or SpectralAttributionConfig()
        pilot = SpectralAudioPilot(
            master_secret,
            SpectralPilotConfig(
                minimum_frequency_hz=self._config.minimum_frequency_hz,
                maximum_frequency_hz=self._config.maximum_frequency_hz,
                relative_difference=self._config.relative_difference,
            ),
            AudioWatermarkConfig(
                attribution_token_bytes=self._config.handle_bytes,
                parity_symbols=self._config.parity_symbols,
            ),
        )
        self._pilot = pilot
        self._codec = FourReplicaAttributionCodec(pilot, self._config.minimum_combined_confidence)

    def embed(self, audio: PcmAudio, handle: bytes, block_seconds: float = 30.0) -> BlockAttributionEmbedding:
        """Embed the same handle into every complete block and preserve any trailing audio unchanged."""

        block_sample_count = self._block_sample_count(audio, block_seconds)
        full_block_count = len(audio.samples) // block_sample_count
        if full_block_count < 1:
            raise ValueError("audio must contain at least one complete attribution block")
        output = np.array(audio.samples, copy=True)
        records: list[AttributionRecord] = []
        snr_values: list[float] = []
        for index in range(full_block_count):
            start = index * block_sample_count
            stop = start + block_sample_count
            embedding = self._codec.embed(PcmAudio(output[start:stop], audio.sample_rate), handle)
            output[start:stop] = embedding.audio.samples
            records.append(embedding.record)
            snr_values.append(embedding.signal_to_noise_db)
        record = BlockAttributionRecord(bytes(handle), block_sample_count, audio.sample_rate, tuple(records), len(audio.samples))
        return BlockAttributionEmbedding(PcmAudio(output, audio.sample_rate), record, tuple(snr_values))

    def verify(self, audio: PcmAudio, record: BlockAttributionRecord) -> BlockAttributionVerification:
        """Verify retained block records and pool carrier evidence across available blocks."""

        if audio.sample_rate != record.sample_rate:
            pooled = self._unrecoverable(record.handle, "received sample rate does not match the retained block record")
            return BlockAttributionVerification(AttributionStatus.UNRECOVERABLE, record.handle, None, (), pooled)
        verifications: list[AttributionVerification] = []
        for index, block_record in enumerate(record.block_records):
            start = index * record.block_sample_count
            stop = start + record.block_sample_count
            if stop > len(audio.samples):
                break
            verifications.append(self._codec.verify(PcmAudio(audio.samples[start:stop], audio.sample_rate), block_record))
        if not verifications:
            pooled = self._unrecoverable(record.handle, "received audio contains no complete retained blocks")
            return BlockAttributionVerification(AttributionStatus.UNRECOVERABLE, record.handle, None, (), pooled)
        pooled = self._pool(record.handle, verifications)
        return BlockAttributionVerification(pooled.status, record.handle, pooled.recovered_handle, tuple(verifications), pooled)

    def _pool(self, handle: bytes, verifications: list[AttributionVerification]) -> AttributionVerification:
        """Pool combined carrier scores from block verifications into one claim decision."""

        carrier_count = len(verifications[0].combined_scores)
        pooled_scores = tuple(
            self._combine_scores(tuple(verification.combined_scores[index] for verification in verifications))
            for index in range(carrier_count)
        )
        observed_bits = tuple(
            None if score is None or abs(score) < self._config.minimum_combined_confidence else int(score >= 0)
            for score in pooled_scores
        )
        return self._verification_from_bits(handle, observed_bits, pooled_scores)

    def _verification_from_bits(
        self,
        handle: bytes,
        observed_bits: tuple[CarrierBit, ...],
        combined_scores: tuple[float | None, ...],
    ) -> AttributionVerification:
        """Build a claim-aware verification from pooled carrier bits."""

        recovery = self._pilot.schema.recover_attribution(observed_bits)
        plan = self._pilot.schema.plan_attribution(handle)
        expected = self._pilot.schema._channel.inspect_carrier_bits(plan.carrier_bits, plan.payload_length)
        observed = self._pilot.schema._channel.inspect_carrier_bits(observed_bits, plan.payload_length)
        erasures = set(observed.erasure_positions)
        symbol_errors = sum(
            index not in erasures and expected.codeword[index] != observed.codeword[index]
            for index in range(len(expected.codeword))
        )
        rs_cost = 2 * symbol_errors + len(erasures)
        recovered_handle = recovery.token
        status = (
            AttributionStatus.RECOVERED
            if rs_cost <= self._config.parity_symbols
            else AttributionStatus.MISMATCH
            if recovered_handle is not None
            else AttributionStatus.UNRECOVERABLE
        )
        return AttributionVerification(
            status,
            handle,
            handle if status is AttributionStatus.RECOVERED else recovered_handle,
            observed_bits,
            combined_scores,
            sum(bit is not None and bit != target for target, bit in zip(plan.carrier_bits, observed_bits)),
            sum(bit is None for bit in observed_bits),
            symbol_errors,
            len(erasures),
            rs_cost,
            recovery,
            None if status is AttributionStatus.RECOVERED else recovery.channel_recovery.error,
        )

    def _unrecoverable(self, handle: bytes, error: str) -> AttributionVerification:
        """Return an explicit pooled failure when block geometry is unavailable."""

        plan = self._pilot.schema.plan_attribution(handle)
        observed_bits = tuple(None for _ in plan.carrier_bits)
        verification = self._verification_from_bits(handle, observed_bits, tuple(None for _ in plan.carrier_bits))
        return AttributionVerification(
            AttributionStatus.UNRECOVERABLE,
            handle,
            None,
            verification.observed_carrier_bits,
            verification.combined_scores,
            verification.known_bit_errors,
            verification.carrier_erasures,
            verification.claim_symbol_errors,
            verification.claim_symbol_erasures,
            verification.claim_rs_cost,
            verification.recovery,
            error,
        )

    @staticmethod
    def _combine_scores(scores: tuple[float | None, ...]) -> float | None:
        """Combine block scores with absolute-score weighting."""

        available = tuple(score for score in scores if score is not None)
        total_weight = sum(abs(score) for score in available)
        if not total_weight:
            return None
        return sum(score * abs(score) for score in available) / total_weight

    @staticmethod
    def _block_sample_count(audio: PcmAudio, block_seconds: float) -> int:
        """Convert a positive block duration to a whole-sample block length."""

        if isinstance(block_seconds, bool) or block_seconds <= 0:
            raise ValueError("block_seconds must be positive")
        return int(round(audio.sample_rate * float(block_seconds)))

