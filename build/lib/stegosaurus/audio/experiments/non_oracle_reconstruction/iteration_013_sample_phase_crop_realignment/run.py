"""Run iteration 013: bounded sample-phase realignment after a blind coarse offset scan.

Experiment goal: test the hypothesis raised by iteration 012's split crop
result. That experiment often selected the correct nearest STFT frame for a
250 ms leading crop, but 250 ms is 15.625 current analysis hops; whole-frame
alignment therefore left a fractional sample-domain phase mismatch. This
experiment keeps every transport and attack setting fixed, first selects a
coarse source-frame offset from keyed pilot evidence, then evaluates nine
sample-domain STFT-origin phases around the residual consistent with a single
edge crop before running full local-pilot candidate ranking.

Pipeline state: no source map, crop direction, crop duration, or crop sample
position is supplied to the decoder. Expected crop values appear only as
post-hoc labels. The residual model intentionally supports only a short,
bounded single-edge crop on the current 30-second, 16 kHz synthetic fixture;
it does not claim general synchronization for arbitrary timing edits.
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
from ..iteration_006_pilot_threshold_sweep.run import PilotThresholds
from ..iteration_010_constant_codeword_allocation.run import CodewordAllocation, _allocations
from ..iteration_011_blind_attack_validation.run import AttackDefinition, _attack_definitions
from ..iteration_012_offset_scan_crop_realignment.run import (
    OffsetScanDecision,
    OffsetScanningLocalPilotDecoder,
    _scan_policy,
)


@dataclass(frozen=True, slots=True)
class ResidualPhasePolicy:
    """Configure a short sample-domain search around one coarse edge-crop-consistent residual."""

    radius_samples: int = 16
    step_samples: int = 4
    minimum_mean_pilot_evidence: float = 0.02
    minimum_best_minus_runner_evidence: float = 0.005

    def __post_init__(self) -> None:
        """Validate symmetric phase-search geometry and finite non-negative pilot-evidence thresholds."""

        if self.radius_samples < 0 or self.step_samples < 1:
            raise ValueError("residual phase counts must be non-negative and positive")
        if self.radius_samples % self.step_samples:
            raise ValueError("residual phase radius must be divisible by its step")
        if any(
            not math.isfinite(value) or value < 0
            for value in (self.minimum_mean_pilot_evidence, self.minimum_best_minus_runner_evidence)
        ):
            raise ValueError("residual phase evidence thresholds must be finite and non-negative")


@dataclass(frozen=True, slots=True)
class ResidualPhaseScore:
    """Record pilot evidence for one sample-domain analysis-origin hypothesis at a fixed coarse offset."""

    phase_samples: int
    mean_pilot_evidence: float | None
    probe_score_count: int


@dataclass(frozen=True, slots=True)
class ResidualPhaseDecision:
    """Record residual candidate scoring and conservative acceptance after coarse keyed synchronization."""

    searched_scores: tuple[ResidualPhaseScore, ...]
    selected_phase_samples: int | None
    selected_mean_pilot_evidence: float | None
    runner_up_mean_pilot_evidence: float | None
    best_minus_runner_evidence: float | None
    accepted: bool


@dataclass(frozen=True, slots=True)
class SamplePhaseTrial:
    """Record one coarse-to-fine blind crop decode, post-hoc labels, RS result, and controls."""

    attack_name: str
    trial_index: int
    cover_seed: int
    virtual_timeline_offset_seconds: float
    decoder_received_oracle_map: bool
    oracle_crop_offset_frames: int
    oracle_analysis_phase_samples: int
    coarse_offset_frames: int | None
    coarse_scan_accepted: bool
    residual_phase_candidate_count: int
    residual_selected_phase_samples: int | None
    residual_scan_accepted: bool
    residual_selected_mean_pilot_evidence: float | None
    residual_best_minus_runner_evidence: float | None
    embedding_snr_db: float | None
    measurement: dict[str, object] | None
    unwatermarked_control_handle_match: bool | None
    wrong_secret_control_handle_match: bool | None
    error: str | None


def _selected_allocation() -> CodewordAllocation:
    """Return the compact six-byte handle and fourteen-parity allocation held fixed since iteration 010."""

    return next(allocation for allocation in _allocations() if allocation.name == "registry_handle_6_parity_14")


def _profile() -> LocalPilotProfile:
    """Return the frozen four-pilot / twelve-payload local-pilot allocation."""

    return next(profile for profile in _profiles() if profile.name == "small_pilot_4_payload_12")


def _threshold_policy() -> PilotThresholds:
    """Return the frozen absolute pilot and rival-gap payload decision policy."""

    return PilotThresholds(0.0, 0.24)


def _phase_policy() -> ResidualPhasePolicy:
    """Return the declared nine-candidate residual search around each feasible edge-crop phase."""

    return ResidualPhasePolicy()


def _crop_attacks() -> tuple[AttackDefinition, ...]:
    """Return the same 250 ms leading and trailing crop definitions used by iterations 011 and 012."""

    crop_names = {"leading_crop_025s", "trailing_crop_025s"}
    return tuple(attack for attack in _attack_definitions() if attack.name in crop_names)


class SamplePhaseLocalPilotDecoder:
    """Perform a keyed coarse frame scan followed by a bounded sample-origin pilot scan before extraction."""

    def __init__(
        self,
        encoder: ContrastivePilotCalibratedExperiment,
        nominal_duration_seconds: float = 30.0,
    ) -> None:
        """Initialize the inherited coarse scanner, fixed payload policy, and bounded residual search policy."""

        self._coarse_decoder = OffsetScanningLocalPilotDecoder(
            encoder,
            _scan_policy(),
            _threshold_policy(),
            nominal_duration_seconds,
        )
        self._encoder = encoder
        self._pilot = encoder._pilot
        self._phase_policy = _phase_policy()
        self._nominal_duration_seconds = nominal_duration_seconds

    def reconstruct(
        self,
        audio: PcmAudio,
        carrier_plan: CarrierPlan,
    ) -> tuple[LocalPilotReconstruction, OffsetScanDecision, ResidualPhaseDecision]:
        """Blindly select a coarse offset, scan feasible residual phases, and recover payload candidates at both decisions."""

        frequencies, spectrum = self._pilot._stft(audio)
        lower_bin, upper_bin = self._pilot._frequency_bin_range(frequencies)
        nominal_frame_count = self._coarse_decoder._nominal_frame_count(audio.sample_rate)
        coarse_decision = self._coarse_decoder._select_offset(
            spectrum,
            carrier_plan,
            lower_bin,
            upper_bin,
            nominal_frame_count,
        )
        if coarse_decision.selected_offset_frames is None:
            return (
                self._coarse_decoder._erasure_reconstruction(carrier_plan),
                coarse_decision,
                ResidualPhaseDecision((), None, None, None, None, False),
            )
        phase_decision, phase_spectra = self._select_phase(
            audio,
            carrier_plan,
            lower_bin,
            upper_bin,
            nominal_frame_count,
            coarse_decision.selected_offset_frames,
        )
        if phase_decision.selected_phase_samples is None:
            return self._coarse_decoder._erasure_reconstruction(carrier_plan), coarse_decision, phase_decision
        selected_spectrum = phase_spectra[phase_decision.selected_phase_samples]
        reconstruction = self._coarse_decoder._reconstruct_at_offset(
            selected_spectrum,
            carrier_plan,
            lower_bin,
            upper_bin,
            nominal_frame_count,
            coarse_decision.selected_offset_frames,
        )
        return reconstruction, coarse_decision, phase_decision

    def _select_phase(
        self,
        audio: PcmAudio,
        carrier_plan: CarrierPlan,
        lower_bin: int,
        upper_bin: int,
        nominal_frame_count: int,
        coarse_offset_frames: int,
    ) -> tuple[ResidualPhaseDecision, dict[int, np.ndarray]]:
        """Score feasible sample-origin hypotheses using keyed pilots while retaining spectra for the winning phase."""

        center_phase = self._edge_crop_phase_center(audio, coarse_offset_frames)
        if center_phase is None:
            return ResidualPhaseDecision((), None, None, None, None, False), {}
        phase_spectra: dict[int, np.ndarray] = {}
        scores: list[ResidualPhaseScore] = []
        for phase_samples in range(
            center_phase - self._phase_policy.radius_samples,
            center_phase + self._phase_policy.radius_samples + 1,
            self._phase_policy.step_samples,
        ):
            reframed = self._reframe_audio(audio, phase_samples)
            _, spectrum = self._pilot._stft(reframed)
            phase_spectra[phase_samples] = spectrum
            score = self._coarse_decoder._offset_score(
                spectrum,
                carrier_plan,
                lower_bin,
                upper_bin,
                nominal_frame_count,
                coarse_offset_frames,
            )
            scores.append(ResidualPhaseScore(phase_samples, score.mean_pilot_evidence, score.probe_score_count))
        ranked = tuple(
            sorted(
                (score for score in scores if score.mean_pilot_evidence is not None),
                key=lambda score: (float(score.mean_pilot_evidence), -abs(score.phase_samples), -score.phase_samples),
                reverse=True,
            )
        )
        if not ranked:
            return ResidualPhaseDecision(tuple(scores), None, None, None, None, False), phase_spectra
        best = ranked[0]
        runner_up = ranked[1] if len(ranked) > 1 else None
        runner_up_evidence = runner_up.mean_pilot_evidence if runner_up is not None else None
        gap = (
            float(best.mean_pilot_evidence) - float(runner_up_evidence)
            if runner_up_evidence is not None
            else float("inf")
        )
        accepted = (
            best.probe_score_count >= _scan_policy().minimum_probe_scores
            and float(best.mean_pilot_evidence) >= self._phase_policy.minimum_mean_pilot_evidence
            and gap >= self._phase_policy.minimum_best_minus_runner_evidence
        )
        return (
            ResidualPhaseDecision(
                tuple(scores),
                best.phase_samples if accepted else None,
                best.mean_pilot_evidence,
                runner_up_evidence,
                gap,
                accepted,
            ),
            phase_spectra,
        )

    def _edge_crop_phase_center(self, audio: PcmAudio, coarse_offset_frames: int) -> int | None:
        """Derive one feasible residual from received-length loss under a bounded single-edge-crop model."""

        nominal_sample_count = int(round(self._nominal_duration_seconds * audio.sample_rate))
        missing_samples = nominal_sample_count - len(audio.samples)
        hop_size = self._pilot._config.hop_size
        if missing_samples < 0:
            return None
        if coarse_offset_frames == 0:
            return 0
        center_phase = coarse_offset_frames * hop_size - missing_samples
        if -hop_size < center_phase < hop_size:
            return center_phase
        return None

    def _reframe_audio(self, audio: PcmAudio, phase_samples: int) -> PcmAudio:
        """Shift the STFT analysis origin by trimming or zero-prepending a bounded sample-domain phase."""

        if phase_samples >= 0:
            return PcmAudio(np.asarray(audio.samples[phase_samples:], dtype=np.float64), audio.sample_rate)
        padding = np.zeros(-phase_samples, dtype=np.float64)
        return PcmAudio(np.concatenate((padding, audio.samples)), audio.sample_rate)


def _measured_extraction(reconstruction: LocalPilotReconstruction, token: bytes) -> FourFrameExtraction:
    """Convert the coarse-to-fine blind reconstruction result to the shared transport measurement shape."""

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


def _oracle_crop_labels(attack: AttackDefinition) -> tuple[int, int]:
    """Return fixed crop frame/phase labels only for post-hoc scoring of the unchanged named fixture."""

    if attack.name == "leading_crop_025s":
        return 16, 96
    if attack.name == "trailing_crop_025s":
        return 0, 0
    raise ValueError("attack is not a declared crop transformation")


def evaluate_variant(trial_index: int, attacks: Iterable[AttackDefinition]) -> tuple[SamplePhaseTrial, ...]:
    """Embed one fixed crop-fixture cover and run independent coarse-to-fine blind decodes for every crop/control."""

    allocation = _selected_allocation()
    token = allocation.token()
    cover_seed = 6600 + trial_index
    timeline_offset = _trial_offset_seconds(400 + trial_index)
    source = _cover_variant(30, cover_seed, timeline_offset)
    watermark_config = AudioWatermarkConfig(
        attribution_token_bytes=allocation.payload_bytes,
        parity_symbols=allocation.parity_symbols,
    )
    attack_values = tuple(attacks)
    pilot_config = SpectralPilotConfig(
        minimum_frequency_hz=500.0,
        maximum_frequency_hz=3800.0,
        relative_difference=0.95,
    )
    pilot = SpectralAudioPilot(b"audio-pilot-test-key", pilot_config, watermark_config)
    encoder = ContrastivePilotCalibratedExperiment(pilot, 0.01, _profile())
    decoder = SamplePhaseLocalPilotDecoder(encoder)
    try:
        embedding = encoder.embed(source, token)
        wrong_pilot = SpectralAudioPilot(b"wrong-audio-pilot-test-key", pilot_config, watermark_config)
        wrong_encoder = ContrastivePilotCalibratedExperiment(wrong_pilot, 0.01, _profile())
        wrong_decoder = SamplePhaseLocalPilotDecoder(wrong_encoder)
        wrong_plan = wrong_pilot.schema.plan_attribution(token)
    except Exception as error:
        detail = str(error) or "no message"
        return tuple(
            SamplePhaseTrial(
                attack.name, trial_index, cover_seed, timeline_offset, False, *_oracle_crop_labels(attack),
                None, False, 0, None, False, None, None, None, None, None, f"{type(error).__name__}: {detail}",
            )
            for attack in attack_values
        )
    records: list[SamplePhaseTrial] = []
    for attack in attack_values:
        try:
            seed = 7000 + trial_index
            attacked_audio = attack.transform(embedding.audio, seed)
            reconstruction, coarse, residual = decoder.reconstruct(attacked_audio, embedding.carrier_plan)
            measurement = _extraction_record(encoder, embedding, _measured_extraction(reconstruction, token))
            unwatermarked, _, _ = decoder.reconstruct(attack.transform(source, seed), embedding.carrier_plan)
            wrong_secret, _, _ = wrong_decoder.reconstruct(attack.transform(embedding.audio, seed), wrong_plan)
        except Exception as error:
            detail = str(error) or "no message"
            records.append(
                SamplePhaseTrial(
                    attack.name, trial_index, cover_seed, timeline_offset, False, *_oracle_crop_labels(attack),
                    None, False, 0, None, False, None, None, embedding.signal_to_noise_db, None, None, None,
                    f"{type(error).__name__}: {detail}",
                )
            )
            continue
        records.append(
            SamplePhaseTrial(
                attack.name,
                trial_index,
                cover_seed,
                timeline_offset,
                False,
                *_oracle_crop_labels(attack),
                coarse.selected_offset_frames,
                coarse.accepted,
                len(residual.searched_scores),
                residual.selected_phase_samples,
                residual.accepted,
                residual.selected_mean_pilot_evidence,
                residual.best_minus_runner_evidence,
                embedding.signal_to_noise_db,
                measurement,
                _control_token_match(unwatermarked, token),
                _control_token_match(wrong_secret, token),
                None,
            )
        )
    return tuple(records)


def _summary(attack: AttackDefinition, trials: tuple[SamplePhaseTrial, ...]) -> dict[str, object]:
    """Aggregate coarse and residual decisions, post-hoc alignment labels, RS recovery, and controls per crop."""

    measurements = tuple(trial.measurement for trial in trials if trial.measurement is not None)
    residual_accepted = tuple(
        trial for trial in trials if trial.residual_scan_accepted and trial.residual_selected_phase_samples is not None
    )
    correct_coarse = sum(trial.coarse_offset_frames == trial.oracle_crop_offset_frames for trial in trials)
    correct_phase = sum(
        trial.residual_selected_phase_samples == trial.oracle_analysis_phase_samples
        for trial in residual_accepted
    )
    return {
        "attack_name": attack.name,
        "trial_count": len(trials),
        "execution_failures": sum(trial.error is not None for trial in trials),
        "coarse_scan_acceptances": sum(trial.coarse_scan_accepted for trial in trials),
        "posthoc_correct_coarse_offsets": correct_coarse,
        "residual_scan_acceptances": len(residual_accepted),
        "posthoc_exact_residual_phases": correct_phase,
        "median_selected_residual_phase_samples": median(
            trial.residual_selected_phase_samples
            for trial in residual_accepted
            if trial.residual_selected_phase_samples is not None
        ) if residual_accepted else None,
        "exact_recoveries": sum(bool(measurement["token_matches_input"]) for measurement in measurements),
        "median_rs_cost": median(int(measurement["rs_error_cost"]) for measurement in measurements) if measurements else None,
        "maximum_rs_cost": max(int(measurement["rs_error_cost"]) for measurement in measurements) if measurements else None,
        "median_carrier_erasures": median(int(measurement["carrier_erasures"]) for measurement in measurements) if measurements else None,
        "unwatermarked_control_false_accepts": sum(bool(trial.unwatermarked_control_handle_match) for trial in trials),
        "wrong_secret_control_false_accepts": sum(bool(trial.wrong_secret_control_handle_match) for trial in trials),
    }


def run() -> dict[str, object]:
    """Run the bounded sample-phase crop study over the direct-comparison fixture and archive every decision."""

    attacks = _crop_attacks()
    trials = tuple(record for trial_index in range(10) for record in evaluate_variant(trial_index, attacks))
    allocation = _selected_allocation()
    return {
        "fixture": "iteration 012's direct-comparison ten-cover crop fixture, reused before fresh held-out validation",
        "mapping_mode": "blind_non_oracle_coarse_frame_plus_sample_phase_scan",
        "decoder_received_oracle_map": False,
        "posthoc_labels": "Crop displacement and residual phase labels are recorded only after blind reconstruction.",
        "allocation": asdict(allocation),
        "protected_codeword_bytes": allocation.payload_bytes + allocation.parity_symbols,
        "carrier_bit_count": 184,
        "physical_carrier_count": 736,
        "profile": asdict(_profile()),
        "payload_thresholds": asdict(_threshold_policy()),
        "coarse_offset_policy": asdict(_scan_policy()),
        "residual_phase_policy": asdict(_phase_policy()),
        "validation_cover_seeds": list(range(6600, 6610)),
        "summaries": [
            _summary(attack, tuple(trial for trial in trials if trial.attack_name == attack.name))
            for attack in attacks
        ],
        "trials": [asdict(trial) for trial in trials],
    }


def main() -> None:
    """Print the complete reproducible coarse-to-fine sample-phase study as formatted JSON."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
