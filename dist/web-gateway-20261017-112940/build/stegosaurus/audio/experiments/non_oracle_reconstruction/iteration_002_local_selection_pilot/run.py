"""Run iteration 002: local selection-pilot non-oracle reconstruction.

Experiment goal: test whether every payload carrier can carry its own
decoder-known map-selection signal. The encoder splits its 16 secret-keyed
spectral pairs into disjoint local-pilot and payload groups. It embeds a
secret-derived pilot bit and the opaque payload bit in the calibrated selected
frame. The decoder regenerates two observed candidates per stratum, selects a
frame only from the known local-pilot score, and extracts payload evidence from
the selected frame's separate payload pairs. Ambiguous local-pilot decisions
become erasures rather than data-driven frame guesses.

Pipeline state: non-oracle iteration 001 regenerated the encoder's candidate
frames with high coverage but recovered no tokens because four-copy data-bit
consensus selected wrong maps confidently. This study remains clean-audio,
synthetic, and transform-free. It compares a small four-pair local pilot and a
balanced eight-pair local pilot; it does not establish a production watermark.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
import hashlib
import hmac
import json
import math
from statistics import median

import numpy as np

from ....pilot import PcmAudio, SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioWatermarkConfig
from ....transport import CarrierPlan
from ...transport_optimization.iteration_004_four_frame_soft_combine.run import (
    FourFrameCapacityError,
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
class LocalPilotProfile:
    """Describe one disjoint local-pilot and payload-pair allocation."""

    name: str
    pilot_pair_count: int
    minimum_pilot_pairs: int
    minimum_payload_pairs: int
    minimum_pilot_margin: float


@dataclass(frozen=True, slots=True)
class LocalPilotReconstruction:
    """Record pilot-selected candidate frames and payload extraction without an oracle map."""

    candidate_frame_indices: tuple[tuple[tuple[int, ...], ...], ...]
    selected_candidate_ranks: tuple[tuple[int | None, ...], ...]
    selected_frame_indices: tuple[tuple[int | None, ...], ...]
    pilot_margins: tuple[tuple[float | None, ...], ...]
    extraction: FourFrameExtraction


@dataclass(frozen=True, slots=True)
class LocalPilotTrial:
    """Record one profile, clean cover, map reconstruction, and control outcome."""

    profile_name: str
    trial_index: int
    embedding_snr_db: float | None
    map_metrics: Mapping[str, object] | None
    measurement: Mapping[str, object] | None
    unwatermarked_control_token_match: bool | None
    wrong_secret_control_token_match: bool | None
    error: str | None


class LocalPilotCalibratedExperiment(CalibratedMarginExperiment):
    """Calibrate payload carriers while embedding a disjoint keyed local selection pilot."""

    def __init__(
        self,
        pilot: SpectralAudioPilot,
        minimum_combined_confidence: float,
        profile: LocalPilotProfile,
    ) -> None:
        """Initialize a calibrated encoder with one validated pilot-to-payload pair allocation."""

        super().__init__(pilot, minimum_combined_confidence)
        pair_count = pilot._config.pairs_per_frame
        payload_pair_count = pair_count - profile.pilot_pair_count
        if not 1 <= profile.pilot_pair_count < pair_count:
            raise ValueError("pilot_pair_count must leave at least one payload pair")
        if not 1 <= profile.minimum_pilot_pairs <= profile.pilot_pair_count:
            raise ValueError("minimum_pilot_pairs is outside the pilot pair allocation")
        if not 1 <= profile.minimum_payload_pairs <= payload_pair_count:
            raise ValueError("minimum_payload_pairs is outside the payload pair allocation")
        if profile.minimum_pilot_margin <= 0:
            raise ValueError("minimum_pilot_margin must be positive")
        self._profile = profile

    @property
    def profile(self) -> LocalPilotProfile:
        """Return the local-pilot allocation used for embedding and reconstruction."""

        return self._profile

    @property
    def payload_pair_count(self) -> int:
        """Return the number of disjoint keyed pairs reserved for the opaque payload bit."""

        return self._pilot._config.pairs_per_frame - self._profile.pilot_pair_count

    def _frame_quality(
        self,
        frame_spectrum: np.ndarray,
        lower_bin: int,
        upper_bin: int,
        frame_index: int,
    ) -> float | None:
        """Require sufficient observed energy in both local-pilot and payload pair groups."""

        if self._pilot._frame_rms(frame_spectrum) < self._pilot._config.minimum_frame_rms:
            return None
        pair_energies = tuple(
            float(abs(frame_spectrum[first_bin])) + float(abs(frame_spectrum[second_bin]))
            for first_bin, second_bin in self._pilot._pair_bins(lower_bin, upper_bin, frame_index)
        )
        usable_pilot = tuple(
            energy
            for energy in pair_energies[: self._profile.pilot_pair_count]
            if energy >= self._pilot._config.minimum_pair_magnitude
        )
        usable_payload = tuple(
            energy
            for energy in pair_energies[self._profile.pilot_pair_count :]
            if energy >= self._pilot._config.minimum_pair_magnitude
        )
        if len(usable_pilot) < self._profile.minimum_pilot_pairs:
            return None
        if len(usable_payload) < self._profile.minimum_payload_pairs:
            return None
        floor = self._pilot._config.minimum_pair_magnitude
        return sum(math.log(energy + floor) for energy in usable_pilot + usable_payload) / (
            len(usable_pilot) + len(usable_payload)
        )

    def _embed_mapped_bits(
        self,
        spectrum: np.ndarray,
        replica_frame_indices: tuple[tuple[int, ...], ...],
        carrier_bits: tuple[int, ...],
        lower_bin: int,
        upper_bin: int,
    ) -> None:
        """Embed a keyed selection pilot and payload bit into disjoint pairs for every mapped frame."""

        for replica_index, frame_map in enumerate(replica_frame_indices):
            for carrier_index, (payload_bit, frame_index) in enumerate(zip(carrier_bits, frame_map)):
                pilot_bit = self.selection_pilot_bit(replica_index, carrier_index)
                if not self._embed_local_frame(
                    spectrum[:, frame_index],
                    pilot_bit,
                    payload_bit,
                    lower_bin,
                    upper_bin,
                    frame_index,
                ):
                    raise FourFrameCapacityError("a local-pilot carrier frame became ineligible")

    def _embed_local_frame(
        self,
        frame_spectrum: np.ndarray,
        pilot_bit: int,
        payload_bit: int,
        lower_bin: int,
        upper_bin: int,
        frame_index: int,
    ) -> bool:
        """Apply local-pilot and payload modulation atomically while preserving pair-group separation."""

        if self._pilot._frame_rms(frame_spectrum) < self._pilot._config.minimum_frame_rms:
            return False
        modified_spectrum = np.array(frame_spectrum, copy=True)
        pairs = self._pilot._pair_bins(lower_bin, upper_bin, frame_index)
        pilot_usable = self._embed_pair_group(
            modified_spectrum,
            pilot_bit,
            pairs[: self._profile.pilot_pair_count],
            0,
            frame_index,
        )
        payload_usable = self._embed_pair_group(
            modified_spectrum,
            payload_bit,
            pairs[self._profile.pilot_pair_count :],
            self._profile.pilot_pair_count,
            frame_index,
        )
        if pilot_usable < self._profile.minimum_pilot_pairs:
            return False
        if payload_usable < self._profile.minimum_payload_pairs:
            return False
        frame_spectrum[:] = modified_spectrum
        return True

    def _embed_pair_group(
        self,
        frame_spectrum: np.ndarray,
        expected_bit: int,
        pairs: tuple[tuple[int, int], ...],
        pair_offset: int,
        frame_index: int,
    ) -> int:
        """Modulate one disjoint pair group and return its count of usable spectral pairs."""

        desired_sign = 1.0 if expected_bit else -1.0
        usable_pair_count = 0
        for local_pair_index, (first_bin, second_bin) in enumerate(pairs):
            first_magnitude = float(abs(frame_spectrum[first_bin]))
            second_magnitude = float(abs(frame_spectrum[second_bin]))
            pair_energy = first_magnitude + second_magnitude
            if pair_energy < self._pilot._config.minimum_pair_magnitude:
                continue
            chip = self._pilot._pair_chip(frame_index, pair_offset + local_pair_index)
            first_magnitude, second_magnitude = self._pilot._modulated_pair_magnitudes(
                first_magnitude,
                second_magnitude,
                desired_sign * chip * self._pilot._config.relative_difference,
            )
            frame_spectrum[first_bin] = self._pilot._with_magnitude(frame_spectrum[first_bin], first_magnitude)
            frame_spectrum[second_bin] = self._pilot._with_magnitude(frame_spectrum[second_bin], second_magnitude)
            usable_pair_count += 1
        return usable_pair_count

    def _score_at_frame(
        self,
        spectrum: np.ndarray,
        lower_bin: int,
        upper_bin: int,
        frame_index: int,
    ) -> float | None:
        """Return payload-only score for calibrated margins and post-selection token extraction."""

        if frame_index >= spectrum.shape[1]:
            return None
        return self._group_score(
            spectrum[:, frame_index],
            lower_bin,
            upper_bin,
            frame_index,
            self._profile.pilot_pair_count,
            self.payload_pair_count,
            self._profile.minimum_payload_pairs,
        )

    def pilot_score_at_frame(
        self,
        spectrum: np.ndarray,
        lower_bin: int,
        upper_bin: int,
        frame_index: int,
    ) -> float | None:
        """Return local-pilot-only score for one observed frame candidate."""

        if frame_index >= spectrum.shape[1]:
            return None
        return self._group_score(
            spectrum[:, frame_index],
            lower_bin,
            upper_bin,
            frame_index,
            0,
            self._profile.pilot_pair_count,
            self._profile.minimum_pilot_pairs,
        )

    def _group_score(
        self,
        frame_spectrum: np.ndarray,
        lower_bin: int,
        upper_bin: int,
        frame_index: int,
        pair_offset: int,
        pair_count: int,
        minimum_usable_pairs: int,
    ) -> float | None:
        """Return signed chip-corrected evidence from one configured disjoint pair group."""

        if self._pilot._frame_rms(frame_spectrum) < self._pilot._config.minimum_frame_rms:
            return None
        pair_scores: list[float] = []
        pairs = self._pilot._pair_bins(lower_bin, upper_bin, frame_index)
        for local_pair_index, (first_bin, second_bin) in enumerate(
            pairs[pair_offset : pair_offset + pair_count]
        ):
            first_magnitude = float(abs(frame_spectrum[first_bin]))
            second_magnitude = float(abs(frame_spectrum[second_bin]))
            pair_energy = first_magnitude + second_magnitude
            if pair_energy < self._pilot._config.minimum_pair_magnitude:
                continue
            chip = self._pilot._pair_chip(frame_index, pair_offset + local_pair_index)
            pair_scores.append(
                chip
                * math.log(
                    (first_magnitude + self._pilot._config.minimum_pair_magnitude)
                    / (second_magnitude + self._pilot._config.minimum_pair_magnitude)
                )
            )
        if len(pair_scores) < minimum_usable_pairs:
            return None
        return sum(pair_scores) / len(pair_scores)

    def selection_pilot_bit(self, replica_index: int, carrier_index: int) -> int:
        """Derive a secret domain-separated known pilot bit for one physical carrier replica."""

        digest = hmac.new(
            self._pilot._carrier_secret,
            b"local-selection-pilot|"
            + replica_index.to_bytes(4, "big")
            + carrier_index.to_bytes(4, "big"),
            hashlib.sha256,
        ).digest()
        return digest[0] & 1


class LocalPilotCandidateMapExperiment:
    """Select one observed carrier candidate exclusively from its decoder-known local pilot."""

    def __init__(self, encoder: LocalPilotCalibratedExperiment, minimum_combined_confidence: float) -> None:
        """Initialize pilot-guided non-oracle reconstruction with a payload confidence threshold."""

        if not 0 < minimum_combined_confidence < 1:
            raise ValueError("minimum_combined_confidence must be between zero and one")
        self._encoder = encoder
        self._pilot = encoder._pilot
        self._minimum_combined_confidence = minimum_combined_confidence

    def reconstruct(self, audio: PcmAudio, carrier_plan: CarrierPlan) -> LocalPilotReconstruction:
        """Regenerate candidates, choose them from local pilots, and recover payload bits without an oracle map."""

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
                best_rank = max(range(self._encoder._candidate_rank_count), key=lambda rank: (signed_scores[rank], -rank))
                other_rank = 1 - best_rank
                margin = signed_scores[best_rank] - signed_scores[other_rank]
                accepted = (
                    math.isfinite(signed_scores[best_rank])
                    and signed_scores[best_rank] >= self._encoder.profile.minimum_pilot_margin
                    and margin >= self._encoder.profile.minimum_pilot_margin
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
                replica_margins.append(margin)
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

    def _extract(
        self,
        replica_scores: tuple[tuple[float | None, ...], ...],
        carrier_plan: CarrierPlan,
    ) -> FourFrameExtraction:
        """Soft-combine pilot-selected payload scores and decode the protected token stream."""

        combined_scores = tuple(
            self._encoder._combine_scores(
                replica_scores[replica_index][carrier_index]
                for replica_index in range(self._encoder._replica_count)
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


def _profiles() -> tuple[LocalPilotProfile, ...]:
    """Return the pre-registered small and balanced local-pilot pair allocations."""

    return (
        LocalPilotProfile("small_pilot_4_payload_12", 4, 3, 6, 0.01),
        LocalPilotProfile("balanced_pilot_8_payload_8", 8, 6, 4, 0.01),
    )


def _map_metrics(
    reconstruction: LocalPilotReconstruction,
    embedding: FourFrameEmbedding,
) -> dict[str, object]:
    """Score pilot-guided candidate coverage, selected-map accuracy, and map erasures post hoc."""

    total_positions = 0
    candidate_covered = 0
    selected_positions = 0
    selected_matches = 0
    selection_erasures = 0
    for replica_index, oracle_map in enumerate(embedding.replica_frame_indices):
        for carrier_index, oracle_frame_index in enumerate(oracle_map):
            total_positions += 1
            candidate_frames = tuple(
                reconstruction.candidate_frame_indices[replica_index][rank][carrier_index]
                for rank in range(LocalPilotCalibratedExperiment._candidate_rank_count)
            )
            candidate_covered += int(oracle_frame_index in candidate_frames)
            selected_frame = reconstruction.selected_frame_indices[replica_index][carrier_index]
            if selected_frame is None:
                selection_erasures += 1
                continue
            selected_positions += 1
            selected_matches += int(selected_frame == oracle_frame_index)
    return {
        "physical_carrier_positions": total_positions,
        "oracle_candidate_coverage": candidate_covered / total_positions,
        "selected_map_accuracy": selected_matches / selected_positions if selected_positions else None,
        "selection_erasure_rate": selection_erasures / total_positions,
    }


def _control_token_match(reconstruction: LocalPilotReconstruction, token: bytes) -> bool:
    """Return whether one control reconstruction falsely yields the known token exactly."""

    return reconstruction.extraction.recovery.token == token


def evaluate_trial(profile: LocalPilotProfile, trial_index: int) -> LocalPilotTrial:
    """Evaluate one local-pilot profile on a clean cover and two exact-token negative controls."""

    token = bytes.fromhex("0123456789abcdef")
    source = _cover_variant(30, 6100 + trial_index, _trial_offset_seconds(trial_index))
    config = SpectralPilotConfig(
        minimum_frequency_hz=500.0,
        maximum_frequency_hz=3800.0,
        relative_difference=0.95,
    )
    watermark_config = AudioWatermarkConfig(parity_symbols=12)
    pilot = SpectralAudioPilot(b"audio-pilot-test-key", config, watermark_config)
    encoder = LocalPilotCalibratedExperiment(pilot, 0.01, profile)
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
        wrong_encoder = LocalPilotCalibratedExperiment(wrong_pilot, 0.01, profile)
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
    """Aggregate recovery, map selection, erasure, SNR, and control outcomes for one profile."""

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
    """Run both pre-registered local-pilot allocations across ten clean synthetic covers each."""

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
        "mapping_mode": "non_oracle_local_selection_pilot",
        "decoder_received_oracle_map": False,
        "carrier_band_hz": [500.0, 3800.0],
        "relative_difference": 0.95,
        "parity_symbols": 12,
        "repetition": 4,
        "profiles": [asdict(profile) for profile in profiles],
        "summaries": list(summaries),
        "trials": [asdict(trial) for trial in trials],
    }


def main() -> None:
    """Print the complete reproducible local-selection-pilot study as formatted JSON."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
