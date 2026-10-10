"""Embed and verify a claimed opaque handle through four retained STFT frame maps.

This is the compact v1 carrier implementation informed by the four-replica
transport experiments. It is intentionally a **map-retained verifier**:
``AttributionRecord`` supplies the exact frames selected during encoding. That
makes clean claimed-handle verification usable now, while avoiding a false claim
that blind map reconstruction is solved.

Pseudocode:
    handle -> RS/framed carrier bits -> four disjoint eligible frame spans
    record + received PCM -> four soft scores per carrier -> weighted combine
    combined bits/erasures -> claimed-codeword RS budget -> claim acceptance
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from .attribution_models import (
    AttributionEmbedding,
    AttributionRecord,
    AttributionStatus,
    AttributionVerification,
)
from .pilot import PcmAudio, SpectralAudioPilot


class AttributionCapacityError(ValueError):
    """Report a cover that cannot provide one eligible frame per carrier in every replica span."""


class FourReplicaAttributionCodec:
    """Repeat v1 carrier bits across four disjoint frame quarters and combine their soft evidence."""

    _replica_count = 4

    def __init__(self, pilot: SpectralAudioPilot, minimum_combined_confidence: float) -> None:
        """Initialize a configured pilot and the fixed confidence-to-erasure threshold."""

        if not 0 < minimum_combined_confidence < 1:
            raise ValueError("minimum_combined_confidence must be between zero and one")
        self._pilot = pilot
        self._minimum_combined_confidence = minimum_combined_confidence

    def embed(self, audio: PcmAudio, handle: bytes) -> AttributionEmbedding:
        """Embed a four-byte handle once per eligible frame span for all four replicas."""

        carrier_plan = self._pilot.schema.plan_attribution(handle)
        frequencies, spectrum = self._pilot._stft(audio)
        lower_bin, upper_bin = self._pilot._frequency_bin_range(frequencies)
        frame_maps = tuple(
            self._embed_replica(spectrum, frame_span, carrier_plan.carrier_bits, lower_bin, upper_bin)
            for frame_span in self._replica_ranges(spectrum.shape[1])
        )
        encoded_samples = self._pilot._inverse_stft(spectrum, audio)
        noise_samples = encoded_samples - audio.samples
        record = AttributionRecord(bytes(handle), carrier_plan, frame_maps, audio.sample_rate)
        return AttributionEmbedding(
            PcmAudio(encoded_samples, audio.sample_rate),
            record,
            self._pilot._signal_to_noise_db(audio.samples, noise_samples),
        )

    def verify(self, audio: PcmAudio, record: AttributionRecord) -> AttributionVerification:
        """Recover a retained-map claim from four score streams without guessing missing evidence."""

        if audio.sample_rate != record.sample_rate:
            return AttributionVerification(
                AttributionStatus.UNRECOVERABLE,
                record.handle,
                None,
                (),
                (),
                0,
                0,
                0,
                0,
                0,
                None,
                "received sample rate does not match the retained attribution record",
            )
        frequencies, spectrum = self._pilot._stft(audio)
        lower_bin, upper_bin = self._pilot._frequency_bin_range(frequencies)
        replica_scores = tuple(
            tuple(self._score_at_frame(spectrum, lower_bin, upper_bin, frame_index) for frame_index in frame_map)
            for frame_map in record.replica_frame_indices
        )
        carrier_count = len(record.carrier_plan.carrier_bits)
        combined_scores = tuple(
            self._combine_scores(replica_scores[replica_index][carrier_index] for replica_index in range(self._replica_count))
            for carrier_index in range(carrier_count)
        )
        observed_bits = tuple(
            None if score is None or abs(score) < self._minimum_combined_confidence else int(score >= 0)
            for score in combined_scores
        )
        recovery = self._pilot.schema.recover_attribution(observed_bits)
        expected_codeword = self._pilot.schema._channel.inspect_carrier_bits(
            record.carrier_plan.carrier_bits,
            record.carrier_plan.payload_length,
        )
        observed_codeword = self._pilot.schema._channel.inspect_carrier_bits(
            observed_bits,
            record.carrier_plan.payload_length,
        )
        erasure_positions = set(observed_codeword.erasure_positions)
        claim_symbol_errors = sum(
            byte_index not in erasure_positions
            and expected_codeword.codeword[byte_index] != observed_codeword.codeword[byte_index]
            for byte_index in range(len(expected_codeword.codeword))
        )
        claim_symbol_erasures = len(erasure_positions)
        claim_rs_cost = 2 * claim_symbol_errors + claim_symbol_erasures
        recovered_handle = recovery.token
        status = (
            AttributionStatus.RECOVERED
            if claim_rs_cost <= self._pilot.schema._channel.parity_symbols
            else AttributionStatus.MISMATCH
            if recovered_handle is not None
            else AttributionStatus.UNRECOVERABLE
        )
        known_bit_errors = sum(
            observed is not None and observed != expected
            for expected, observed in zip(record.carrier_plan.carrier_bits, observed_bits)
        )
        return AttributionVerification(
            status,
            record.handle,
            record.handle if status is AttributionStatus.RECOVERED else recovered_handle,
            observed_bits,
            combined_scores,
            known_bit_errors,
            sum(observed is None for observed in observed_bits),
            claim_symbol_errors,
            claim_symbol_erasures,
            claim_rs_cost,
            recovery,
            None if status is AttributionStatus.RECOVERED else recovery.channel_recovery.error,
        )

    @classmethod
    def _replica_ranges(cls, frame_count: int) -> tuple[range, ...]:
        """Partition STFT frames into four contiguous non-overlapping carrier spans."""

        boundaries = np.linspace(0, frame_count, cls._replica_count + 1, dtype=int)
        return tuple(range(int(boundaries[index]), int(boundaries[index + 1])) for index in range(cls._replica_count))

    def _embed_replica(
        self,
        spectrum: np.ndarray,
        frame_span: range,
        carrier_bits: tuple[int, ...],
        lower_bin: int,
        upper_bin: int,
    ) -> tuple[int, ...]:
        """Embed one ordered carrier plan into eligible frames in a single replica span."""

        selected_frames: list[int] = []
        for frame_index in frame_span:
            carrier_index = len(selected_frames)
            if carrier_index == len(carrier_bits):
                break
            if self._pilot._embed_frame(
                spectrum[:, frame_index], carrier_bits[carrier_index], lower_bin, upper_bin, frame_index
            ):
                selected_frames.append(frame_index)
        if len(selected_frames) != len(carrier_bits):
            raise AttributionCapacityError("cover lacks eligible frames for one four-replica attribution span")
        return tuple(selected_frames)

    def _score_at_frame(
        self, spectrum: np.ndarray, lower_bin: int, upper_bin: int, frame_index: int
    ) -> float | None:
        """Return raw signed frame evidence or an erasure when that mapped frame is unavailable."""

        if frame_index >= spectrum.shape[1]:
            return None
        score, _ = self._pilot._extract_frame_score(spectrum[:, frame_index], lower_bin, upper_bin, frame_index)
        return score

    @staticmethod
    def _combine_scores(scores: Iterable[float | None]) -> float | None:
        """Return an absolute-score-weighted signed average or an all-replica erasure."""

        available_scores = tuple(score for score in scores if score is not None)
        total_weight = sum(abs(score) for score in available_scores)
        if not total_weight:
            return None
        return sum(score * abs(score) for score in available_scores) / total_weight
