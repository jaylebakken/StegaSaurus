"""Run iteration 001: clean-audio non-oracle candidate-map reconstruction.

Experiment goal: establish the first blind-map baseline after the completed
oracle-aligned transport-optimization track. The decoder receives only the
watermarked waveform, shared secret, transport configuration, and known
framing pattern. It regenerates two high-quality candidates per carrier
stratum from the observed spectrum, chooses sync carriers with known framing
bits, and chooses data carriers by four-copy signed-consensus evidence. The
retained encoder map is used only after decoding to measure candidate coverage
and selection accuracy.

Pipeline state: transport optimization can recover the fixed 8-byte token from
clean 30-second synthetic covers when its calibrated encoder-selected source
frame map is retained. This experiment does not use that map in reconstruction,
does not search time offsets, and does not claim resilience to transformations.
Unwatermarked and wrong-secret controls report false token acceptances under
the same candidate-selection procedure.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from itertools import product
import json
from statistics import median

import numpy as np

from ....pilot import PcmAudio, SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioWatermarkConfig
from ....transport import BitFramer, CarrierPlan
from ...transport_optimization.iteration_004_four_frame_soft_combine.run import (
    FourFrameEmbedding,
    FourFrameExtraction,
    _extraction_record,
)
from ...transport_optimization.iteration_006_duration_stability_bounds.run import (
    _cover_variant,
    _trial_offset_seconds,
)
from ...transport_optimization.iteration_009_calibrated_margin_selection.run import (
    CalibratedMarginExperiment,
)


@dataclass(frozen=True, slots=True)
class NonOracleReconstruction:
    """Represent a candidate-derived map and token observation without encoder map input."""

    candidate_frame_indices: tuple[tuple[tuple[int, ...], ...], ...]
    selected_candidate_ranks: tuple[tuple[int, ...], ...]
    selected_frame_indices: tuple[tuple[int, ...], ...]
    extraction: FourFrameExtraction


@dataclass(frozen=True, slots=True)
class CleanCandidateMapTrial:
    """Record clean non-oracle reconstruction and control outcomes for one cover variant."""

    trial_index: int
    embedding_snr_db: float | None
    decoder_received_oracle_map: bool
    map_metrics: Mapping[str, object] | None
    measurement: Mapping[str, object] | None
    unwatermarked_control_token_match: bool | None
    wrong_secret_control_token_match: bool | None
    error: str | None


class CleanCandidateMapExperiment:
    """Regenerate and select clean-audio carrier maps without calibrated encoder metadata."""

    _candidate_rank_count = 2

    def __init__(
        self,
        calibration_experiment: CalibratedMarginExperiment,
        minimum_combined_confidence: float,
    ) -> None:
        """Initialize observed-spectrum candidate reconstruction with a fixed confidence threshold."""

        if not 0 < minimum_combined_confidence < 1:
            raise ValueError("minimum_combined_confidence must be between zero and one")
        self._calibration_experiment = calibration_experiment
        self._pilot = calibration_experiment._pilot
        self._minimum_combined_confidence = minimum_combined_confidence

    def reconstruct(self, audio: PcmAudio, carrier_plan: CarrierPlan) -> NonOracleReconstruction:
        """Infer a four-copy carrier map and decode one token without an encoder frame map."""

        frequencies, spectrum = self._pilot._stft(audio)
        lower_bin, upper_bin = self._pilot._frequency_bin_range(frequencies)
        candidate_frame_indices = tuple(
            self._calibration_experiment._ranked_frame_maps(
                spectrum,
                frame_range,
                carrier_plan.carrier_bits,
                lower_bin,
                upper_bin,
            )
            for frame_range in self._calibration_experiment._replica_ranges(spectrum.shape[1])
        )
        candidate_scores = self._candidate_scores(
            spectrum,
            candidate_frame_indices,
            lower_bin,
            upper_bin,
        )
        selected_candidate_ranks = self._select_candidate_ranks(
            candidate_scores,
            carrier_plan,
        )
        selected_frame_indices = tuple(
            tuple(
                candidate_frame_indices[replica_index][selected_candidate_ranks[replica_index][carrier_index]][carrier_index]
                for carrier_index in range(len(carrier_plan.carrier_bits))
            )
            for replica_index in range(self._calibration_experiment._replica_count)
        )
        replica_scores = tuple(
            tuple(
                candidate_scores[replica_index][selected_candidate_ranks[replica_index][carrier_index]][carrier_index]
                for carrier_index in range(len(carrier_plan.carrier_bits))
            )
            for replica_index in range(self._calibration_experiment._replica_count)
        )
        extraction = self._extract(replica_scores, carrier_plan)
        return NonOracleReconstruction(
            candidate_frame_indices,
            selected_candidate_ranks,
            selected_frame_indices,
            extraction,
        )

    def _candidate_scores(
        self,
        spectrum: np.ndarray,
        candidate_frame_indices: tuple[tuple[tuple[int, ...], ...], ...],
        lower_bin: int,
        upper_bin: int,
    ) -> tuple[tuple[tuple[float | None, ...], ...], ...]:
        """Extract keyed evidence from every observed candidate frame without oracle positions."""

        return tuple(
            tuple(
                tuple(
                    self._calibration_experiment._score_at_frame(
                        spectrum,
                        lower_bin,
                        upper_bin,
                        frame_index,
                    )
                    for frame_index in rank_map
                )
                for rank_map in replica_rank_maps
            )
            for replica_rank_maps in candidate_frame_indices
        )

    def _select_candidate_ranks(
        self,
        candidate_scores: tuple[tuple[tuple[float | None, ...], ...], ...],
        carrier_plan: CarrierPlan,
    ) -> tuple[tuple[int, ...], ...]:
        """Choose one observed candidate per replica using sync bits or replica consistency only."""

        replica_count = self._calibration_experiment._replica_count
        carrier_count = len(carrier_plan.carrier_bits)
        selected_ranks = [[0] * carrier_count for _ in range(replica_count)]
        sync_positions = set(self._sync_positions(carrier_plan))
        for carrier_index in range(carrier_count):
            scores_by_replica = tuple(
                tuple(candidate_scores[replica_index][rank][carrier_index] for rank in range(self._candidate_rank_count))
                for replica_index in range(replica_count)
            )
            if carrier_index in sync_positions:
                expected_sign = 1.0 if carrier_plan.carrier_bits[carrier_index] else -1.0
                selected = tuple(
                    self._best_rank_for_sign(replica_scores, expected_sign)
                    for replica_scores in scores_by_replica
                )
            else:
                selected = self._best_consensus_ranks(scores_by_replica)
            for replica_index, rank in enumerate(selected):
                selected_ranks[replica_index][carrier_index] = rank
        return tuple(tuple(replica_ranks) for replica_ranks in selected_ranks)

    def _best_rank_for_sign(self, scores: tuple[float | None, ...], expected_sign: float) -> int:
        """Choose the candidate with the greatest known-sync signed margin for one replica."""

        return max(
            range(self._candidate_rank_count),
            key=lambda rank: (
                float("-inf") if scores[rank] is None else expected_sign * float(scores[rank]),
                -rank,
            ),
        )

    def _best_consensus_ranks(
        self,
        scores_by_replica: tuple[tuple[float | None, ...], ...],
    ) -> tuple[int, ...]:
        """Choose data candidates that maximize four-copy signed evidence without reading payload bits."""

        candidates: list[tuple[tuple[float, float, tuple[int, ...]], tuple[int, ...]]] = []
        for ranks in product(range(self._candidate_rank_count), repeat=len(scores_by_replica)):
            selected_scores = tuple(
                scores_by_replica[replica_index][rank]
                for replica_index, rank in enumerate(ranks)
            )
            available_scores = tuple(float(score) for score in selected_scores if score is not None)
            if not available_scores:
                continue
            direction = 1.0 if sum(available_scores) >= 0 else -1.0
            signed_scores = tuple(direction * score for score in available_scores)
            candidates.append(
                (
                    (
                        sum(signed_scores),
                        min(signed_scores),
                        tuple(-rank for rank in ranks),
                    ),
                    tuple(ranks),
                )
            )
        if not candidates:
            return (0,) * len(scores_by_replica)
        return max(candidates, key=lambda candidate: candidate[0])[1]

    def _extract(
        self,
        replica_scores: tuple[tuple[float | None, ...], ...],
        carrier_plan: CarrierPlan,
    ) -> FourFrameExtraction:
        """Soft-combine a reconstructed map into carrier observations and Reed--Solomon recovery."""

        combined_scores = tuple(
            self._calibration_experiment._combine_scores(
                replica_scores[replica_index][carrier_index]
                for replica_index in range(self._calibration_experiment._replica_count)
            )
            for carrier_index in range(len(carrier_plan.carrier_bits))
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
            for target_bit, observed_bit in zip(carrier_plan.carrier_bits, observed_bits)
        )
        return FourFrameExtraction(
            replica_scores,
            combined_scores,
            observed_bits,
            known_bit_errors,
            sum(observed_bit is None for observed_bit in observed_bits),
            recovery,
            False,
        )

    @staticmethod
    def _sync_positions(carrier_plan: CarrierPlan) -> tuple[int, ...]:
        """Return carrier positions occupied by fixed framing synchronization bits only."""

        framer = BitFramer()
        positions: list[int] = []
        carrier_position = 0
        remaining_data_bits = carrier_plan.codeword_length * 8
        while remaining_data_bits:
            positions.extend(range(carrier_position, carrier_position + len(framer.sync_pattern)))
            data_bits = min(framer.data_bits_per_frame, remaining_data_bits)
            carrier_position += len(framer.sync_pattern) + data_bits
            remaining_data_bits -= data_bits
        return tuple(positions)


def _map_metrics(
    reconstruction: NonOracleReconstruction,
    embedding: FourFrameEmbedding,
) -> dict[str, object]:
    """Score reconstructed candidates against the retained oracle map after decoding only."""

    sync_positions = set(CleanCandidateMapExperiment._sync_positions(embedding.carrier_plan))
    total_positions = 0
    candidate_covered = 0
    selected_matches = 0
    sync_positions_total = 0
    sync_matches = 0
    data_positions_total = 0
    data_matches = 0
    for replica_index, oracle_map in enumerate(embedding.replica_frame_indices):
        for carrier_index, oracle_frame_index in enumerate(oracle_map):
            total_positions += 1
            candidate_frames = tuple(
                reconstruction.candidate_frame_indices[replica_index][rank][carrier_index]
                for rank in range(CleanCandidateMapExperiment._candidate_rank_count)
            )
            candidate_covered += int(oracle_frame_index in candidate_frames)
            matched = reconstruction.selected_frame_indices[replica_index][carrier_index] == oracle_frame_index
            selected_matches += int(matched)
            if carrier_index in sync_positions:
                sync_positions_total += 1
                sync_matches += int(matched)
            else:
                data_positions_total += 1
                data_matches += int(matched)
    return {
        "physical_carrier_positions": total_positions,
        "oracle_candidate_coverage": candidate_covered / total_positions,
        "selected_map_accuracy": selected_matches / total_positions,
        "sync_selected_map_accuracy": sync_matches / sync_positions_total,
        "data_selected_map_accuracy": data_matches / data_positions_total,
    }


def _control_token_match(reconstruction: NonOracleReconstruction, token: bytes) -> bool:
    """Return whether a control reconstruction falsely yields the known token exactly."""

    return reconstruction.extraction.recovery.token == token


def evaluate_trial(trial_index: int) -> CleanCandidateMapTrial:
    """Embed one clean cover, reconstruct its map blindly, and evaluate two false-accept controls."""

    token = bytes.fromhex("0123456789abcdef")
    source = _cover_variant(30, 6100 + trial_index, _trial_offset_seconds(trial_index))
    config = SpectralPilotConfig(
        minimum_frequency_hz=500.0,
        maximum_frequency_hz=3800.0,
        relative_difference=0.95,
    )
    watermark_config = AudioWatermarkConfig(parity_symbols=12)
    pilot = SpectralAudioPilot(b"audio-pilot-test-key", config, watermark_config)
    encoder = CalibratedMarginExperiment(pilot, 0.01)
    decoder = CleanCandidateMapExperiment(encoder, 0.01)
    try:
        embedding = encoder.embed(source, token)
        reconstruction = decoder.reconstruct(embedding.audio, embedding.carrier_plan)
        extraction = reconstruction.extraction
        reconstructed_extraction = FourFrameExtraction(
            extraction.replica_scores,
            extraction.combined_scores,
            extraction.observed_carrier_bits,
            extraction.known_bit_errors,
            extraction.carrier_erasures,
            extraction.recovery,
            extraction.recovery.token == embedding.token,
        )
        measurement = _extraction_record(encoder, embedding, reconstructed_extraction)
        unwatermarked = decoder.reconstruct(source, embedding.carrier_plan)
        wrong_pilot = SpectralAudioPilot(b"wrong-audio-pilot-test-key", config, watermark_config)
        wrong_decoder = CleanCandidateMapExperiment(CalibratedMarginExperiment(wrong_pilot, 0.01), 0.01)
        wrong_plan = wrong_pilot.schema.plan_attribution(token)
        wrong_secret = wrong_decoder.reconstruct(embedding.audio, wrong_plan)
    except Exception as error:
        detail = str(error) or "no message"
        return CleanCandidateMapTrial(trial_index, None, False, None, None, None, None, f"{type(error).__name__}: {detail}")
    return CleanCandidateMapTrial(
        trial_index,
        embedding.signal_to_noise_db,
        False,
        _map_metrics(reconstruction, embedding),
        measurement,
        _control_token_match(unwatermarked, token),
        _control_token_match(wrong_secret, token),
        None,
    )


def run() -> dict[str, object]:
    """Execute clean non-oracle candidate-map reconstruction over ten seeded cover variants."""

    trials = tuple(evaluate_trial(trial_index) for trial_index in range(10))
    successful_trials = tuple(trial for trial in trials if trial.measurement is not None and trial.map_metrics is not None)
    measurements = tuple(trial.measurement for trial in successful_trials if trial.measurement is not None)
    map_metrics = tuple(trial.map_metrics for trial in successful_trials if trial.map_metrics is not None)
    return {
        "fixture": "ten seeded 30-second music-like cover variants and virtual timeline offsets",
        "mapping_mode": "non_oracle_observed_spectrum_candidate_selection",
        "decoder_received_oracle_map": False,
        "candidate_rank_count": CleanCandidateMapExperiment._candidate_rank_count,
        "candidate_selection": "known-sync signed margins; unknown-data four-copy signed consensus",
        "carrier_band_hz": [500.0, 3800.0],
        "relative_difference": 0.95,
        "parity_symbols": 12,
        "repetition": 4,
        "trial_count": len(trials),
        "execution_failures": sum(trial.error is not None for trial in trials),
        "exact_recoveries": sum(bool(measurement["token_matches_input"]) for measurement in measurements),
        "median_rs_cost": median(int(measurement["rs_error_cost"]) for measurement in measurements) if measurements else None,
        "maximum_rs_cost": max(int(measurement["rs_error_cost"]) for measurement in measurements) if measurements else None,
        "median_oracle_candidate_coverage": median(float(metric["oracle_candidate_coverage"]) for metric in map_metrics) if map_metrics else None,
        "median_selected_map_accuracy": median(float(metric["selected_map_accuracy"]) for metric in map_metrics) if map_metrics else None,
        "median_sync_selected_map_accuracy": median(float(metric["sync_selected_map_accuracy"]) for metric in map_metrics) if map_metrics else None,
        "median_data_selected_map_accuracy": median(float(metric["data_selected_map_accuracy"]) for metric in map_metrics) if map_metrics else None,
        "unwatermarked_control_false_accepts": sum(bool(trial.unwatermarked_control_token_match) for trial in successful_trials),
        "wrong_secret_control_false_accepts": sum(bool(trial.wrong_secret_control_token_match) for trial in successful_trials),
        "trials": [asdict(trial) for trial in trials],
    }


def main() -> None:
    """Print the complete reproducible clean non-oracle reconstruction study as JSON."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
