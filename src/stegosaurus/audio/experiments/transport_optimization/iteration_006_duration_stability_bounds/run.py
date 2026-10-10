"""Run iteration 006: clean duration and threshold stability bounds.

Experiment goal: measure lower duration, upper-duration stability, and
confidence-threshold tolerance for iteration 005's smallest verified transport
configuration: an 8-byte token, 12 Reed--Solomon parity bytes, and four-copy
soft combining. The study uses multiple deterministic cover variants and
different virtual timeline offsets instead of one favorable fixture.

Pipeline state: iteration 005 exactly recovered one token from a 30-second
synthetic fixture with 12 parity bytes. That result was not a corpus-level
duration guarantee. This iteration remains clean and oracle aligned, preserves
exact known-token verification, and does not assess compression, DSP attacks,
or edit synchronization.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
import json
from statistics import median

import numpy as np

from ....pilot import PcmAudio, SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioWatermarkConfig
from ..iteration_004_four_frame_soft_combine.run import (
    FourFrameCapacityError,
    FourFrameSoftCombineExperiment,
    _extraction_record,
)
from ..iteration_005_duration_parity_budget.run import (
    _combined_replica_scores,
    _decode_at_threshold,
)


@dataclass(frozen=True, slots=True)
class TrialRecord:
    """Record all threshold measurements for one deterministic cover trial."""

    duration_seconds: int
    trial_index: int
    seed: int
    timeline_offset_seconds: float
    stft_frames: int
    embedding_snr_db: float | None
    capacity_error: str | None
    measurements: Mapping[str, Mapping[str, object]]


def _cover_variant(
    duration_seconds: int,
    seed: int,
    timeline_offset_seconds: float,
) -> PcmAudio:
    """Create a deterministic music-like cover segment with seed-specific spectral structure."""

    sample_rate = 16000
    generator = np.random.default_rng(seed)
    sample_positions = timeline_offset_seconds + np.arange(sample_rate * duration_seconds) / sample_rate
    fundamental_hz = generator.uniform(85.0, 145.0)
    modulation_rate_hz = generator.uniform(0.06, 0.18)
    modulation_phase = generator.uniform(0.0, 2 * np.pi)
    slow_modulation = 0.5 + 0.5 * np.sin(
        2 * np.pi * modulation_rate_hz * sample_positions + modulation_phase
    )
    harmonic_stack = (
        generator.uniform(0.14, 0.20) * np.sin(2 * np.pi * fundamental_hz * sample_positions)
        + generator.uniform(0.09, 0.14)
        * np.sin(2 * np.pi * 2 * fundamental_hz * sample_positions + 0.35 * slow_modulation)
        + generator.uniform(0.07, 0.12) * np.sin(2 * np.pi * 3 * fundamental_hz * sample_positions)
        + generator.uniform(0.05, 0.10)
        * np.sin(2 * np.pi * (generator.uniform(550.0, 900.0) + 110 * slow_modulation) * sample_positions)
        + generator.uniform(0.04, 0.08)
        * np.sin(2 * np.pi * (generator.uniform(1200.0, 1800.0) + 180 * slow_modulation) * sample_positions)
    )
    beat_rate_hz = generator.uniform(1.4, 2.8)
    beat_envelope = np.maximum(0.0, np.sin(2 * np.pi * beat_rate_hz * sample_positions)) ** 8
    percussion = generator.uniform(0.05, 0.12) * beat_envelope * np.sin(
        2 * np.pi * generator.uniform(70.0, 130.0) * sample_positions
    )
    noise = generator.uniform(0.015, 0.035) * generator.normal(size=len(sample_positions))
    return PcmAudio(np.asarray(harmonic_stack + percussion + noise, dtype=np.float64), sample_rate)


def _trial_offset_seconds(trial_index: int) -> float:
    """Return a deterministic non-repeating virtual source-timeline offset for one trial."""

    return 37.0 + trial_index * 113.0


def evaluate_trial(
    duration_seconds: int,
    trial_index: int,
    thresholds: Iterable[float],
) -> TrialRecord:
    """Embed one cover variant and reuse its raw four-copy scores across thresholds."""

    seed = 6100 + trial_index
    timeline_offset_seconds = _trial_offset_seconds(trial_index)
    source = _cover_variant(duration_seconds, seed, timeline_offset_seconds)
    pilot = SpectralAudioPilot(
        b"audio-pilot-test-key",
        SpectralPilotConfig(relative_difference=0.84),
        AudioWatermarkConfig(parity_symbols=12),
    )
    experiment = FourFrameSoftCombineExperiment(pilot, 0.01)
    _, spectrum = pilot._stft(source)
    try:
        embedding = experiment.embed(source, bytes.fromhex("0123456789abcdef"))
    except FourFrameCapacityError as error:
        return TrialRecord(
            duration_seconds,
            trial_index,
            seed,
            timeline_offset_seconds,
            spectrum.shape[1],
            None,
            str(error),
            {},
        )
    replica_scores = _combined_replica_scores(experiment, embedding)
    measurements: dict[str, Mapping[str, object]] = {}
    for threshold in thresholds:
        extraction = _decode_at_threshold(experiment, embedding, replica_scores, threshold)
        measurements[f"{threshold:.3f}"] = _extraction_record(experiment, embedding, extraction)
    return TrialRecord(
        duration_seconds,
        trial_index,
        seed,
        timeline_offset_seconds,
        spectrum.shape[1],
        embedding.signal_to_noise_db,
        None,
        measurements,
    )


def _aggregate_threshold(
    duration_seconds: int,
    threshold: float,
    trials: Iterable[TrialRecord],
) -> dict[str, object]:
    """Summarize exact recovery, correction burden, quality, and capacity for one setting."""

    trial_records = tuple(trials)
    threshold_key = f"{threshold:.3f}"
    available_measurements = tuple(
        trial.measurements[threshold_key]
        for trial in trial_records
        if threshold_key in trial.measurements
    )
    snr_values = tuple(
        trial.embedding_snr_db for trial in trial_records if trial.embedding_snr_db is not None
    )
    exact_recoveries = sum(
        measurement["token_matches_input"] for measurement in available_measurements
    )
    rs_costs = tuple(int(measurement["rs_error_cost"]) for measurement in available_measurements)
    return {
        "duration_seconds": duration_seconds,
        "threshold": threshold,
        "trial_count": len(trial_records),
        "capacity_failures": sum(trial.capacity_error is not None for trial in trial_records),
        "exact_recoveries": exact_recoveries,
        "exact_recovery_rate": exact_recoveries / len(trial_records),
        "median_rs_cost": median(rs_costs) if rs_costs else None,
        "maximum_rs_cost": max(rs_costs) if rs_costs else None,
        "median_embedding_snr_db": median(snr_values) if snr_values else None,
        "minimum_embedding_snr_db": min(snr_values) if snr_values else None,
        "reliable": exact_recoveries == len(trial_records)
        and not any(trial.capacity_error is not None for trial in trial_records),
    }


def _setting_rank(summary: Mapping[str, object]) -> tuple[int, float, float, float]:
    """Rank a threshold by recovery rate, capacity, median RS cost, and SNR."""

    return (
        -int(summary["exact_recoveries"]),
        int(summary["capacity_failures"]),
        float(summary["median_rs_cost"] or float("inf")),
        -float(summary["median_embedding_snr_db"] or 0.0),
    )


def _duration_record(
    duration_seconds: int,
    thresholds: Iterable[float],
    trial_count: int,
) -> dict[str, object]:
    """Evaluate all cover trials for one duration and return threshold-level aggregates."""

    threshold_values = tuple(thresholds)
    trials = tuple(
        evaluate_trial(duration_seconds, trial_index, threshold_values)
        for trial_index in range(trial_count)
    )
    summaries = tuple(
        _aggregate_threshold(duration_seconds, threshold, trials)
        for threshold in threshold_values
    )
    best = min(summaries, key=_setting_rank)
    return {
        "duration_seconds": duration_seconds,
        "best_threshold": best["threshold"],
        "best_summary": best,
        "reliable_thresholds": [
            summary["threshold"] for summary in summaries if summary["reliable"]
        ],
        "threshold_summaries": list(summaries),
        "trials": [asdict(trial) for trial in trials],
    }


def run() -> dict[str, object]:
    """Execute the pre-registered clean boundary study and return JSON-serializable output."""

    durations = (12, 15, 18, 21, 24, 27, 30, 45, 60, 90, 120)
    thresholds = (0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07)
    trial_count = 10
    duration_records = tuple(
        _duration_record(duration, thresholds, trial_count) for duration in durations
    )
    reliable_records = tuple(
        record for record in duration_records if record["reliable_thresholds"]
    )
    minimum_reliable = reliable_records[0] if reliable_records else None
    return {
        "fixture": "ten seeded music-like cover variants with deterministic virtual timeline offsets",
        "sample_rate": 16000,
        "token_bytes": 8,
        "parity_symbols": 12,
        "repetition": 4,
        "relative_difference": 0.84,
        "durations_seconds": durations,
        "thresholds": thresholds,
        "trial_count": trial_count,
        "minimum_observed_reliable_seconds": (
            minimum_reliable["duration_seconds"] if minimum_reliable else None
        ),
        "reliable_thresholds_at_minimum_duration": (
            minimum_reliable["reliable_thresholds"] if minimum_reliable else []
        ),
        "duration_records": list(duration_records),
    }


def main() -> None:
    """Print the complete reproducible duration-boundary study as formatted JSON."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
