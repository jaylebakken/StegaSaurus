"""Run iteration 003: two-frame soft combining for opaque-token carrier bits.

Experiment goal: test whether repeating every planned token bit in two
time-separated STFT frames and combining their signed evidence reduces the
clean-channel error rate enough for Reed--Solomon recovery.

Pipeline state: iteration 002 established that one frame per framed/interleaved
token bit fails clean oracle-aligned recovery with 50 confident bit errors. The
statistical detector remains functional, but there is no production attribution
encoder or synchronized attribution decoder. This iteration still uses oracle
frame mapping and evaluates a 30-second synthetic music-like cover signal.
"""

from __future__ import annotations

from dataclasses import dataclass
import json

import numpy as np

from ....pilot import PcmAudio, SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioAttributionResult
from ....transport import CarrierBit, CarrierPlan


class TwoFrameCapacityError(ValueError):
    """Report a cover signal that cannot provide two eligible time-separated frames per bit."""


@dataclass(frozen=True, slots=True)
class TwoFrameEmbedding:
    """Record a repeated token plan, its two oracle frame maps, and waveform quality diagnostics."""

    audio: PcmAudio
    carrier_plan: CarrierPlan
    primary_frame_indices: tuple[int, ...]
    replica_frame_indices: tuple[int, ...]
    signal_to_noise_db: float


@dataclass(frozen=True, slots=True)
class TwoFrameExtraction:
    """Record both signed evidence streams, combined decisions, and token recovery diagnostics."""

    primary_scores: tuple[float | None, ...]
    replica_scores: tuple[float | None, ...]
    combined_scores: tuple[float | None, ...]
    observed_carrier_bits: tuple[CarrierBit, ...]
    known_bit_errors: int
    carrier_erasures: int
    recovery: AudioAttributionResult

    @property
    def recovered(self) -> bool:
        """Return whether the combined observation stream yielded a full opaque token."""

        return self.recovery.recovered


class TwoFrameSoftCombineExperiment:
    """Repeat each planned carrier bit across frame halves and combine signed evidence before decoding."""

    def __init__(self, pilot: SpectralAudioPilot, minimum_combined_confidence: float | None = None) -> None:
        """Initialize a fixed-pilot experiment with an optional post-combination confidence threshold."""

        self._pilot = pilot
        threshold = pilot._config.minimum_confidence if minimum_combined_confidence is None else minimum_combined_confidence
        if not 0 < threshold < 1:
            raise ValueError("minimum_combined_confidence must be between zero and one")
        self._minimum_combined_confidence = threshold

    def embed(self, audio: PcmAudio, token: bytes) -> TwoFrameEmbedding:
        """Embed each planned bit once in each source-frame half and retain the oracle mappings."""

        carrier_plan = self._pilot.schema.plan_attribution(token)
        frequencies, spectrum = self._pilot._stft(audio)
        lower_bin, upper_bin = self._pilot._frequency_bin_range(frequencies)
        midpoint = spectrum.shape[1] // 2
        primary_indices = self._embed_copy(
            spectrum,
            range(0, midpoint),
            carrier_plan.carrier_bits,
            lower_bin,
            upper_bin,
        )
        replica_indices = self._embed_copy(
            spectrum,
            range(midpoint, spectrum.shape[1]),
            carrier_plan.carrier_bits,
            lower_bin,
            upper_bin,
        )
        encoded_samples = self._pilot._inverse_stft(spectrum, audio)
        noise_samples = encoded_samples - audio.samples
        return TwoFrameEmbedding(
            PcmAudio(encoded_samples, audio.sample_rate),
            carrier_plan,
            primary_indices,
            replica_indices,
            self._pilot._signal_to_noise_db(audio.samples, noise_samples),
        )

    def extract(self, audio: PcmAudio, embedding: TwoFrameEmbedding) -> TwoFrameExtraction:
        """Combine two oracle-aligned signed score streams into ordered carrier bits and recover the token."""

        if len(embedding.primary_frame_indices) != len(embedding.carrier_plan.carrier_bits):
            raise ValueError("primary frame map does not match the carrier plan")
        if len(embedding.replica_frame_indices) != len(embedding.carrier_plan.carrier_bits):
            raise ValueError("replica frame map does not match the carrier plan")
        frequencies, spectrum = self._pilot._stft(audio)
        lower_bin, upper_bin = self._pilot._frequency_bin_range(frequencies)
        primary_scores: list[float | None] = []
        replica_scores: list[float | None] = []
        combined_scores: list[float | None] = []
        observed_bits: list[CarrierBit] = []
        for target_bit, primary_index, replica_index in zip(
            embedding.carrier_plan.carrier_bits,
            embedding.primary_frame_indices,
            embedding.replica_frame_indices,
        ):
            primary_score = self._score_at_frame(
                spectrum,
                lower_bin,
                upper_bin,
                primary_index,
            )
            replica_score = self._score_at_frame(
                spectrum,
                lower_bin,
                upper_bin,
                replica_index,
            )
            combined_score = self._combine_scores(primary_score, replica_score)
            primary_scores.append(primary_score)
            replica_scores.append(replica_score)
            combined_scores.append(combined_score)
            if combined_score is None or abs(combined_score) < self._minimum_combined_confidence:
                observed_bits.append(None)
            else:
                observed_bits.append(int(combined_score >= 0))
        normalized_bits = tuple(observed_bits)
        recovery = self._pilot.schema.recover_attribution(normalized_bits)
        known_bit_errors = sum(
            observed_bit is not None and observed_bit != target_bit
            for target_bit, observed_bit in zip(embedding.carrier_plan.carrier_bits, normalized_bits)
        )
        return TwoFrameExtraction(
            tuple(primary_scores),
            tuple(replica_scores),
            tuple(combined_scores),
            normalized_bits,
            known_bit_errors,
            sum(observed_bit is None for observed_bit in normalized_bits),
            recovery,
        )

    def _embed_copy(
        self,
        spectrum: np.ndarray,
        frame_indices: range,
        carrier_bits: tuple[int, ...],
        lower_bin: int,
        upper_bin: int,
    ) -> tuple[int, ...]:
        """Embed an ordered carrier plan into one disjoint span of eligible STFT source frames."""

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
            raise TwoFrameCapacityError(
                "cover signal does not contain enough eligible frames in one required replica half"
            )
        return tuple(selected_indices)

    def _score_at_frame(
        self,
        spectrum: np.ndarray,
        lower_bin: int,
        upper_bin: int,
        frame_index: int,
    ) -> float | None:
        """Return raw signed evidence at one mapped frame or an erasure after duration loss."""

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
    def _combine_scores(primary_score: float | None, replica_score: float | None) -> float | None:
        """Return an absolute-score-weighted signed average while preserving a missing-copy erasure."""

        available_scores = tuple(
            score for score in (primary_score, replica_score) if score is not None
        )
        total_weight = sum(abs(score) for score in available_scores)
        if not total_weight:
            return None
        return sum(score * abs(score) for score in available_scores) / total_weight


def _music_like_fixture(duration_seconds: int = 30) -> PcmAudio:
    """Create deterministic, dynamically layered synthetic music-like mono audio for capacity testing."""

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


def _extraction_record(extraction: TwoFrameExtraction) -> dict[str, object]:
    """Serialize soft-combined raw damage and Reed--Solomon outcome for one margin setting."""

    recovery = extraction.recovery.channel_recovery
    return {
        "known_bit_errors": extraction.known_bit_errors,
        "carrier_erasures": extraction.carrier_erasures,
        "byte_erasures": len(recovery.erasure_positions),
        "corrected_bytes": len(recovery.corrected_positions),
        "recovered": extraction.recovered,
        "channel_error": recovery.error,
    }


def run() -> dict[str, object]:
    """Execute the clean two-frame margin sweep and return JSON-serializable measurements."""

    source = _music_like_fixture()
    token = bytes.fromhex("0123456789abcdef")
    results: dict[str, object] = {}
    for relative_difference in (0.48, 0.60, 0.72, 0.84):
        pilot = SpectralAudioPilot(
            b"audio-pilot-test-key",
            SpectralPilotConfig(relative_difference=relative_difference),
        )
        experiment = TwoFrameSoftCombineExperiment(pilot)
        embedding = experiment.embed(source, token)
        extraction = experiment.extract(embedding.audio, embedding)
        results[f"{relative_difference:.2f}"] = {
            "embedding_snr_db": embedding.signal_to_noise_db,
            "carrier_bits": len(embedding.carrier_plan.carrier_bits),
            "primary_frame_count": len(embedding.primary_frame_indices),
            "replica_frame_count": len(embedding.replica_frame_indices),
            "minimum_frame_separation": min(
                replica_index - primary_index
                for primary_index, replica_index in zip(
                    embedding.primary_frame_indices,
                    embedding.replica_frame_indices,
                )
            ),
            "extraction": _extraction_record(extraction),
        }
    return {
        "fixture": {
            "description": "deterministic 30-second synthetic music-like mono waveform",
            "sample_rate": source.sample_rate,
            "duration_seconds": source.duration_seconds,
        },
        "repetition": 2,
        "results": results,
    }


def main() -> None:
    """Print the complete reproducible iteration record as formatted JSON."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
