"""Run iteration 004: four-frame soft combining for opaque-token carrier bits.

Experiment goal: determine whether placing every framed/interleaved token bit in
four disjoint STFT-frame quarters, then combining all signed observations, can
recover the clean 8-byte token protected by eight Reed--Solomon parity bytes.
The experiment sweeps a post-combination confidence threshold so weak evidence
becomes a declared erasure rather than an unknown bit error.

Pipeline state: iteration 003 tested two time-separated copies on a 30-second
synthetic music-like fixture. Its best clean setting still had 17 known carrier
bit errors, so Reed--Solomon recovery failed. Detection remains a separate,
working statistical pilot. This attribution experiment is oracle aligned: the
extractor receives the source-frame map and therefore does not solve temporal
alignment after cropping, insertion, deletion, or time scaling.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
import json

import numpy as np

from ....pilot import PcmAudio, SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioAttributionResult
from ....transport import CarrierBit, CarrierPlan


class FourFrameCapacityError(ValueError):
    """Report a cover signal that cannot supply four disjoint carrier-frame spans."""


@dataclass(frozen=True, slots=True)
class FourFrameEmbedding:
    """Record the repeated plan, its four oracle frame maps, and signal quality."""

    audio: PcmAudio
    carrier_plan: CarrierPlan
    token: bytes
    replica_frame_indices: tuple[tuple[int, ...], ...]
    signal_to_noise_db: float


@dataclass(frozen=True, slots=True)
class FourFrameExtraction:
    """Record replica evidence, combined decisions, and attribution recovery output."""

    replica_scores: tuple[tuple[float | None, ...], ...]
    combined_scores: tuple[float | None, ...]
    observed_carrier_bits: tuple[CarrierBit, ...]
    known_bit_errors: int
    carrier_erasures: int
    recovery: AudioAttributionResult
    token_matches_input: bool

    @property
    def recovered(self) -> bool:
        """Return whether the full opaque token was recovered from combined evidence."""

        return self.token_matches_input


class FourFrameSoftCombineExperiment:
    """Repeat each carrier bit across four waveform quarters and combine signed evidence."""

    _replica_count = 4

    def __init__(self, pilot: SpectralAudioPilot, minimum_combined_confidence: float) -> None:
        """Initialize a fixed pilot and confidence-to-erasure threshold for one extraction pass."""

        if not 0 < minimum_combined_confidence < 1:
            raise ValueError("minimum_combined_confidence must be between zero and one")
        self._pilot = pilot
        self._minimum_combined_confidence = minimum_combined_confidence

    def embed(self, audio: PcmAudio, token: bytes) -> FourFrameEmbedding:
        """Embed each planned carrier bit once in each of four disjoint frame quarters."""

        carrier_plan = self._pilot.schema.plan_attribution(token)
        frequencies, spectrum = self._pilot._stft(audio)
        lower_bin, upper_bin = self._pilot._frequency_bin_range(frequencies)
        replica_ranges = self._replica_ranges(spectrum.shape[1])
        replica_frame_indices = tuple(
            self._embed_copy(
                spectrum,
                frame_indices,
                carrier_plan.carrier_bits,
                lower_bin,
                upper_bin,
            )
            for frame_indices in replica_ranges
        )
        encoded_samples = self._pilot._inverse_stft(spectrum, audio)
        noise_samples = encoded_samples - audio.samples
        return FourFrameEmbedding(
            PcmAudio(encoded_samples, audio.sample_rate),
            carrier_plan,
            bytes(token),
            replica_frame_indices,
            self._pilot._signal_to_noise_db(audio.samples, noise_samples),
        )

    def extract(self, audio: PcmAudio, embedding: FourFrameEmbedding) -> FourFrameExtraction:
        """Combine four oracle-aligned score streams into carrier bits and recover the token."""

        expected_carrier_count = len(embedding.carrier_plan.carrier_bits)
        if len(embedding.replica_frame_indices) != self._replica_count:
            raise ValueError("replica map count does not match four-frame repetition")
        if any(len(frame_map) != expected_carrier_count for frame_map in embedding.replica_frame_indices):
            raise ValueError("replica frame map does not match the carrier plan")
        frequencies, spectrum = self._pilot._stft(audio)
        lower_bin, upper_bin = self._pilot._frequency_bin_range(frequencies)
        replica_scores = tuple(
            tuple(
                self._score_at_frame(spectrum, lower_bin, upper_bin, frame_index)
                for frame_index in frame_map
            )
            for frame_map in embedding.replica_frame_indices
        )
        combined_scores = tuple(
            self._combine_scores(replica_scores[replica_index][carrier_index] for replica_index in range(self._replica_count))
            for carrier_index in range(expected_carrier_count)
        )
        observed_bits = tuple(
            None
            if score is None or abs(score) < self._minimum_combined_confidence
            else int(score >= 0)
            for score in combined_scores
        )
        recovery = self._pilot.schema.recover_attribution(observed_bits)
        known_bit_errors = sum(
            observed_bit is not None and observed_bit != target_bit
            for target_bit, observed_bit in zip(embedding.carrier_plan.carrier_bits, observed_bits)
        )
        return FourFrameExtraction(
            replica_scores,
            combined_scores,
            observed_bits,
            known_bit_errors,
            sum(observed_bit is None for observed_bit in observed_bits),
            recovery,
            recovery.token == embedding.token,
        )

    @classmethod
    def _replica_ranges(cls, frame_count: int) -> tuple[range, ...]:
        """Partition STFT frame indices into four contiguous, non-overlapping replica spans."""

        boundaries = np.linspace(0, frame_count, cls._replica_count + 1, dtype=int)
        return tuple(
            range(int(boundaries[index]), int(boundaries[index + 1]))
            for index in range(cls._replica_count)
        )

    def _embed_copy(
        self,
        spectrum: np.ndarray,
        frame_indices: range,
        carrier_bits: tuple[int, ...],
        lower_bin: int,
        upper_bin: int,
    ) -> tuple[int, ...]:
        """Embed one ordered carrier plan into an eligible frame span for one replica."""

        selected_indices: list[int] = []
        for frame_index in frame_indices:
            carrier_index = len(selected_indices)
            if carrier_index == len(carrier_bits):
                break
            if self._pilot._embed_frame(
                spectrum[:, frame_index],
                carrier_bits[carrier_index],
                lower_bin,
                upper_bin,
                frame_index,
            ):
                selected_indices.append(frame_index)
        if len(selected_indices) != len(carrier_bits):
            raise FourFrameCapacityError(
                "cover signal does not contain enough eligible frames in one replica quarter"
            )
        return tuple(selected_indices)

    def _score_at_frame(
        self,
        spectrum: np.ndarray,
        lower_bin: int,
        upper_bin: int,
        frame_index: int,
    ) -> float | None:
        """Return raw signed score at one mapped frame or an erasure after duration loss."""

        if frame_index >= spectrum.shape[1]:
            return None
        score, _ = self._pilot._extract_frame_score(
            spectrum[:, frame_index],
            lower_bin,
            upper_bin,
            frame_index,
        )
        return score

    @staticmethod
    def _combine_scores(scores: Iterable[float | None]) -> float | None:
        """Return an absolute-score-weighted signed average or an all-copy erasure."""

        available_scores = tuple(score for score in scores if score is not None)
        total_weight = sum(abs(score) for score in available_scores)
        if not total_weight:
            return None
        return sum(score * abs(score) for score in available_scores) / total_weight


def _music_like_fixture(duration_seconds: int = 30) -> PcmAudio:
    """Create the deterministic music-like mono fixture used for capacity experiments."""

    sample_rate = 16000
    sample_positions = np.arange(sample_rate * duration_seconds) / sample_rate
    slow_modulation = 0.5 + 0.5 * np.sin(2 * np.pi * 0.11 * sample_positions)
    harmonic_stack = (
        0.18 * np.sin(2 * np.pi * 110 * sample_positions)
        + 0.12 * np.sin(2 * np.pi * 220 * sample_positions + 0.25 * slow_modulation)
        + 0.10 * np.sin(2 * np.pi * 330 * sample_positions)
        + 0.08 * np.sin(2 * np.pi * (700 + 80 * slow_modulation) * sample_positions)
        + 0.06 * np.sin(2 * np.pi * (1400 + 140 * slow_modulation) * sample_positions)
    )
    beat_envelope = np.maximum(0.0, np.sin(2 * np.pi * 2 * sample_positions)) ** 8
    percussion = 0.10 * beat_envelope * np.sin(2 * np.pi * 90 * sample_positions)
    noise = 0.025 * np.random.default_rng(31).normal(size=len(sample_positions))
    return PcmAudio(np.asarray(harmonic_stack + percussion + noise, dtype=np.float64), sample_rate)


def _extraction_record(
    experiment: FourFrameSoftCombineExperiment,
    embedding: FourFrameEmbedding,
    extraction: FourFrameExtraction,
) -> dict[str, object]:
    """Serialize carrier and byte-symbol damage with the applicable Reed--Solomon cost."""

    channel = experiment._pilot.schema._channel
    expected = channel.inspect_carrier_bits(
        embedding.carrier_plan.carrier_bits,
        embedding.carrier_plan.payload_length,
    )
    observed = channel.inspect_carrier_bits(
        extraction.observed_carrier_bits,
        embedding.carrier_plan.payload_length,
    )
    byte_erasures = set(observed.erasure_positions)
    unknown_byte_errors = sum(
        byte_index not in byte_erasures and expected.codeword[byte_index] != observed.codeword[byte_index]
        for byte_index in range(len(expected.codeword))
    )
    recovery = extraction.recovery.channel_recovery
    return {
        "known_bit_errors": extraction.known_bit_errors,
        "carrier_erasures": extraction.carrier_erasures,
        "unknown_byte_errors": unknown_byte_errors,
        "byte_erasures": len(byte_erasures),
        "rs_error_cost": 2 * unknown_byte_errors + len(byte_erasures),
        "rs_parity_budget": channel.parity_symbols,
        "corrected_bytes": len(recovery.corrected_positions),
        "decoder_returned_payload": recovery.payload is not None,
        "token_matches_input": extraction.token_matches_input,
        "recovered": extraction.recovered,
        "channel_error": recovery.error,
    }


def run() -> dict[str, object]:
    """Execute clean four-frame threshold sweeps and return JSON-serializable measurements."""

    source = _music_like_fixture()
    token = bytes.fromhex("0123456789abcdef")
    pilot = SpectralAudioPilot(
        b"audio-pilot-test-key",
        SpectralPilotConfig(relative_difference=0.84),
    )
    embedding_experiment = FourFrameSoftCombineExperiment(pilot, 0.01)
    embedding = embedding_experiment.embed(source, token)
    results: dict[str, object] = {}
    for confidence_threshold in (0.01, 0.03, 0.05, 0.055, 0.06, 0.065, 0.07, 0.08, 0.12):
        experiment = FourFrameSoftCombineExperiment(pilot, confidence_threshold)
        extraction = experiment.extract(embedding.audio, embedding)
        results[f"{confidence_threshold:.3f}"] = _extraction_record(
            experiment,
            embedding,
            extraction,
        )
    return {
        "fixture": {
            "description": "deterministic 30-second synthetic music-like mono waveform",
            "sample_rate": source.sample_rate,
            "duration_seconds": source.duration_seconds,
        },
        "relative_difference": pilot._config.relative_difference,
        "repetition": FourFrameSoftCombineExperiment._replica_count,
        "carrier_bits": len(embedding.carrier_plan.carrier_bits),
        "frames_per_replica": [len(frame_map) for frame_map in embedding.replica_frame_indices],
        "embedding_snr_db": embedding.signal_to_noise_db,
        "results": results,
    }


def main() -> None:
    """Print the complete reproducible iteration record as formatted JSON."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
