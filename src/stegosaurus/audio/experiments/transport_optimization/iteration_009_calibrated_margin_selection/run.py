"""Run iteration 009: calibrated post-round-trip carrier-margin selection.

Experiment goal: test whether a bounded calibration process can choose more
reliable carrier frames than sequential selection. In every time stratum, the
selector probes the two strongest raw pair-energy candidates through complete
embed -> inverse STFT -> STFT round trips, measures their signed extraction
margins, and retains the candidate with the stronger positive margin.

Pipeline state: iteration 007 found that stronger embedding at 0.95 partially
improves recovery, and iteration 008 found that raw high-energy selection is
not a consistent improvement. This experiment holds the 8-byte token, 12 RS
parity bytes, four-copy layout, and 0.95 strength fixed. It remains clean and
oracle aligned; independent map reconstruction and attack robustness are not
evaluated.
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
    FourFrameEmbedding,
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
from ..iteration_008_stratified_carrier_selection.run import StratifiedEnergyExperiment


class CalibratedMarginExperiment(StratifiedEnergyExperiment):
    """Select between two energy-qualified candidates using measured post-round-trip margins."""

    _candidate_rank_count = 2

    def embed(self, audio: PcmAudio, token: bytes) -> FourFrameEmbedding:
        """Probe ranked candidate maps, then embed one maximum-margin carrier choice per stratum."""

        carrier_plan = self._pilot.schema.plan_attribution(token)
        frequencies, source_spectrum = self._pilot._stft(audio)
        lower_bin, upper_bin = self._pilot._frequency_bin_range(frequencies)
        ranked_maps = tuple(
            self._ranked_frame_maps(
                source_spectrum,
                frame_range,
                carrier_plan.carrier_bits,
                lower_bin,
                upper_bin,
            )
            for frame_range in self._replica_ranges(source_spectrum.shape[1])
        )
        probe_margins = tuple(
            self._probe_margins(
                audio,
                source_spectrum,
                tuple(replica_maps[rank] for replica_maps in ranked_maps),
                carrier_plan.carrier_bits,
                lower_bin,
                upper_bin,
            )
            for rank in range(self._candidate_rank_count)
        )
        replica_frame_indices = tuple(
            tuple(
                ranked_maps[replica_index][self._best_rank(probe_margins, replica_index, carrier_index)][carrier_index]
                for carrier_index in range(len(carrier_plan.carrier_bits))
            )
            for replica_index in range(self._replica_count)
        )
        encoded_spectrum = np.array(source_spectrum, copy=True)
        self._embed_mapped_bits(
            encoded_spectrum,
            replica_frame_indices,
            carrier_plan.carrier_bits,
            lower_bin,
            upper_bin,
        )
        encoded_samples = self._pilot._inverse_stft(encoded_spectrum, audio)
        noise_samples = encoded_samples - audio.samples
        return FourFrameEmbedding(
            PcmAudio(encoded_samples, audio.sample_rate),
            carrier_plan,
            bytes(token),
            replica_frame_indices,
            self._pilot._signal_to_noise_db(audio.samples, noise_samples),
        )

    def _ranked_frame_maps(
        self,
        spectrum: np.ndarray,
        frame_range: range,
        carrier_bits: tuple[int, ...],
        lower_bin: int,
        upper_bin: int,
    ) -> tuple[tuple[int, ...], ...]:
        """Return two highest-quality eligible candidate maps, one candidate per time stratum."""

        maps_by_rank = [list() for _ in range(self._candidate_rank_count)]
        for stratum in self._strata(frame_range, len(carrier_bits)):
            ranked_candidates = sorted(
                (
                    (quality, frame_index)
                    for frame_index in stratum
                    for quality in (self._frame_quality(spectrum[:, frame_index], lower_bin, upper_bin, frame_index),)
                    if quality is not None
                ),
                reverse=True,
            )
            if len(ranked_candidates) < self._candidate_rank_count:
                raise FourFrameCapacityError(
                    "one calibration stratum lacks two eligible candidate frames"
                )
            for rank in range(self._candidate_rank_count):
                maps_by_rank[rank].append(ranked_candidates[rank][1])
        return tuple(tuple(frame_map) for frame_map in maps_by_rank)

    def _probe_margins(
        self,
        audio: PcmAudio,
        source_spectrum: np.ndarray,
        replica_frame_indices: tuple[tuple[int, ...], ...],
        carrier_bits: tuple[int, ...],
        lower_bin: int,
        upper_bin: int,
    ) -> tuple[tuple[float, ...], ...]:
        """Measure signed extraction margins after one complete probe watermark round trip."""

        probe_spectrum = np.array(source_spectrum, copy=True)
        self._embed_mapped_bits(
            probe_spectrum,
            replica_frame_indices,
            carrier_bits,
            lower_bin,
            upper_bin,
        )
        probe_audio = PcmAudio(self._pilot._inverse_stft(probe_spectrum, audio), audio.sample_rate)
        _, observed_spectrum = self._pilot._stft(probe_audio)
        margins: list[tuple[float, ...]] = []
        for frame_map in replica_frame_indices:
            copy_margins: list[float] = []
            for expected_bit, frame_index in zip(carrier_bits, frame_map):
                score = self._score_at_frame(observed_spectrum, lower_bin, upper_bin, frame_index)
                expected_sign = 1.0 if expected_bit else -1.0
                copy_margins.append(float("-inf") if score is None else expected_sign * score)
            margins.append(tuple(copy_margins))
        return tuple(margins)

    def _embed_mapped_bits(
        self,
        spectrum: np.ndarray,
        replica_frame_indices: tuple[tuple[int, ...], ...],
        carrier_bits: tuple[int, ...],
        lower_bin: int,
        upper_bin: int,
    ) -> None:
        """Embed every logical carrier bit once for each supplied replica frame map."""

        for frame_map in replica_frame_indices:
            for expected_bit, frame_index in zip(carrier_bits, frame_map):
                if not self._pilot._embed_frame(
                    spectrum[:, frame_index],
                    expected_bit,
                    lower_bin,
                    upper_bin,
                    frame_index,
                ):
                    raise FourFrameCapacityError("a calibrated carrier frame became ineligible")

    def _best_rank(
        self,
        probe_margins: tuple[tuple[tuple[float, ...], ...], ...],
        replica_index: int,
        carrier_index: int,
    ) -> int:
        """Return the probe candidate rank with the strongest signed margin for one carrier copy."""

        return max(
            range(self._candidate_rank_count),
            key=lambda rank: probe_margins[rank][replica_index][carrier_index],
        )


@dataclass(frozen=True, slots=True)
class MarginTrialRecord:
    """Record all threshold measurements for one policy and deterministic cover variant."""

    duration_seconds: int
    selection_policy: str
    trial_index: int
    embedding_snr_db: float | None
    capacity_error: str | None
    measurements: Mapping[str, Mapping[str, object]]


def _experiment_for_policy(
    selection_policy: str,
    pilot: SpectralAudioPilot,
) -> FourFrameSoftCombineExperiment:
    """Construct the requested sequential or calibrated-margin experiment policy."""

    if selection_policy == "sequential":
        return FourFrameSoftCombineExperiment(pilot, 0.01)
    if selection_policy == "calibrated_round_trip_margin":
        return CalibratedMarginExperiment(pilot, 0.01)
    raise ValueError("selection_policy is not recognized")


def evaluate_trial(
    duration_seconds: int,
    selection_policy: str,
    trial_index: int,
    thresholds: Iterable[float],
) -> MarginTrialRecord:
    """Embed one cover with one policy and decode cached four-copy scores at all thresholds."""

    seed = 6100 + trial_index
    source = _cover_variant(duration_seconds, seed, _trial_offset_seconds(trial_index))
    pilot = SpectralAudioPilot(
        b"audio-pilot-test-key",
        SpectralPilotConfig(relative_difference=0.95),
        AudioWatermarkConfig(parity_symbols=12),
    )
    experiment = _experiment_for_policy(selection_policy, pilot)
    try:
        embedding = experiment.embed(source, bytes.fromhex("0123456789abcdef"))
    except FourFrameCapacityError as error:
        return MarginTrialRecord(duration_seconds, selection_policy, trial_index, None, str(error), {})
    replica_scores = _combined_replica_scores(experiment, embedding)
    measurements: dict[str, Mapping[str, object]] = {}
    for threshold in thresholds:
        extraction = _decode_at_threshold(experiment, embedding, replica_scores, threshold)
        measurements[f"{threshold:.3f}"] = _extraction_record(experiment, embedding, extraction)
    return MarginTrialRecord(
        duration_seconds,
        selection_policy,
        trial_index,
        embedding.signal_to_noise_db,
        None,
        measurements,
    )


def _aggregate_threshold(
    duration_seconds: int,
    selection_policy: str,
    threshold: float,
    trials: Iterable[MarginTrialRecord],
) -> dict[str, object]:
    """Summarize exact recovery, correction cost, quality, and capacity for one policy setting."""

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
        "selection_policy": selection_policy,
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
    """Rank policy settings by recovery count, capacity, RS cost, and then SNR."""

    return (
        -int(summary["exact_recoveries"]),
        int(summary["capacity_failures"]),
        float(summary["median_rs_cost"] or float("inf")),
        -float(summary["median_embedding_snr_db"] or 0.0),
    )


def _policy_record(
    duration_seconds: int,
    selection_policy: str,
    thresholds: Iterable[float],
    trial_count: int,
) -> dict[str, object]:
    """Evaluate all cover variants for one duration and one margin-selection policy."""

    threshold_values = tuple(thresholds)
    trials = tuple(
        evaluate_trial(duration_seconds, selection_policy, trial_index, threshold_values)
        for trial_index in range(trial_count)
    )
    summaries = tuple(
        _aggregate_threshold(duration_seconds, selection_policy, threshold, trials)
        for threshold in threshold_values
    )
    best = min(summaries, key=_setting_rank)
    return {
        "duration_seconds": duration_seconds,
        "selection_policy": selection_policy,
        "best_threshold": best["threshold"],
        "best_summary": best,
        "reliable_thresholds": [
            summary["threshold"] for summary in summaries if summary["reliable"]
        ],
        "threshold_summaries": list(summaries),
        "trials": [asdict(trial) for trial in trials],
    }


def _best_record(records: Iterable[Mapping[str, object]]) -> Mapping[str, object] | None:
    """Select the empirical best policy record without treating partial recovery as reliable."""

    record_values = tuple(records)
    return min(record_values, key=lambda record: _setting_rank(record["best_summary"])) if record_values else None


def run() -> dict[str, object]:
    """Execute the sequential versus calibrated-round-trip-margin policy comparison."""

    durations = (30, 60)
    policies = ("sequential", "calibrated_round_trip_margin")
    thresholds = (0.01, 0.02, 0.03, 0.04, 0.05, 0.06, 0.07)
    trial_count = 10
    records = tuple(
        _policy_record(duration, policy, thresholds, trial_count)
        for duration in durations
        for policy in policies
    )
    return {
        "fixture": "iteration-six seeded music-like cover variants and virtual timeline offsets",
        "sample_rate": 16000,
        "token_bytes": 8,
        "parity_symbols": 12,
        "repetition": 4,
        "relative_difference": 0.95,
        "calibration_candidates_per_stratum": CalibratedMarginExperiment._candidate_rank_count,
        "durations_seconds": durations,
        "selection_policies": policies,
        "thresholds": thresholds,
        "trial_count": trial_count,
        "best_observed_setting": _best_record(records),
        "reliable_settings": [record for record in records if record["reliable_thresholds"]],
        "records": list(records),
    }


def main() -> None:
    """Print the complete reproducible calibrated carrier-selection study as formatted JSON."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
