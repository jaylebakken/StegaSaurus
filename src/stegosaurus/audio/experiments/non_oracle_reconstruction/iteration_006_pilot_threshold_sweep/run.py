"""Run iteration 006: local-pilot absolute and contrast threshold sweep.

Experiment goal: test the error-versus-erasure hypothesis after contrastive
calibration in iteration 005 reached 96.7% median selected-map accuracy but
still caused Reed--Solomon failure through a small number of accepted wrong
maps. This study fixes the contrastive encoder and 4-pilot / 12-payload profile.
For every observed candidate pair, the decoder independently thresholds the
selected expected-pilot score and its selected-minus-rival pilot gap. Candidates
that fail either threshold become erasures before payload extraction.

Pipeline state: iteration 004 verifies this profile recovers the clean token
with an exact retained frame map, so payload capacity is sufficient. Iteration
005 narrows the non-oracle problem to accepted wrong map choices. The sweep is
clean, synthetic, and limited to declared thresholds; it does not establish
transform robustness or optimize thresholds on an external holdout corpus.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
import json
import math
from statistics import median

from ....pilot import PcmAudio, SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioWatermarkConfig
from ...transport_optimization.iteration_004_four_frame_soft_combine.run import (
    FourFrameExtraction,
    _extraction_record,
)
from ...transport_optimization.iteration_006_duration_stability_bounds.run import (
    _cover_variant,
    _trial_offset_seconds,
)
from ..iteration_002_local_selection_pilot.run import (
    LocalPilotCandidateMapExperiment,
    LocalPilotProfile,
    LocalPilotReconstruction,
    _control_token_match,
    _map_metrics,
    _profiles,
)
from ..iteration_005_contrastive_pilot_calibration.run import ContrastivePilotCalibratedExperiment


@dataclass(frozen=True, slots=True)
class PilotThresholds:
    """Describe one independently declared absolute-pilot and pilot-gap decoder threshold pair."""

    absolute_pilot_threshold: float
    pilot_gap_threshold: float

    @property
    def name(self) -> str:
        """Return a stable compact identifier for one threshold pair in archived outputs."""

        return f"absolute_{self.absolute_pilot_threshold:.3f}_gap_{self.pilot_gap_threshold:.3f}"


@dataclass(frozen=True, slots=True)
class ThresholdTrial:
    """Record one decoded threshold pair, map metrics, and negative-control outcomes for a cover."""

    thresholds: PilotThresholds
    trial_index: int
    embedding_snr_db: float | None
    map_metrics: dict[str, object] | None
    measurement: dict[str, object] | None
    unwatermarked_control_token_match: bool | None
    wrong_secret_control_token_match: bool | None
    error: str | None


class ThresholdedLocalPilotDecoder(LocalPilotCandidateMapExperiment):
    """Decode local-pilot candidates with independent absolute-score and rival-gap acceptance thresholds."""

    def __init__(
        self,
        encoder: ContrastivePilotCalibratedExperiment,
        minimum_combined_confidence: float,
        thresholds: PilotThresholds,
    ) -> None:
        """Initialize a thresholded decoder and validate both declared map-selection thresholds."""

        super().__init__(encoder, minimum_combined_confidence)
        if thresholds.absolute_pilot_threshold < 0 or thresholds.pilot_gap_threshold < 0:
            raise ValueError("pilot thresholds must not be negative")
        self._thresholds = thresholds

    def reconstruct(self, audio: PcmAudio, carrier_plan) -> LocalPilotReconstruction:
        """Reconstruct candidates with the declared independent pilot-score and pilot-gap thresholds."""

        frequencies, spectrum = self._pilot._stft(audio)
        lower_bin, upper_bin = self._pilot._frequency_bin_range(frequencies)
        candidate_frame_indices = tuple(
            self._encoder._ranked_frame_maps(
                spectrum,
                frame_range,
                carrier_plan.carrier_bits,
                lower_bin,
                upper_bin,
            )
            for frame_range in self._encoder._replica_ranges(spectrum.shape[1])
        )
        selected_ranks: list[list[int | None]] = []
        selected_frames: list[list[int | None]] = []
        pilot_margins: list[list[float | None]] = []
        replica_scores: list[list[float | None]] = []
        for replica_index, replica_rank_maps in enumerate(candidate_frame_indices):
            replica_ranks: list[int | None] = []
            replica_frames: list[int | None] = []
            replica_margins: list[float | None] = []
            replica_payload_scores: list[float | None] = []
            for carrier_index in range(len(carrier_plan.carrier_bits)):
                candidate_scores = tuple(
                    self._encoder.pilot_score_at_frame(
                        spectrum,
                        lower_bin,
                        upper_bin,
                        replica_rank_maps[rank][carrier_index],
                    )
                    for rank in range(self._encoder._candidate_rank_count)
                )
                expected_sign = 1.0 if self._encoder.selection_pilot_bit(replica_index, carrier_index) else -1.0
                signed_scores = tuple(
                    float("-inf") if score is None else expected_sign * score
                    for score in candidate_scores
                )
                best_rank = max(
                    range(self._encoder._candidate_rank_count),
                    key=lambda rank: (signed_scores[rank], -rank),
                )
                rival_rank = 1 - best_rank
                pilot_gap = signed_scores[best_rank] - signed_scores[rival_rank]
                accepted = (
                    math.isfinite(signed_scores[best_rank])
                    and signed_scores[best_rank] >= self._thresholds.absolute_pilot_threshold
                    and pilot_gap >= self._thresholds.pilot_gap_threshold
                )
                if not accepted:
                    replica_ranks.append(None)
                    replica_frames.append(None)
                    replica_margins.append(None)
                    replica_payload_scores.append(None)
                    continue
                frame_index = replica_rank_maps[best_rank][carrier_index]
                replica_ranks.append(best_rank)
                replica_frames.append(frame_index)
                replica_margins.append(pilot_gap)
                replica_payload_scores.append(
                    self._encoder._score_at_frame(
                        spectrum,
                        lower_bin,
                        upper_bin,
                        frame_index,
                    )
                )
            selected_ranks.append(replica_ranks)
            selected_frames.append(replica_frames)
            pilot_margins.append(replica_margins)
            replica_scores.append(replica_payload_scores)
        extraction = self._extract(tuple(tuple(scores) for scores in replica_scores), carrier_plan)
        return LocalPilotReconstruction(
            candidate_frame_indices,
            tuple(tuple(ranks) for ranks in selected_ranks),
            tuple(tuple(frames) for frames in selected_frames),
            tuple(tuple(margins) for margins in pilot_margins),
            extraction,
        )


def _profile() -> LocalPilotProfile:
    """Return the leading contrastive profile fixed for this decoder-only threshold study."""

    return next(profile for profile in _profiles() if profile.name == "small_pilot_4_payload_12")


def _thresholds() -> tuple[PilotThresholds, ...]:
    """Return the declared Cartesian sweep of absolute-pilot and rival-gap thresholds."""

    values = (0.0, 0.01, 0.02, 0.04)
    return tuple(
        PilotThresholds(absolute_threshold, gap_threshold)
        for absolute_threshold in values
        for gap_threshold in values
    )


def evaluate_variant(
    trial_index: int,
    thresholds: Iterable[PilotThresholds],
) -> tuple[ThresholdTrial, ...]:
    """Calibrate one cover once, then decode it and both controls under every threshold pair."""

    token = bytes.fromhex("0123456789abcdef")
    source = _cover_variant(30, 6100 + trial_index, _trial_offset_seconds(trial_index))
    config = SpectralPilotConfig(
        minimum_frequency_hz=500.0,
        maximum_frequency_hz=3800.0,
        relative_difference=0.95,
    )
    watermark_config = AudioWatermarkConfig(parity_symbols=12)
    profile = _profile()
    threshold_values = tuple(thresholds)
    pilot = SpectralAudioPilot(b"audio-pilot-test-key", config, watermark_config)
    encoder = ContrastivePilotCalibratedExperiment(pilot, 0.01, profile)
    try:
        embedding = encoder.embed(source, token)
    except Exception as error:
        detail = str(error) or "no message"
        return tuple(
            ThresholdTrial(threshold, trial_index, None, None, None, None, None, f"{type(error).__name__}: {detail}")
            for threshold in threshold_values
        )
    wrong_pilot = SpectralAudioPilot(b"wrong-audio-pilot-test-key", config, watermark_config)
    wrong_encoder = ContrastivePilotCalibratedExperiment(wrong_pilot, 0.01, profile)
    wrong_plan = wrong_pilot.schema.plan_attribution(token)
    records: list[ThresholdTrial] = []
    for threshold in threshold_values:
        try:
            decoder = ThresholdedLocalPilotDecoder(encoder, 0.01, threshold)
            reconstruction = decoder.reconstruct(embedding.audio, embedding.carrier_plan)
            extraction = reconstruction.extraction
            measured_extraction = FourFrameExtraction(
                extraction.replica_scores,
                extraction.combined_scores,
                extraction.observed_carrier_bits,
                extraction.known_bit_errors,
                extraction.carrier_erasures,
                extraction.recovery,
                extraction.recovery.token == token,
            )
            measurement = _extraction_record(encoder, embedding, measured_extraction)
            unwatermarked = decoder.reconstruct(source, embedding.carrier_plan)
            wrong_decoder = ThresholdedLocalPilotDecoder(wrong_encoder, 0.01, threshold)
            wrong_secret = wrong_decoder.reconstruct(embedding.audio, wrong_plan)
        except Exception as error:
            detail = str(error) or "no message"
            records.append(
                ThresholdTrial(threshold, trial_index, embedding.signal_to_noise_db, None, None, None, None, f"{type(error).__name__}: {detail}")
            )
            continue
        records.append(
            ThresholdTrial(
                threshold,
                trial_index,
                embedding.signal_to_noise_db,
                _map_metrics(reconstruction, embedding),
                measurement,
                _control_token_match(unwatermarked, token),
                _control_token_match(wrong_secret, token),
                None,
            )
        )
    return tuple(records)


def _summary(thresholds: PilotThresholds, trials: tuple[ThresholdTrial, ...]) -> dict[str, object]:
    """Aggregate exact recovery, map errors, erasures, RS cost, and controls for one threshold pair."""

    successful = tuple(trial for trial in trials if trial.measurement is not None and trial.map_metrics is not None)
    measurements = tuple(trial.measurement for trial in successful if trial.measurement is not None)
    map_metrics = tuple(trial.map_metrics for trial in successful if trial.map_metrics is not None)
    snr_values = tuple(trial.embedding_snr_db for trial in successful if trial.embedding_snr_db is not None)
    selected_accuracy = tuple(
        float(metric["selected_map_accuracy"])
        for metric in map_metrics
        if metric["selected_map_accuracy"] is not None
    )
    return {
        "threshold_name": thresholds.name,
        "absolute_pilot_threshold": thresholds.absolute_pilot_threshold,
        "pilot_gap_threshold": thresholds.pilot_gap_threshold,
        "trial_count": len(trials),
        "execution_failures": sum(trial.error is not None for trial in trials),
        "exact_recoveries": sum(bool(measurement["token_matches_input"]) for measurement in measurements),
        "median_rs_cost": median(int(measurement["rs_error_cost"]) for measurement in measurements) if measurements else None,
        "maximum_rs_cost": max(int(measurement["rs_error_cost"]) for measurement in measurements) if measurements else None,
        "median_known_bit_errors": median(int(measurement["known_bit_errors"]) for measurement in measurements) if measurements else None,
        "median_carrier_erasures": median(int(measurement["carrier_erasures"]) for measurement in measurements) if measurements else None,
        "median_unknown_byte_errors": median(int(measurement["unknown_byte_errors"]) for measurement in measurements) if measurements else None,
        "median_byte_erasures": median(int(measurement["byte_erasures"]) for measurement in measurements) if measurements else None,
        "median_selected_map_accuracy": median(selected_accuracy) if selected_accuracy else None,
        "median_selection_erasure_rate": median(float(metric["selection_erasure_rate"]) for metric in map_metrics) if map_metrics else None,
        "median_embedding_snr_db": median(snr_values) if snr_values else None,
        "unwatermarked_control_false_accepts": sum(bool(trial.unwatermarked_control_token_match) for trial in successful),
        "wrong_secret_control_false_accepts": sum(bool(trial.wrong_secret_control_token_match) for trial in successful),
    }


def run() -> dict[str, object]:
    """Run the declared decoder threshold grid over ten contrastively calibrated clean covers."""

    thresholds = _thresholds()
    trials = tuple(
        record
        for trial_index in range(10)
        for record in evaluate_variant(trial_index, thresholds)
    )
    summaries = tuple(
        _summary(
            threshold,
            tuple(trial for trial in trials if trial.thresholds == threshold),
        )
        for threshold in thresholds
    )
    return {
        "fixture": "ten seeded 30-second music-like cover variants and virtual timeline offsets",
        "mapping_mode": "non_oracle_contrastive_local_pilot_threshold_sweep",
        "decoder_received_oracle_map": False,
        "profile": asdict(_profile()),
        "threshold_values": [asdict(threshold) | {"name": threshold.name} for threshold in thresholds],
        "carrier_band_hz": [500.0, 3800.0],
        "relative_difference": 0.95,
        "parity_symbols": 12,
        "repetition": 4,
        "summaries": list(summaries),
        "trials": [asdict(trial) for trial in trials],
    }


def main() -> None:
    """Print the complete reproducible local-pilot decoder threshold study as formatted JSON."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
