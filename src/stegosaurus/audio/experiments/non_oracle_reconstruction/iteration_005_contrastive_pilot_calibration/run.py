"""Run iteration 005: contrastive local-pilot calibration.

Experiment goal: improve clean non-oracle candidate-map selection after
iteration 004 showed that the split-pair payload channel recovers reliably with
the exact map. For each candidate rank, the encoder probes the full spectral
round trip, measures the expected local pilot at the selected frame and its
rival candidate, and selects by the weaker of payload margin, selected-pilot
margin, and selected-minus-rival pilot margin. The decoder remains unchanged:
it receives no encoder map and selects through known local-pilot evidence only.

Pipeline state: iteration 003 joint calibration restored about 84% selected-map
accuracy but still produced no non-oracle token recovery. Iteration 004 proves
that payload capacity is sufficient with the retained map. This experiment holds
the fixture, profiles, RS configuration, carrier band, and decoder thresholds
constant while making pilot discrimination the calibration objective.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from statistics import median

import numpy as np

from ....pilot import PcmAudio, SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioWatermarkConfig
from ...transport_optimization.iteration_004_four_frame_soft_combine.run import (
    FourFrameEmbedding,
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
    LocalPilotTrial,
    _control_token_match,
    _map_metrics,
    _profiles,
)
from ..iteration_003_joint_pilot_payload_calibration.run import (
    JointCalibratedLocalPilotExperiment,
)


@dataclass(frozen=True, slots=True)
class ContrastiveProbeEvidence:
    """Represent payload, selected-pilot, rival-pilot, and contrastive margins for one probe map."""

    payload_margins: tuple[tuple[float, ...], ...]
    selected_pilot_margins: tuple[tuple[float, ...], ...]
    rival_pilot_margins: tuple[tuple[float, ...], ...]
    pilot_gaps: tuple[tuple[float, ...], ...]


class ContrastivePilotCalibratedExperiment(JointCalibratedLocalPilotExperiment):
    """Calibrate carrier ranks by payload evidence and actual local-pilot rival discrimination."""

    def embed(self, audio: PcmAudio, token: bytes) -> FourFrameEmbedding:
        """Embed one token after selecting each rank by its conservative contrastive probe objective."""

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
        probe_evidence = tuple(
            self._probe_contrastive_evidence(
                audio,
                source_spectrum,
                tuple(replica_maps[rank] for replica_maps in ranked_maps),
                tuple(replica_maps[1 - rank] for replica_maps in ranked_maps),
                carrier_plan.carrier_bits,
                lower_bin,
                upper_bin,
            )
            for rank in range(self._candidate_rank_count)
        )
        replica_frame_indices = tuple(
            tuple(
                ranked_maps[replica_index][
                    self._best_contrastive_rank(probe_evidence, replica_index, carrier_index)
                ][carrier_index]
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

    def _probe_contrastive_evidence(
        self,
        audio: PcmAudio,
        source_spectrum: np.ndarray,
        selected_frame_indices: tuple[tuple[int, ...], ...],
        rival_frame_indices: tuple[tuple[int, ...], ...],
        carrier_bits: tuple[int, ...],
        lower_bin: int,
        upper_bin: int,
    ) -> ContrastiveProbeEvidence:
        """Measure a selected candidate's payload and pilot advantage over its rival after one round trip."""

        probe_spectrum = np.array(source_spectrum, copy=True)
        self._embed_mapped_bits(
            probe_spectrum,
            selected_frame_indices,
            carrier_bits,
            lower_bin,
            upper_bin,
        )
        probe_audio = PcmAudio(self._pilot._inverse_stft(probe_spectrum, audio), audio.sample_rate)
        _, observed_spectrum = self._pilot._stft(probe_audio)
        payload_margins: list[tuple[float, ...]] = []
        selected_pilot_margins: list[tuple[float, ...]] = []
        rival_pilot_margins: list[tuple[float, ...]] = []
        pilot_gaps: list[tuple[float, ...]] = []
        for replica_index, (selected_map, rival_map) in enumerate(zip(selected_frame_indices, rival_frame_indices)):
            replica_payload: list[float] = []
            replica_selected_pilot: list[float] = []
            replica_rival_pilot: list[float] = []
            replica_gaps: list[float] = []
            for carrier_index, (payload_bit, selected_frame, rival_frame) in enumerate(
                zip(carrier_bits, selected_map, rival_map)
            ):
                payload_score = self._score_at_frame(
                    observed_spectrum,
                    lower_bin,
                    upper_bin,
                    selected_frame,
                )
                selected_pilot_score = self.pilot_score_at_frame(
                    observed_spectrum,
                    lower_bin,
                    upper_bin,
                    selected_frame,
                )
                rival_pilot_score = self.pilot_score_at_frame(
                    observed_spectrum,
                    lower_bin,
                    upper_bin,
                    rival_frame,
                )
                payload_sign = 1.0 if payload_bit else -1.0
                pilot_sign = 1.0 if self.selection_pilot_bit(replica_index, carrier_index) else -1.0
                payload_margin = float("-inf") if payload_score is None else payload_sign * payload_score
                selected_pilot_margin = (
                    float("-inf") if selected_pilot_score is None else pilot_sign * selected_pilot_score
                )
                rival_pilot_margin = (
                    float("-inf") if rival_pilot_score is None else pilot_sign * rival_pilot_score
                )
                replica_payload.append(payload_margin)
                replica_selected_pilot.append(selected_pilot_margin)
                replica_rival_pilot.append(rival_pilot_margin)
                replica_gaps.append(selected_pilot_margin - rival_pilot_margin)
            payload_margins.append(tuple(replica_payload))
            selected_pilot_margins.append(tuple(replica_selected_pilot))
            rival_pilot_margins.append(tuple(replica_rival_pilot))
            pilot_gaps.append(tuple(replica_gaps))
        return ContrastiveProbeEvidence(
            tuple(payload_margins),
            tuple(selected_pilot_margins),
            tuple(rival_pilot_margins),
            tuple(pilot_gaps),
        )

    def _best_contrastive_rank(
        self,
        probe_evidence: tuple[ContrastiveProbeEvidence, ...],
        replica_index: int,
        carrier_index: int,
    ) -> int:
        """Select the rank with the strongest minimum payload, pilot, and selected-minus-rival margin."""

        return max(
            range(self._candidate_rank_count),
            key=lambda rank: (
                min(
                    probe_evidence[rank].payload_margins[replica_index][carrier_index],
                    probe_evidence[rank].selected_pilot_margins[replica_index][carrier_index],
                    probe_evidence[rank].pilot_gaps[replica_index][carrier_index],
                ),
                probe_evidence[rank].pilot_gaps[replica_index][carrier_index],
                probe_evidence[rank].selected_pilot_margins[replica_index][carrier_index],
                probe_evidence[rank].payload_margins[replica_index][carrier_index],
                -rank,
            ),
        )


def evaluate_trial(profile: LocalPilotProfile, trial_index: int) -> LocalPilotTrial:
    """Evaluate one contrastively calibrated profile on a clean cover and two exact-token controls."""

    token = bytes.fromhex("0123456789abcdef")
    source = _cover_variant(30, 6100 + trial_index, _trial_offset_seconds(trial_index))
    config = SpectralPilotConfig(
        minimum_frequency_hz=500.0,
        maximum_frequency_hz=3800.0,
        relative_difference=0.95,
    )
    watermark_config = AudioWatermarkConfig(parity_symbols=12)
    pilot = SpectralAudioPilot(b"audio-pilot-test-key", config, watermark_config)
    encoder = ContrastivePilotCalibratedExperiment(pilot, 0.01, profile)
    decoder = LocalPilotCandidateMapExperiment(encoder, 0.01)
    try:
        embedding = encoder.embed(source, token)
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
        wrong_pilot = SpectralAudioPilot(b"wrong-audio-pilot-test-key", config, watermark_config)
        wrong_encoder = ContrastivePilotCalibratedExperiment(wrong_pilot, 0.01, profile)
        wrong_decoder = LocalPilotCandidateMapExperiment(wrong_encoder, 0.01)
        wrong_secret = wrong_decoder.reconstruct(embedding.audio, wrong_pilot.schema.plan_attribution(token))
    except Exception as error:
        detail = str(error) or "no message"
        return LocalPilotTrial(profile.name, trial_index, None, None, None, None, None, f"{type(error).__name__}: {detail}")
    return LocalPilotTrial(
        profile.name,
        trial_index,
        embedding.signal_to_noise_db,
        _map_metrics(reconstruction, embedding),
        measurement,
        _control_token_match(unwatermarked, token),
        _control_token_match(wrong_secret, token),
        None,
    )


def _summary(profile: LocalPilotProfile, trials: tuple[LocalPilotTrial, ...]) -> dict[str, object]:
    """Aggregate contrastive calibration recovery, map, erasure, SNR, and control outcomes by profile."""

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
        "profile_name": profile.name,
        "pilot_pair_count": profile.pilot_pair_count,
        "payload_pair_count": 16 - profile.pilot_pair_count,
        "minimum_pilot_pairs": profile.minimum_pilot_pairs,
        "minimum_payload_pairs": profile.minimum_payload_pairs,
        "minimum_pilot_margin": profile.minimum_pilot_margin,
        "trial_count": len(trials),
        "execution_failures": sum(trial.error is not None for trial in trials),
        "exact_recoveries": sum(bool(measurement["token_matches_input"]) for measurement in measurements),
        "median_rs_cost": median(int(measurement["rs_error_cost"]) for measurement in measurements) if measurements else None,
        "maximum_rs_cost": max(int(measurement["rs_error_cost"]) for measurement in measurements) if measurements else None,
        "median_known_bit_errors": median(int(measurement["known_bit_errors"]) for measurement in measurements) if measurements else None,
        "median_carrier_erasures": median(int(measurement["carrier_erasures"]) for measurement in measurements) if measurements else None,
        "median_oracle_candidate_coverage": median(float(metric["oracle_candidate_coverage"]) for metric in map_metrics) if map_metrics else None,
        "median_selected_map_accuracy": median(selected_accuracy) if selected_accuracy else None,
        "median_selection_erasure_rate": median(float(metric["selection_erasure_rate"]) for metric in map_metrics) if map_metrics else None,
        "median_embedding_snr_db": median(snr_values) if snr_values else None,
        "unwatermarked_control_false_accepts": sum(bool(trial.unwatermarked_control_token_match) for trial in successful),
        "wrong_secret_control_false_accepts": sum(bool(trial.wrong_secret_control_token_match) for trial in successful),
    }


def run() -> dict[str, object]:
    """Run contrastive local-pilot calibration for both split-pair allocations over ten clean covers each."""

    profiles = _profiles()
    trials = tuple(
        trial
        for profile in profiles
        for trial_index in range(10)
        for trial in (evaluate_trial(profile, trial_index),)
    )
    summaries = tuple(
        _summary(profile, tuple(trial for trial in trials if trial.profile_name == profile.name))
        for profile in profiles
    )
    return {
        "fixture": "ten seeded 30-second music-like cover variants and virtual timeline offsets",
        "mapping_mode": "non_oracle_local_selection_pilot_contrastive_calibration",
        "decoder_received_oracle_map": False,
        "calibration_objective": "maximize min(payload_margin, selected_pilot_margin, selected_minus_rival_pilot_margin)",
        "carrier_band_hz": [500.0, 3800.0],
        "relative_difference": 0.95,
        "parity_symbols": 12,
        "repetition": 4,
        "profiles": [asdict(profile) for profile in profiles],
        "summaries": list(summaries),
        "trials": [asdict(trial) for trial in trials],
    }


def main() -> None:
    """Print the complete reproducible contrastive local-pilot calibration study as JSON."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
