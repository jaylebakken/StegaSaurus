"""Run iteration 008: stratified high-energy carrier selection.

Experiment goal: determine whether selecting high-energy, secret-pair-eligible
frames throughout each replica quarter reduces Reed--Solomon transport damage
relative to iteration 007's sequential first-eligible-frame mapping. Both
policies use iteration 007's strongest tested margin, ``relative_difference``
of 0.95, while preserving the 8-byte token, 12 parity bytes, and four-copy
layout.

Pipeline state: stronger embedding improved the best 60-second clean result to
three exact recoveries from ten variants but remained unreliable. Iteration 006
showed capacity was not the bottleneck. This experiment is oracle aligned and
stores source-frame maps, so it evaluates carrier quality only, not a finished
synchronization strategy for independently received audio.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from dataclasses import asdict, dataclass
import json
import math
from statistics import median

import numpy as np

from ....pilot import SpectralAudioPilot, SpectralPilotConfig
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


class StratifiedEnergyExperiment(FourFrameSoftCombineExperiment):
    """Embed each copy in high-energy secret-pair frames distributed across its time quarter."""

    def embed(self, audio, token: bytes) -> FourFrameEmbedding:
        """Select one high-quality carrier frame per time stratum before embedding all copies."""

        carrier_plan = self._pilot.schema.plan_attribution(token)
        frequencies, spectrum = self._pilot._stft(audio)
        lower_bin, upper_bin = self._pilot._frequency_bin_range(frequencies)
        replica_frame_indices = tuple(
            self._select_and_embed_copy(
                spectrum,
                frame_range,
                carrier_plan.carrier_bits,
                lower_bin,
                upper_bin,
            )
            for frame_range in self._replica_ranges(spectrum.shape[1])
        )
        encoded_samples = self._pilot._inverse_stft(spectrum, audio)
        noise_samples = encoded_samples - audio.samples
        return FourFrameEmbedding(
            type(audio)(encoded_samples, audio.sample_rate),
            carrier_plan,
            bytes(token),
            replica_frame_indices,
            self._pilot._signal_to_noise_db(audio.samples, noise_samples),
        )

    @staticmethod
    def _strata(frame_range: range, carrier_count: int) -> tuple[range, ...]:
        """Partition one replica quarter into ordered non-overlapping frame-selection strata."""

        if carrier_count < 1:
            raise ValueError("carrier_count must be positive")
        boundaries = np.linspace(frame_range.start, frame_range.stop, carrier_count + 1, dtype=int)
        return tuple(
            range(int(boundaries[index]), int(boundaries[index + 1]))
            for index in range(carrier_count)
        )

    def _select_and_embed_copy(
        self,
        spectrum: np.ndarray,
        frame_range: range,
        carrier_bits: tuple[int, ...],
        lower_bin: int,
        upper_bin: int,
    ) -> tuple[int, ...]:
        """Select the strongest eligible frame in each stratum and embed its ordered carrier bit."""

        selected_indices: list[int] = []
        for expected_bit, stratum in zip(carrier_bits, self._strata(frame_range, len(carrier_bits))):
            candidates = tuple(
                (self._frame_quality(spectrum[:, frame_index], lower_bin, upper_bin, frame_index), frame_index)
                for frame_index in stratum
            )
            usable_candidates = tuple(
                (quality, frame_index)
                for quality, frame_index in candidates
                if quality is not None
            )
            if not usable_candidates:
                raise FourFrameCapacityError(
                    "one carrier-selection stratum has no eligible high-energy frame"
                )
            _, selected_index = max(usable_candidates)
            if not self._pilot._embed_frame(
                spectrum[:, selected_index],
                expected_bit,
                lower_bin,
                upper_bin,
                selected_index,
            ):
                raise FourFrameCapacityError("selected high-energy frame became ineligible")
            selected_indices.append(selected_index)
        return tuple(selected_indices)

    def _frame_quality(
        self,
        frame_spectrum: np.ndarray,
        lower_bin: int,
        upper_bin: int,
        frame_index: int,
    ) -> float | None:
        """Return pair-energy quality for one frame or ``None`` when it cannot carry a bit."""

        if self._pilot._frame_rms(frame_spectrum) < self._pilot._config.minimum_frame_rms:
            return None
        pair_energies = tuple(
            float(abs(frame_spectrum[first_bin])) + float(abs(frame_spectrum[second_bin]))
            for first_bin, second_bin in self._pilot._pair_bins(lower_bin, upper_bin, frame_index)
        )
        usable_energies = tuple(
            energy
            for energy in pair_energies
            if energy >= self._pilot._config.minimum_pair_magnitude
        )
        if len(usable_energies) < self._pilot._config.minimum_pairs_per_frame:
            return None
        floor = self._pilot._config.minimum_pair_magnitude
        return sum(math.log(energy + floor) for energy in usable_energies) / len(usable_energies)


@dataclass(frozen=True, slots=True)
class SelectionTrialRecord:
    """Record all threshold measurements for one selection policy and cover variant."""

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
    """Construct the requested sequential or stratified high-energy embedding policy."""

    if selection_policy == "sequential":
        return FourFrameSoftCombineExperiment(pilot, 0.01)
    if selection_policy == "stratified_pair_energy":
        return StratifiedEnergyExperiment(pilot, 0.01)
    raise ValueError("selection_policy is not recognized")


def evaluate_trial(
    duration_seconds: int,
    selection_policy: str,
    trial_index: int,
    thresholds: Iterable[float],
) -> SelectionTrialRecord:
    """Embed one cover variant with one policy and decode cached scores at all thresholds."""

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
        return SelectionTrialRecord(
            duration_seconds,
            selection_policy,
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
    return SelectionTrialRecord(
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
    trials: Iterable[SelectionTrialRecord],
) -> dict[str, object]:
    """Summarize recovery, RS cost, quality, and capacity for one selection setting."""

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
    """Rank one policy setting by recovery, capacity, RS cost, and embedding SNR."""

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
    """Evaluate all cover variants for one duration and carrier-selection policy."""

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
    """Select the empirical best policy without treating partial recovery as reliable."""

    record_values = tuple(records)
    return min(record_values, key=lambda record: _setting_rank(record["best_summary"])) if record_values else None


def run() -> dict[str, object]:
    """Execute the sequential versus stratified pair-energy carrier-selection comparison."""

    durations = (30, 60)
    policies = ("sequential", "stratified_pair_energy")
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
        "durations_seconds": durations,
        "selection_policies": policies,
        "thresholds": thresholds,
        "trial_count": trial_count,
        "best_observed_setting": _best_record(records),
        "reliable_settings": [record for record in records if record["reliable_thresholds"]],
        "records": list(records),
    }


def main() -> None:
    """Print the complete reproducible carrier-selection comparison as formatted JSON."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
