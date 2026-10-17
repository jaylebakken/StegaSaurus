"""Run iteration 002: measure direct opaque-token transport through the spectral carrier.

Experiment goal: determine whether the detector-only spectral pilot can carry
the complete 144-bit framed/interleaved opaque-token plan before attempting
real synchronization or attribution integration.

Pipeline state: the repository has a working statistical presence detector,
Reed--Solomon transport schema, and detector attack benchmark. It does not have
an audio attribution encoder or synchronized attribution decoder. This script
uses oracle source-frame indices solely to isolate raw carrier transport.

This module provides an oracle-aligned experiment, not a production attribution
decoder. It serializes the schema's framed and interleaved carrier-bit plan into
eligible STFT frames, then extracts observations from the exact frame indices
chosen at embedding. That controlled mapping isolates bit errors, erasures, and
Reed--Solomon recovery from the unsolved crop and time-scale synchronization
problem. Benchmark callers can apply named audio transformations and retain all
raw diagnostics for later comparison with a real synchronized decoder.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
import json

import numpy as np

from ....attacks import add_white_noise, mp3_round_trip, resample_audio
from ....pilot import PcmAudio, SpectralAudioPilot
from ....schema import AudioAttributionResult
from ....transport import CarrierBit, CarrierPlan


AudioAttack = Callable[[PcmAudio], PcmAudio]


class TokenBitCapacityError(ValueError):
    """Report an audio sample that cannot supply every planned token carrier frame."""


@dataclass(frozen=True, slots=True)
class TokenBitEmbedding:
    """Record a token-bearing waveform and the oracle frame mapping used in the experiment."""

    audio: PcmAudio
    token: bytes
    carrier_plan: CarrierPlan
    carrier_frame_indices: tuple[int, ...]
    scanned_frame_count: int
    signal_to_noise_db: float


@dataclass(frozen=True, slots=True)
class TokenBitExtraction:
    """Record carrier observations, raw transport damage, and opaque-token recovery output."""

    observed_carrier_bits: tuple[CarrierBit, ...]
    frame_confidences: tuple[float | None, ...]
    known_bit_errors: int
    carrier_erasures: int
    recovery: AudioAttributionResult

    @property
    def recovered(self) -> bool:
        """Return whether Reed--Solomon produced a complete opaque token in this trial."""

        return self.recovery.recovered


@dataclass(frozen=True, slots=True)
class TokenBitAttackEvaluation:
    """Record one attacked extraction or a concise failure without aborting other attacks."""

    name: str
    duration_seconds: float | None
    extraction: TokenBitExtraction | None
    error: str | None

    def __post_init__(self) -> None:
        """Require a usable name and exactly one successful extraction or error description."""

        if not self.name.strip():
            raise ValueError("attack names must not be empty")
        if (self.extraction is None) == (self.error is None):
            raise ValueError("an attack evaluation must contain exactly one outcome or error")

    @property
    def succeeded(self) -> bool:
        """Return whether this attack yielded an extractable waveform and token-bit report."""

        return self.extraction is not None


@dataclass(frozen=True, slots=True)
class TokenBitExperimentResult:
    """Represent a clean token extraction plus all named transformed-audio evaluations."""

    embedding: TokenBitEmbedding
    clean_extraction: TokenBitExtraction
    attacks: tuple[TokenBitAttackEvaluation, ...]

    @property
    def failures(self) -> tuple[TokenBitAttackEvaluation, ...]:
        """Return attack invocations that failed before token-bit extraction could complete."""

        return tuple(evaluation for evaluation in self.attacks if not evaluation.succeeded)


class TokenBitExperiment:
    """Embed and recover schema token bits using an explicit oracle-aligned STFT frame map."""

    def __init__(self, pilot: SpectralAudioPilot) -> None:
        """Initialize the experiment with the exact secret, spectral configuration, and schema to test."""

        self._pilot = pilot

    def embed(self, audio: PcmAudio, token: bytes) -> TokenBitEmbedding:
        """Embed every framed token bit in the next eligible unique source frame or fail closed."""

        carrier_plan = self._pilot.schema.plan_attribution(token)
        frequencies, spectrum = self._pilot._stft(audio)
        lower_bin, upper_bin = self._pilot._frequency_bin_range(frequencies)
        carrier_frame_indices: list[int] = []
        for frame_index in range(spectrum.shape[1]):
            carrier_index = len(carrier_frame_indices)
            if carrier_index == len(carrier_plan.carrier_bits):
                break
            target_bit = carrier_plan.carrier_bits[carrier_index]
            if self._pilot._embed_frame(
                spectrum[:, frame_index],
                target_bit,
                lower_bin,
                upper_bin,
                frame_index,
            ):
                carrier_frame_indices.append(frame_index)
        if len(carrier_frame_indices) != len(carrier_plan.carrier_bits):
            raise TokenBitCapacityError(
                "audio does not contain enough eligible frames for the planned attribution transport"
            )
        encoded_samples = self._pilot._inverse_stft(spectrum, audio)
        noise_samples = encoded_samples - audio.samples
        return TokenBitEmbedding(
            PcmAudio(encoded_samples, audio.sample_rate),
            bytes(token),
            carrier_plan,
            tuple(carrier_frame_indices),
            spectrum.shape[1],
            self._pilot._signal_to_noise_db(audio.samples, noise_samples),
        )

    def extract(self, audio: PcmAudio, embedding: TokenBitEmbedding) -> TokenBitExtraction:
        """Extract ordered carrier observations using the embedding's oracle source-frame map."""

        if len(embedding.carrier_plan.carrier_bits) != len(embedding.carrier_frame_indices):
            raise ValueError("embedding carrier plan and frame map must have matching lengths")
        frequencies, spectrum = self._pilot._stft(audio)
        lower_bin, upper_bin = self._pilot._frequency_bin_range(frequencies)
        observed_bits: list[CarrierBit] = []
        frame_confidences: list[float | None] = []
        for target_bit, frame_index in zip(
            embedding.carrier_plan.carrier_bits,
            embedding.carrier_frame_indices,
        ):
            if frame_index >= spectrum.shape[1]:
                observed_bits.append(None)
                frame_confidences.append(None)
                continue
            observed_bit, confidence = self._pilot._extract_frame(
                spectrum[:, frame_index],
                lower_bin,
                upper_bin,
                frame_index,
            )
            observed_bits.append(observed_bit)
            frame_confidences.append(confidence)
        normalized_observations = tuple(observed_bits)
        recovery = self._pilot.schema.recover_attribution(normalized_observations)
        known_bit_errors = sum(
            observed_bit is not None and observed_bit != target_bit
            for target_bit, observed_bit in zip(
                embedding.carrier_plan.carrier_bits,
                normalized_observations,
            )
        )
        return TokenBitExtraction(
            normalized_observations,
            tuple(frame_confidences),
            known_bit_errors,
            sum(observed_bit is None for observed_bit in normalized_observations),
            recovery,
        )

    def evaluate(
        self,
        audio: PcmAudio,
        token: bytes,
        attacks: Mapping[str, AudioAttack],
    ) -> TokenBitExperimentResult:
        """Embed one token, recover it cleanly, and measure every supplied transformed waveform."""

        self._validate_attacks(attacks)
        embedding = self.embed(audio, token)
        clean_extraction = self.extract(embedding.audio, embedding)
        evaluations = tuple(
            self._evaluate_attack(name, attack, embedding) for name, attack in attacks.items()
        )
        return TokenBitExperimentResult(embedding, clean_extraction, evaluations)

    def _evaluate_attack(
        self,
        name: str,
        attack: AudioAttack,
        embedding: TokenBitEmbedding,
    ) -> TokenBitAttackEvaluation:
        """Apply one attack and preserve either token recovery diagnostics or its execution error."""

        try:
            attacked_audio = attack(embedding.audio)
            if not isinstance(attacked_audio, PcmAudio):
                raise TypeError("audio attacks must return PcmAudio")
            extraction = self.extract(attacked_audio, embedding)
        except Exception as error:
            detail = str(error) or "no message"
            return TokenBitAttackEvaluation(name, None, None, f"{type(error).__name__}: {detail}")
        return TokenBitAttackEvaluation(name, attacked_audio.duration_seconds, extraction, None)

    @staticmethod
    def _validate_attacks(attacks: Mapping[str, AudioAttack]) -> None:
        """Reject malformed experiment attack definitions before embedding the requested token."""

        for name, attack in attacks.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("attack names must be non-empty strings")
            if not callable(attack):
                raise TypeError(f"attack {name!r} must be callable")


def _fixture_audio() -> PcmAudio:
    """Create the deterministic six-second speech-like waveform used by iteration 002."""

    sample_rate = 16000
    sample_positions = np.arange(sample_rate * 6) / sample_rate
    modulated_frequency = 900 + 90 * np.sin(2 * np.pi * 2 * sample_positions)
    samples = (
        0.28 * np.sin(2 * np.pi * 190 * sample_positions)
        + 0.18 * np.sin(2 * np.pi * 420 * sample_positions)
        + 0.10 * np.sin(2 * np.pi * modulated_frequency * sample_positions)
        + 0.02 * np.random.default_rng(7).normal(size=len(sample_positions))
    )
    return PcmAudio(samples.astype(np.float64), sample_rate)


def _extraction_record(extraction: TokenBitExtraction) -> dict[str, object]:
    """Serialize raw carrier damage and Reed--Solomon output for one token-bit condition."""

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
    """Execute the recorded oracle-aligned token-bit baseline and return primitive result data."""

    source = _fixture_audio()
    experiment = TokenBitExperiment(SpectralAudioPilot(b"audio-pilot-test-key"))
    result = experiment.evaluate(
        source,
        bytes.fromhex("0123456789abcdef"),
        {
            "mp3_96": lambda audio: mp3_round_trip(audio, 96),
            "noise_30db": lambda audio: add_white_noise(audio, 30.0, seed=13),
            "resample_44k1_round_trip": lambda audio: resample_audio(
                resample_audio(audio, 44100),
                16000,
            ),
        },
    )
    return {
        "carrier_bits": len(result.embedding.carrier_plan.carrier_bits),
        "carrier_frames": len(result.embedding.carrier_frame_indices),
        "embedding_snr_db": result.embedding.signal_to_noise_db,
        "clean": _extraction_record(result.clean_extraction),
        "attacks": {
            evaluation.name: _extraction_record(evaluation.extraction)
            for evaluation in result.attacks
            if evaluation.extraction is not None
        },
    }


def main() -> None:
    """Print the complete reproducible iteration record as formatted JSON."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
