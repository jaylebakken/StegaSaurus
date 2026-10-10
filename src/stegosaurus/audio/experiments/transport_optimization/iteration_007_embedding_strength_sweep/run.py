"""Run iteration 007: spectral embedding-strength sweep.

Experiment goal: measure whether increasing the spectral pair log-ratio shift
improves exact opaque-token recovery before modifying carrier selection. The
study holds the 8-byte token, 12 Reed--Solomon parity bytes, four-copy layout,
cover variants, and threshold search constant while sweeping the embedding
``relative_difference``.

Pipeline state: iteration 006 found no duration and threshold setting that
recovered all ten seeded cover variants. Its carrier capacity was sufficient,
but Reed--Solomon error costs exceeded the 12-symbol budget. This clean,
oracle-aligned experiment tests strength only; it does not claim perceptual,
codec, DSP, crop, or synchronization robustness.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
import json
from statistics import median

from ....pilot import SpectralAudioPilot, SpectralPilotConfig
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
from ..iteration_006_duration_stability_bounds.run import (
    _cover_variant,
    _trial_offset_seconds,
)


@dataclass(frozen=True, slots=True)
class StrengthTrialRecord:
    """Record all threshold results for one duration, cover variant, and strength setting."""

    duration_seconds: int
    relative_difference: float
    trial_index: int
    embedding_snr_db: float | None
    capacity_error: str | None
    measurements: Mapping[str, Mapping[str, object]]


def evaluate_trial(
    duration_seconds: int,
    relative_difference: float,
    trial_index: int,
    thresholds: Iterable[float],
) -> StrengthTrialRecord:
    """Embed one deterministic cover variant and decode cached evidence at all thresholds."""

    seed = 6100 + trial_index
    source = _cover_variant(duration_seconds, seed, _trial_offset_seconds(trial_index))
    pilot = SpectralAudioPilot(
        b"audio-pilot-test-key",
        SpectralPilotConfig(relative_difference=relative_difference),
        AudioWatermarkConfig(parity_symbols=12),
    )
    experiment = FourFrameSoftCombineExperiment(pilot, 0.01)
    try:
        embedding = experiment.embed(source, bytes.fromhex("0123456789abcdef"))
    except FourFrameCapacityError as error:
        return StrengthTrialRecord(
            duration_seconds,
            relative_difference,
            trial_index,
            None,
            str(error),
            {},
        )
    replica_scores = _combined_replica_scores(experiment, embedding)
    measurements: dict[str, Mapping[str, object]] = {}
    for threshold in thresholds:
        extraction = _decode_at_threshold(experiment, embedding, replica_scores, threshold)
        measurements[f"{threshold:.3f}"] = _extraction_record(experiment, embedding, extraction)
    return StrengthTrialRecord(
        duration_seconds,
        relative_difference,
        trial_index,
        embedding.signal_to_noise_db,
        None,
        measurements,
    )


def _aggregate_threshold(
    duration_seconds: int,
    relative_difference: float,
    threshold: float,
    trials: Iterable[StrengthTrialRecord],
) -> dict[str, object]:
    """Summarize exact recovery, RS cost, quality, and capacity for one strength setting."""

    trial_records = tuple(trials)
    threshold_key = f"{threshold:.3f}"
    measurements = tuple(
        trial.measurements[threshold_key]
        for trial in trial_records
        if threshold_key in trial.measurements
    )
    snr_values = tuple(
        trial.embedding_snr_db for trial in trial_records if trial.embedding_snr_db is not None
    )
    exact_recoveries = sum(measurement["token_matches_input"] for measurement in measurements)
    rs_costs = tuple(int(measurement["rs_error_cost"]) for measurement in measurements)
    return {
        "duration_seconds": duration_seconds,
        "relative_difference": relative_difference,
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


def _setting_rank(summary: Mapping[str, object]) -> tuple[int, int, float, float]:
    """Rank a setting by recovery count, capacity, RS cost, and then embedding SNR."""

    return (
        -int(summary["exact_recoveries"]),
        int(summary["capacity_failures"]),
        float(summary["median_rs_cost"] or float("inf")),
        -float(summary["median_embedding_snr_db"] or 0.0),
    )


def _strength_record(
    duration_seconds: int,
    relative_difference: float,
    thresholds: Iterable[float],
    trial_count: int,
) -> dict[str, object]:
    """Run all cover variants for one duration and embedding strength combination."""

    threshold_values = tuple(thresholds)
    trials = tuple(
        evaluate_trial(duration_seconds, relative_difference, trial_index, threshold_values)
        for trial_index in range(trial_count)
    )
    summaries = tuple(
        _aggregate_threshold(duration_seconds, relative_difference, threshold, trials)
        for threshold in threshold_values
    )
    best = min(summaries, key=_setting_rank)
    return {
        "duration_seconds": duration_seconds,
        "relative_difference": relative_difference,
        "best_threshold": best["threshold"],
        "best_summary": best,
        "reliable_thresholds": [
            summary["threshold"] for summary in summaries if summary["reliable"]
        ],
        "threshold_summaries": list(summaries),
        "trials": [asdict(trial) for trial in trials],
    }


def _best_record(records: Iterable[Mapping[str, object]]) -> Mapping[str, object] | None:
    """Select the strongest empirical setting without treating partial recovery as reliable."""

    record_values = tuple(records)
    if not record_values:
        return None
    return min(record_values, key=lambda record: _setting_rank(record["best_summary"]))


def run() -> dict[str, object]:
    """Execute the strength sweep across two representative duration bounds."""

    durations = (30, 60)
    strengths = (0.60, 0.72, 0.84, 0.90, 0.95)
    thresholds = (0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07)
    trial_count = 10
    records = tuple(
        _strength_record(duration, strength, thresholds, trial_count)
        for duration in durations
        for strength in strengths
    )
    reliable_records = tuple(record for record in records if record["reliable_thresholds"])
    return {
        "fixture": "iteration-six seeded music-like cover variants and virtual timeline offsets",
        "sample_rate": 16000,
        "token_bytes": 8,
        "parity_symbols": 12,
        "repetition": 4,
        "durations_seconds": durations,
        "relative_differences": strengths,
        "thresholds": thresholds,
        "trial_count": trial_count,
        "best_observed_setting": _best_record(records),
        "reliable_settings": list(reliable_records),
        "records": list(records),
    }


def main() -> None:
    """Print the complete reproducible embedding-strength sweep as formatted JSON."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
