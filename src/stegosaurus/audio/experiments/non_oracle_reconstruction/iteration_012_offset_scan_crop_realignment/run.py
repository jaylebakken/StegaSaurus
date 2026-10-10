"""Run iteration 012: blind bounded-offset scan before crop reconstruction.

Experiment goal: test a keyed STFT timeline scan before local candidate ranking
on the exact leading and trailing 250 ms crop conditions that recovered 0/10
in iteration 011. The scan reconstructs the original 30-second four-replica
stratum geometry under every bounded source-frame offset, probes secret-derived
pilot signs on a sparse carrier subset, and only ranks every carrier at the
best offset when its evidence and runner-up gap meet fixed thresholds.

Pipeline state: the selected allocation is a 6-byte registry handle with 14
Reed--Solomon parity symbols, 184 framed carrier bits, four replicas, a
500--3800 Hz band, contrastive 4-pilot / 12-payload calibration, and frozen
blind pilot thresholds. No encoder frame map is supplied to this decoder. The
known crop displacement is retained only as a post-hoc result label, never as
an input to candidate generation, offset scoring, or payload extraction.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
import json
import math
from statistics import median

import numpy as np

from ....pilot import PcmAudio, SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioWatermarkConfig, CarrierPlan
from ...transport_optimization.iteration_004_four_frame_soft_combine.run import (
    FourFrameExtraction,
    _extraction_record,
)
from ...transport_optimization.iteration_006_duration_stability_bounds.run import (
    _cover_variant,
    _trial_offset_seconds,
)
from ..iteration_002_local_selection_pilot.run import (
    LocalPilotProfile,
    LocalPilotReconstruction,
    _control_token_match,
    _profiles,
)
from ..iteration_005_contrastive_pilot_calibration.run import ContrastivePilotCalibratedExperiment
from ..iteration_006_pilot_threshold_sweep.run import PilotThresholds, ThresholdedLocalPilotDecoder
from ..iteration_010_constant_codeword_allocation.run import CodewordAllocation, _allocations
from ..iteration_011_blind_attack_validation.run import AttackDefinition, _attack_definitions


@dataclass(frozen=True, slots=True)
class OffsetScanPolicy:
    """Configure the bounded secret-pilot offset search and conservative acceptance criteria."""

    maximum_offset_frames: int = 32
    probe_stride: int = 8
    minimum_probe_scores: int = 40
    minimum_mean_pilot_evidence: float = 0.02
    minimum_best_minus_runner_evidence: float = 0.005

    def __post_init__(self) -> None:
        """Validate finite bounded scan geometry and non-negative evidence thresholds."""

        if self.maximum_offset_frames < 0 or self.probe_stride < 1 or self.minimum_probe_scores < 1:
            raise ValueError("offset scan counts must be positive except maximum_offset_frames")
        thresholds = (self.minimum_mean_pilot_evidence, self.minimum_best_minus_runner_evidence)
        if any(not math.isfinite(value) or value < 0 for value in thresholds):
            raise ValueError("offset scan evidence thresholds must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class OffsetScore:
    """Record normalized secret-pilot evidence at one hypothetical source-frame offset."""

    offset_frames: int
    mean_pilot_evidence: float | None
    probe_score_count: int


@dataclass(frozen=True, slots=True)
class OffsetScanDecision:
    """Record the bounded offset search result without treating post-hoc truth as a decoder input."""

    searched_scores: tuple[OffsetScore, ...]
    selected_offset_frames: int | None
    selected_mean_pilot_evidence: float | None
    runner_up_mean_pilot_evidence: float | None
    best_minus_runner_evidence: float | None
    accepted: bool


@dataclass(frozen=True, slots=True)
class OffsetScanTrial:
    """Record one crop decode, bounded scan decision, RS result, and transformed controls."""

    attack_name: str
    trial_index: int
    cover_seed: int
    virtual_timeline_offset_seconds: float
    decoder_received_oracle_map: bool
    oracle_crop_offset_frames: int
    scan_searched_offset_count: int
    scan_selected_offset_frames: int | None
    scan_selected_mean_pilot_evidence: float | None
    scan_best_minus_runner_evidence: float | None
    scan_accepted: bool
    embedding_snr_db: float | None
    measurement: dict[str, object] | None
    unwatermarked_control_handle_match: bool | None
    wrong_secret_control_handle_match: bool | None
    error: str | None


def _selected_allocation() -> CodewordAllocation:
    """Return iteration 010's selected compact registry-handle allocation."""

    return next(allocation for allocation in _allocations() if allocation.name == "registry_handle_6_parity_14")


def _profile() -> LocalPilotProfile:
    """Return the frozen four-pilot / twelve-payload contrastive carrier allocation."""

    return next(profile for profile in _profiles() if profile.name == "small_pilot_4_payload_12")


def _threshold_policy() -> PilotThresholds:
    """Return the frozen local-pilot absolute-score and rival-gap payload policy."""

    return PilotThresholds(0.0, 0.24)


def _scan_policy() -> OffsetScanPolicy:
    """Return the declared ±512 ms single-hop offset scan and conservative acceptance thresholds."""

    return OffsetScanPolicy()


def _crop_attacks() -> tuple[AttackDefinition, ...]:
    """Return exactly iteration 011's leading and trailing 250 ms crop transformations."""

    crop_names = {"leading_crop_025s", "trailing_crop_025s"}
    return tuple(attack for attack in _attack_definitions() if attack.name in crop_names)


class OffsetScanningLocalPilotDecoder(ThresholdedLocalPilotDecoder):
    """Blindly synchronize a bounded source timeline from secret pilots before selecting local candidates."""

    def __init__(
        self,
        encoder: ContrastivePilotCalibratedExperiment,
        policy: OffsetScanPolicy,
        payload_thresholds: PilotThresholds,
        nominal_duration_seconds: float = 30.0,
    ) -> None:
        """Initialize fixed encoder dependencies, scan policy, payload thresholds, and nominal timeline length."""

        if not math.isfinite(nominal_duration_seconds) or nominal_duration_seconds <= 0:
            raise ValueError("nominal_duration_seconds must be finite and positive")
        super().__init__(encoder, 0.01, payload_thresholds)
        self._policy = policy
        self._payload_thresholds = payload_thresholds
        self._nominal_duration_seconds = nominal_duration_seconds

    def reconstruct(self, audio: PcmAudio, carrier_plan: CarrierPlan) -> tuple[LocalPilotReconstruction, OffsetScanDecision]:
        """Select a bounded timeline offset from pilots, then reconstruct local candidates without an oracle map."""

        frequencies, spectrum = self._pilot._stft(audio)
        lower_bin, upper_bin = self._pilot._frequency_bin_range(frequencies)
        nominal_frame_count = self._nominal_frame_count(audio.sample_rate)
        decision = self._select_offset(
            spectrum,
            carrier_plan,
            lower_bin,
            upper_bin,
            nominal_frame_count,
        )
        if decision.selected_offset_frames is None:
            return self._erasure_reconstruction(carrier_plan), decision
        reconstruction = self._reconstruct_at_offset(
            spectrum,
            carrier_plan,
            lower_bin,
            upper_bin,
            nominal_frame_count,
            decision.selected_offset_frames,
        )
        return reconstruction, decision

    def _nominal_frame_count(self, sample_rate: int) -> int:
        """Return the configured 30-second source-grid frame count without accessing an encoder source signal."""

        sample_count = int(round(self._nominal_duration_seconds * sample_rate))
        _, spectrum = self._pilot._stft(PcmAudio(np.zeros(sample_count, dtype=np.float64), sample_rate))
        return int(spectrum.shape[1])

    def _select_offset(
        self,
        spectrum: np.ndarray,
        carrier_plan: CarrierPlan,
        lower_bin: int,
        upper_bin: int,
        nominal_frame_count: int,
    ) -> OffsetScanDecision:
        """Score every bounded offset using sparse fixed-rank pilot evidence and accept only a separated winner."""

        scores = tuple(
            self._offset_score(
                spectrum,
                carrier_plan,
                lower_bin,
                upper_bin,
                nominal_frame_count,
                offset_frames,
            )
            for offset_frames in range(-self._policy.maximum_offset_frames, self._policy.maximum_offset_frames + 1)
        )
        ranked_scores = tuple(
            sorted(
                (score for score in scores if score.mean_pilot_evidence is not None),
                key=lambda score: (float(score.mean_pilot_evidence), -abs(score.offset_frames), -score.offset_frames),
                reverse=True,
            )
        )
        if not ranked_scores:
            return OffsetScanDecision(scores, None, None, None, None, False)
        best = ranked_scores[0]
        runner_up = ranked_scores[1] if len(ranked_scores) > 1 else None
        runner_up_evidence = runner_up.mean_pilot_evidence if runner_up is not None else None
        gap = (
            float(best.mean_pilot_evidence) - float(runner_up_evidence)
            if runner_up_evidence is not None
            else float("inf")
        )
        accepted = (
            best.probe_score_count >= self._policy.minimum_probe_scores
            and float(best.mean_pilot_evidence) >= self._policy.minimum_mean_pilot_evidence
            and gap >= self._policy.minimum_best_minus_runner_evidence
        )
        return OffsetScanDecision(
            scores,
            best.offset_frames if accepted else None,
            best.mean_pilot_evidence,
            runner_up_evidence,
            gap,
            accepted,
        )

    def _offset_score(
        self,
        spectrum: np.ndarray,
        carrier_plan: CarrierPlan,
        lower_bin: int,
        upper_bin: int,
        nominal_frame_count: int,
        offset_frames: int,
    ) -> OffsetScore:
        """Average expected-signed pilot evidence across sparse source strata at one hypothetical offset."""

        evidence: list[float] = []
        for replica_index, source_replica_range in enumerate(self._encoder._replica_ranges(nominal_frame_count)):
            for carrier_index, source_stratum in enumerate(
                self._encoder._strata(source_replica_range, len(carrier_plan.carrier_bits))
            ):
                if carrier_index % self._policy.probe_stride:
                    continue
                expected_sign = 1.0 if self._encoder.selection_pilot_bit(replica_index, carrier_index) else -1.0
                for observed_frame, source_frame in self._ranked_candidates(
                    spectrum,
                    source_stratum,
                    lower_bin,
                    upper_bin,
                    offset_frames,
                ):
                    if observed_frame is None or source_frame is None:
                        continue
                    score = self._pilot_score(spectrum, observed_frame, source_frame, lower_bin, upper_bin)
                    if score is not None:
                        evidence.append(expected_sign * score)
        mean_evidence = sum(evidence) / len(evidence) if evidence else None
        return OffsetScore(offset_frames, mean_evidence, len(evidence))

    def _reconstruct_at_offset(
        self,
        spectrum: np.ndarray,
        carrier_plan: CarrierPlan,
        lower_bin: int,
        upper_bin: int,
        nominal_frame_count: int,
        offset_frames: int,
    ) -> LocalPilotReconstruction:
        """Rank full rebased candidate maps and decode payload scores at one accepted source-time offset."""

        candidate_maps = tuple(
            tuple(
                self._ranked_candidates(
                    spectrum,
                    source_stratum,
                    lower_bin,
                    upper_bin,
                    offset_frames,
                )
                for source_stratum in self._encoder._strata(source_replica_range, len(carrier_plan.carrier_bits))
            )
            for source_replica_range in self._encoder._replica_ranges(nominal_frame_count)
        )
        selected_ranks: list[list[int | None]] = []
        selected_frames: list[list[int | None]] = []
        pilot_margins: list[list[float | None]] = []
        replica_scores: list[list[float | None]] = []
        rank_maps: list[tuple[tuple[int | None, ...], ...]] = []
        for replica_index, replica_candidates in enumerate(candidate_maps):
            rank_zero = tuple(candidate[0][0] for candidate in replica_candidates)
            rank_one = tuple(candidate[1][0] for candidate in replica_candidates)
            rank_maps.append((rank_zero, rank_one))
            replica_ranks: list[int | None] = []
            replica_frames: list[int | None] = []
            replica_margins: list[float | None] = []
            replica_payload_scores: list[float | None] = []
            for carrier_index, candidates in enumerate(replica_candidates):
                expected_sign = 1.0 if self._encoder.selection_pilot_bit(replica_index, carrier_index) else -1.0
                signed_scores = tuple(
                    float("-inf")
                    if observed_frame is None or source_frame is None or (score := self._pilot_score(spectrum, observed_frame, source_frame, lower_bin, upper_bin)) is None
                    else expected_sign * score
                    for observed_frame, source_frame in candidates
                )
                best_rank = max(range(self._encoder._candidate_rank_count), key=lambda rank: (signed_scores[rank], -rank))
                rival_rank = 1 - best_rank
                best_observed_frame, best_source_frame = candidates[best_rank]
                gap = signed_scores[best_rank] - signed_scores[rival_rank]
                accepted = (
                    math.isfinite(signed_scores[best_rank])
                    and signed_scores[best_rank] >= self._payload_thresholds.absolute_pilot_threshold
                    and gap >= self._payload_thresholds.pilot_gap_threshold
                )
                if not accepted or best_observed_frame is None or best_source_frame is None:
                    replica_ranks.append(None)
                    replica_frames.append(None)
                    replica_margins.append(None)
                    replica_payload_scores.append(None)
                    continue
                replica_ranks.append(best_rank)
                replica_frames.append(best_observed_frame)
                replica_margins.append(gap)
                replica_payload_scores.append(
                    self._payload_score(spectrum, best_observed_frame, best_source_frame, lower_bin, upper_bin)
                )
            selected_ranks.append(replica_ranks)
            selected_frames.append(replica_frames)
            pilot_margins.append(replica_margins)
            replica_scores.append(replica_payload_scores)
        extraction = self._extract(tuple(tuple(scores) for scores in replica_scores), carrier_plan)
        return LocalPilotReconstruction(
            tuple(tuple(rank_map) for rank_map in rank_maps),
            tuple(tuple(ranks) for ranks in selected_ranks),
            tuple(tuple(frames) for frames in selected_frames),
            tuple(tuple(margins) for margins in pilot_margins),
            extraction,
        )

    def _ranked_candidates(
        self,
        spectrum: np.ndarray,
        source_stratum: range,
        lower_bin: int,
        upper_bin: int,
        offset_frames: int,
    ) -> tuple[tuple[int | None, int | None], tuple[int | None, int | None]]:
        """Return two quality-ranked observed candidates while retaining their hypothesized source indices."""

        ranked: list[tuple[float, int, int]] = []
        for source_frame in source_stratum:
            observed_frame = source_frame - offset_frames
            if not 0 <= observed_frame < spectrum.shape[1]:
                continue
            quality = self._encoder._frame_quality(
                spectrum[:, observed_frame],
                lower_bin,
                upper_bin,
                source_frame,
            )
            if quality is not None:
                ranked.append((quality, observed_frame, source_frame))
        ranked.sort(reverse=True)
        candidates = tuple((observed_frame, source_frame) for _, observed_frame, source_frame in ranked[:2])
        return tuple(candidates[index] if index < len(candidates) else (None, None) for index in range(2))

    def _pilot_score(
        self,
        spectrum: np.ndarray,
        observed_frame: int,
        source_frame: int,
        lower_bin: int,
        upper_bin: int,
    ) -> float | None:
        """Score observed pilot pairs using the offset-rebased source index for keyed bins and chips."""

        return self._encoder._group_score(
            spectrum[:, observed_frame],
            lower_bin,
            upper_bin,
            source_frame,
            0,
            self._profile().pilot_pair_count,
            self._profile().minimum_pilot_pairs,
        )

    def _payload_score(
        self,
        spectrum: np.ndarray,
        observed_frame: int,
        source_frame: int,
        lower_bin: int,
        upper_bin: int,
    ) -> float | None:
        """Score observed payload pairs using the offset-rebased source index for keyed bins and chips."""

        profile = self._profile()
        return self._encoder._group_score(
            spectrum[:, observed_frame],
            lower_bin,
            upper_bin,
            source_frame,
            profile.pilot_pair_count,
            self._encoder.payload_pair_count,
            profile.minimum_payload_pairs,
        )

    def _profile(self) -> LocalPilotProfile:
        """Return the local-pilot allocation owned by the frozen contrastive encoder."""

        return self._encoder._profile

    def _erasure_reconstruction(self, carrier_plan: CarrierPlan) -> LocalPilotReconstruction:
        """Return a deliberate all-erasure decode when no offset meets the keyed scan acceptance rule."""

        carrier_count = len(carrier_plan.carrier_bits)
        empty_maps = tuple(
            tuple(tuple(None for _ in range(carrier_count)) for _ in range(self._encoder._candidate_rank_count))
            for _ in range(self._encoder._replica_count)
        )
        empty_values = tuple(tuple(None for _ in range(carrier_count)) for _ in range(self._encoder._replica_count))
        extraction = self._extract(empty_values, carrier_plan)
        return LocalPilotReconstruction(empty_maps, empty_values, empty_values, empty_values, extraction)


def _measured_extraction(reconstruction: LocalPilotReconstruction, token: bytes) -> FourFrameExtraction:
    """Convert offset-scanned blind reconstruction output into the shared transport measurement record shape."""

    extraction = reconstruction.extraction
    return FourFrameExtraction(
        extraction.replica_scores,
        extraction.combined_scores,
        extraction.observed_carrier_bits,
        extraction.known_bit_errors,
        extraction.carrier_erasures,
        extraction.recovery,
        extraction.recovery.token == token,
    )


def _oracle_crop_offset_frames(attack: AttackDefinition) -> int:
    """Return the known crop displacement only as a post-hoc label for the fixed named transformations."""

    if attack.name == "leading_crop_025s":
        return 16
    if attack.name == "trailing_crop_025s":
        return 0
    raise ValueError("attack is not a declared crop transformation")


def evaluate_variant(trial_index: int, attacks: Iterable[AttackDefinition]) -> tuple[OffsetScanTrial, ...]:
    """Embed one iteration-011 cover and evaluate the bounded offset scan on each unchanged crop attack."""

    allocation = _selected_allocation()
    token = allocation.token()
    cover_seed = 6600 + trial_index
    timeline_offset = _trial_offset_seconds(400 + trial_index)
    source = _cover_variant(30, cover_seed, timeline_offset)
    watermark_config = AudioWatermarkConfig(allocation.payload_bytes, allocation.parity_symbols)
    attacks = tuple(attacks)
    pilot_config = SpectralPilotConfig(
        minimum_frequency_hz=500.0,
        maximum_frequency_hz=3800.0,
        relative_difference=0.95,
    )
    pilot = SpectralAudioPilot(b"audio-pilot-test-key", pilot_config, watermark_config)
    encoder = ContrastivePilotCalibratedExperiment(pilot, 0.01, _profile())
    decoder = OffsetScanningLocalPilotDecoder(encoder, _scan_policy(), _threshold_policy())
    try:
        embedding = encoder.embed(source, token)
        wrong_pilot = SpectralAudioPilot(b"wrong-audio-pilot-test-key", pilot_config, watermark_config)
        wrong_encoder = ContrastivePilotCalibratedExperiment(wrong_pilot, 0.01, _profile())
        wrong_decoder = OffsetScanningLocalPilotDecoder(wrong_encoder, _scan_policy(), _threshold_policy())
        wrong_plan = wrong_pilot.schema.plan_attribution(token)
    except Exception as error:
        detail = str(error) or "no message"
        return tuple(
            OffsetScanTrial(
                attack.name, trial_index, cover_seed, timeline_offset, False, _oracle_crop_offset_frames(attack), 65,
                None, None, None, False, None, None, None, None, f"{type(error).__name__}: {detail}",
            )
            for attack in attacks
        )
    records: list[OffsetScanTrial] = []
    for attack in attacks:
        try:
            attacked_audio = attack.transform(embedding.audio, 7000 + trial_index)
            reconstruction, decision = decoder.reconstruct(attacked_audio, embedding.carrier_plan)
            measurement = _extraction_record(encoder, embedding, _measured_extraction(reconstruction, token))
            unwatermarked, _ = decoder.reconstruct(attack.transform(source, 7000 + trial_index), embedding.carrier_plan)
            wrong_secret, _ = wrong_decoder.reconstruct(attack.transform(embedding.audio, 7000 + trial_index), wrong_plan)
        except Exception as error:
            detail = str(error) or "no message"
            records.append(
                OffsetScanTrial(
                    attack.name, trial_index, cover_seed, timeline_offset, False, _oracle_crop_offset_frames(attack), 65,
                    None, None, None, False, embedding.signal_to_noise_db, None, None, None,
                    f"{type(error).__name__}: {detail}",
                )
            )
            continue
        records.append(
            OffsetScanTrial(
                attack.name,
                trial_index,
                cover_seed,
                timeline_offset,
                False,
                _oracle_crop_offset_frames(attack),
                len(decision.searched_scores),
                decision.selected_offset_frames,
                decision.selected_mean_pilot_evidence,
                decision.best_minus_runner_evidence,
                decision.accepted,
                embedding.signal_to_noise_db,
                measurement,
                _control_token_match(unwatermarked, token),
                _control_token_match(wrong_secret, token),
                None,
            )
        )
    return tuple(records)


def _summary(attack: AttackDefinition, trials: tuple[OffsetScanTrial, ...]) -> dict[str, object]:
    """Aggregate scan acceptance, post-hoc offset agreement, RS recovery, and controls for one crop direction."""

    measurements = tuple(trial.measurement for trial in trials if trial.measurement is not None)
    accepted = tuple(trial for trial in trials if trial.scan_accepted and trial.scan_selected_offset_frames is not None)
    offset_errors = tuple(
        abs(int(trial.scan_selected_offset_frames) - trial.oracle_crop_offset_frames)
        for trial in accepted
        if trial.scan_selected_offset_frames is not None
    )
    return {
        "attack_name": attack.name,
        "trial_count": len(trials),
        "execution_failures": sum(trial.error is not None for trial in trials),
        "scan_acceptances": len(accepted),
        "median_selected_offset_frames": median(
            int(trial.scan_selected_offset_frames) for trial in accepted if trial.scan_selected_offset_frames is not None
        ) if accepted else None,
        "median_absolute_posthoc_offset_error_frames": median(offset_errors) if offset_errors else None,
        "median_selected_pilot_evidence": median(
            float(trial.scan_selected_mean_pilot_evidence)
            for trial in accepted
            if trial.scan_selected_mean_pilot_evidence is not None
        ) if accepted else None,
        "median_best_minus_runner_evidence": median(
            float(trial.scan_best_minus_runner_evidence)
            for trial in accepted
            if trial.scan_best_minus_runner_evidence is not None
        ) if accepted else None,
        "exact_recoveries": sum(bool(measurement["token_matches_input"]) for measurement in measurements),
        "median_rs_cost": median(int(measurement["rs_error_cost"]) for measurement in measurements) if measurements else None,
        "maximum_rs_cost": max(int(measurement["rs_error_cost"]) for measurement in measurements) if measurements else None,
        "median_carrier_erasures": median(int(measurement["carrier_erasures"]) for measurement in measurements) if measurements else None,
        "unwatermarked_control_false_accepts": sum(bool(trial.unwatermarked_control_handle_match) for trial in trials),
        "wrong_secret_control_false_accepts": sum(bool(trial.wrong_secret_control_handle_match) for trial in trials),
    }


def run() -> dict[str, object]:
    """Run the bounded blind offset scan over the unchanged leading and trailing crop fixture."""

    attacks = _crop_attacks()
    trials = tuple(record for trial_index in range(10) for record in evaluate_variant(trial_index, attacks))
    allocation = _selected_allocation()
    return {
        "fixture": "iteration 011's ten 30-second synthetic crop variants, reused solely for direct alignment comparison",
        "mapping_mode": "blind_non_oracle_bounded_offset_scan",
        "decoder_received_oracle_map": False,
        "posthoc_oracle_offset_label": "The crop displacement label is retained only for evaluation after decoding.",
        "allocation": asdict(allocation),
        "protected_codeword_bytes": allocation.payload_bytes + allocation.parity_symbols,
        "carrier_bit_count": 184,
        "physical_carrier_count": 736,
        "profile": asdict(_profile()),
        "payload_thresholds": asdict(_threshold_policy()),
        "offset_scan_policy": asdict(_scan_policy()),
        "offset_search_duration_ms": 512.0,
        "validation_cover_seeds": list(range(6600, 6610)),
        "summaries": [
            _summary(attack, tuple(trial for trial in trials if trial.attack_name == attack.name))
            for attack in attacks
        ],
        "trials": [asdict(trial) for trial in trials],
    }


def main() -> None:
    """Print the reproducible bounded-offset crop realignment experiment as formatted JSON."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
