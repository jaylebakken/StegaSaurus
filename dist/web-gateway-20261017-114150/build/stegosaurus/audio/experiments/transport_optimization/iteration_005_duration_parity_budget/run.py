"""Run iteration 005: duration and Reed--Solomon parity budget sweep.

Experiment goal: determine the smallest Reed--Solomon parity configuration that
verifies an 8-byte opaque token for four-copy spectral transport over 30 to 120
seconds of deterministic cover audio. The output reports both theoretical frame
capacity and the shortest observed duration that exactly recovers the embedded
token.

Pipeline state: iteration 004 reduced raw errors with four-copy soft combining
but did not recover the known input token with eight parity bytes. It also showed
that a non-null Reed--Solomon decoder result cannot be treated as a verified
attribution. This experiment therefore compares decoder output with the known
input token and remains oracle aligned; synchronization under edits is unsolved.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import dataclass
import json

from ....pilot import SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioWatermarkConfig
from ..iteration_004_four_frame_soft_combine.run import (
    FourFrameCapacityError,
    FourFrameEmbedding,
    FourFrameExtraction,
    FourFrameSoftCombineExperiment,
    _extraction_record,
    _music_like_fixture,
)


@dataclass(frozen=True, slots=True)
class CandidateResult:
    """Record the best threshold result for one duration and parity configuration."""

    duration_seconds: int
    parity_symbols: int
    stft_frames: int
    carrier_bits: int | None
    physical_carrier_frames: int | None
    embedding_snr_db: float | None
    best_threshold: float | None
    best_measurement: Mapping[str, object] | None
    verified_thresholds: tuple[float, ...]
    capacity_error: str | None = None

    @property
    def verified(self) -> bool:
        """Return whether any evaluated threshold exactly recovered the input token."""

        return bool(self.verified_thresholds)


def _combined_replica_scores(
    experiment: FourFrameSoftCombineExperiment,
    embedding: FourFrameEmbedding,
) -> tuple[tuple[float | None, ...], ...]:
    """Extract all raw oracle-aligned replica scores once for threshold reuse."""

    pilot = experiment._pilot
    frequencies, spectrum = pilot._stft(embedding.audio)
    lower_bin, upper_bin = pilot._frequency_bin_range(frequencies)
    return tuple(
        tuple(
            experiment._score_at_frame(spectrum, lower_bin, upper_bin, frame_index)
            for frame_index in frame_map
        )
        for frame_map in embedding.replica_frame_indices
    )


def _decode_at_threshold(
    experiment: FourFrameSoftCombineExperiment,
    embedding: FourFrameEmbedding,
    replica_scores: tuple[tuple[float | None, ...], ...],
    confidence_threshold: float,
) -> FourFrameExtraction:
    """Convert cached four-copy evidence into one thresholded token observation stream."""

    carrier_bits = embedding.carrier_plan.carrier_bits
    combined_scores = tuple(
        experiment._combine_scores(copy_scores[carrier_index] for copy_scores in replica_scores)
        for carrier_index in range(len(carrier_bits))
    )
    observed_bits = tuple(
        None if score is None or abs(score) < confidence_threshold else int(score >= 0)
        for score in combined_scores
    )
    recovery = experiment._pilot.schema.recover_attribution(observed_bits)
    known_bit_errors = sum(
        observed_bit is not None and observed_bit != target_bit
        for target_bit, observed_bit in zip(carrier_bits, observed_bits)
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


def _measurement_rank(measurement: Mapping[str, object]) -> tuple[int, int, int, int]:
    """Rank measurements by verified recovery, correction cost, unknown errors, and erasures."""

    return (
        0 if measurement["token_matches_input"] else 1,
        int(measurement["rs_error_cost"]),
        int(measurement["unknown_byte_errors"]),
        int(measurement["byte_erasures"]),
    )


def evaluate_candidate(
    duration_seconds: int,
    parity_symbols: int,
    thresholds: Iterable[float],
) -> CandidateResult:
    """Embed and score one parity candidate, reusing its raw evidence across thresholds."""

    source = _music_like_fixture(duration_seconds)
    pilot = SpectralAudioPilot(
        b"audio-pilot-test-key",
        SpectralPilotConfig(relative_difference=0.84),
        AudioWatermarkConfig(parity_symbols=parity_symbols),
    )
    experiment = FourFrameSoftCombineExperiment(pilot, 0.01)
    frequencies, spectrum = pilot._stft(source)
    stft_frames = spectrum.shape[1]
    try:
        embedding = experiment.embed(source, bytes.fromhex("0123456789abcdef"))
    except FourFrameCapacityError as error:
        return CandidateResult(
            duration_seconds,
            parity_symbols,
            stft_frames,
            None,
            None,
            None,
            None,
            None,
            (),
            str(error),
        )
    replica_scores = _combined_replica_scores(experiment, embedding)
    threshold_results: list[tuple[float, dict[str, object]]] = []
    for threshold in thresholds:
        extraction = _decode_at_threshold(experiment, embedding, replica_scores, threshold)
        measurement = _extraction_record(experiment, embedding, extraction)
        threshold_results.append((threshold, measurement))
    best_threshold, best_measurement = min(
        threshold_results,
        key=lambda result: _measurement_rank(result[1]),
    )
    return CandidateResult(
        duration_seconds,
        parity_symbols,
        stft_frames,
        len(embedding.carrier_plan.carrier_bits),
        len(embedding.carrier_plan.carrier_bits) * FourFrameSoftCombineExperiment._replica_count,
        embedding.signal_to_noise_db,
        best_threshold,
        best_measurement,
        tuple(
            threshold
            for threshold, measurement in threshold_results
            if measurement["token_matches_input"]
        ),
    )


def _candidate_record(candidate: CandidateResult) -> dict[str, object]:
    """Serialize one candidate for the archived JSON output without NumPy values."""

    return {
        "duration_seconds": candidate.duration_seconds,
        "parity_symbols": candidate.parity_symbols,
        "stft_frames": candidate.stft_frames,
        "carrier_bits": candidate.carrier_bits,
        "physical_carrier_frames": candidate.physical_carrier_frames,
        "embedding_snr_db": candidate.embedding_snr_db,
        "best_threshold": candidate.best_threshold,
        "best_measurement": candidate.best_measurement,
        "verified_thresholds": candidate.verified_thresholds,
        "capacity_error": candidate.capacity_error,
    }


def _optimal_candidate(candidates: Iterable[CandidateResult]) -> CandidateResult | None:
    """Choose the smallest verified carrier plan, preferring shorter cover duration for ties."""

    verified_candidates = tuple(candidate for candidate in candidates if candidate.verified)
    if not verified_candidates:
        return None
    return min(
        verified_candidates,
        key=lambda candidate: (
            int(candidate.physical_carrier_frames or 0),
            candidate.duration_seconds,
            -float(candidate.embedding_snr_db or 0.0),
            candidate.parity_symbols,
        ),
    )


def run() -> dict[str, object]:
    """Execute the bounded duration-parity search and report optimal verified candidates."""

    durations = (30, 45, 60, 90, 120)
    parity_options = (8, 10, 12, 16, 20, 24, 32, 40, 48)
    thresholds = (0.01, 0.03, 0.05, 0.055, 0.06, 0.065, 0.07, 0.08, 0.12)
    candidates = tuple(
        evaluate_candidate(duration, parity_symbols, thresholds)
        for duration in durations
        for parity_symbols in parity_options
    )
    optimal = _optimal_candidate(candidates)
    best_by_duration = {
        str(duration): _candidate_record(
            _optimal_candidate(candidate for candidate in candidates if candidate.duration_seconds == duration)
            or min(
                (candidate for candidate in candidates if candidate.duration_seconds == duration),
                key=lambda candidate: _measurement_rank(candidate.best_measurement)
                if candidate.best_measurement is not None
                else (2, 10**9, 10**9, 10**9),
            )
        )
        for duration in durations
    }
    return {
        "fixture": "deterministic synthetic music-like mono waveform",
        "sample_rate": 16000,
        "durations_seconds": durations,
        "parity_options": parity_options,
        "thresholds": thresholds,
        "repetition": FourFrameSoftCombineExperiment._replica_count,
        "best_by_duration": best_by_duration,
        "optimal_verified_candidate": _candidate_record(optimal) if optimal else None,
        "minimum_observed_verified_seconds": min(
            (candidate.duration_seconds for candidate in candidates if candidate.verified),
            default=None,
        ),
        "candidates": [_candidate_record(candidate) for candidate in candidates],
    }


def main() -> None:
    """Print the complete reproducible duration and parity experiment record as JSON."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
