"""Run iteration 021: test a bounded coarse-hypothesis bank without an oracle map.

Goal: determine whether the remaining iteration 020 crop failures are caused
by early commitment to one coarse timing offset rather than by Reed--Solomon
damage after a feasible alignment. The experiment freezes the 4-byte handle,
16-parity, 20-byte codeword, four replicas, carrier band, payload thresholds,
and deterministic one-edge crop phase model. It replaces only single-winner
coarse selection with the three strongest duration-feasible pilot-scored offsets.

Toy flow:
    received audio -> top-three duration-feasible keyed pilot offsets -> model-center phase
        -> blind local map reconstruction -> RS-success ranking -> accept/erase

No hypothesis receives the encoder carrier map, source waveform, crop label,
or expected handle. Exact-handle comparison and byte RS cost remain post-hoc
measurement fields. A returned RS payload is not itself an authenticated
registry lookup; controls record this limitation explicitly.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
import json
from statistics import median

from ....pilot import PcmAudio, SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioWatermarkConfig, CarrierPlan
from ...transport_optimization.iteration_006_duration_stability_bounds.run import (
    _cover_variant,
    _trial_offset_seconds,
)
from ..iteration_002_local_selection_pilot.run import LocalPilotReconstruction
from ..iteration_005_contrastive_pilot_calibration.run import ContrastivePilotCalibratedExperiment
from ..iteration_011_blind_attack_validation.run import AttackDefinition
from ..iteration_013_sample_phase_crop_realignment.run import SamplePhaseLocalPilotDecoder, _measured_extraction
from ..iteration_015_center_phase_held_out_validation.run import DeterministicCenterPhaseDecoder
from ..iteration_019_registry_handle_parity_tradeoff.run import _crop_attacks, _profile
from ..iteration_020_sixteen_parity_registry_handle.run import _handle_allocations
from ...transport_optimization.iteration_004_four_frame_soft_combine.run import _extraction_record


@dataclass(frozen=True, slots=True)
class CoarseHypothesis:
    """Keep one blind timing candidate and its complete local-pilot reconstruction evidence."""

    offset_frames: int
    pilot_evidence: float
    center_phase_samples: int
    reconstruction: LocalPilotReconstruction


@dataclass(frozen=True, slots=True)
class BankDecision:
    """Report all reconstructed hypotheses and one uniquely preferred RS-successful candidate."""

    hypotheses: tuple[CoarseHypothesis, ...]
    selected: CoarseHypothesis | None
    coarse_scan_accepted: bool


@dataclass(frozen=True, slots=True)
class BankTrial:
    """Record paired baseline and bank measurements plus negative-control acceptance diagnostics."""

    attack_name: str
    trial_index: int
    cover_seed: int
    baseline_measurement: dict[str, object]
    bank_measurement: dict[str, object] | None
    bank_hypothesis_count: int
    bank_rs_success_count: int
    bank_posthoc_correct_candidate_count: int
    bank_selected_offset_frames: int | None
    bank_selected_center_phase_samples: int | None
    unwatermarked_bank_accepted: bool
    wrong_secret_bank_accepted: bool
    error: str | None


class CoarseHypothesisBankDecoder:
    """Reconstruct the three strongest feasible coarse timing hypotheses before deterministic phase recovery."""

    def __init__(self, encoder: ContrastivePilotCalibratedExperiment, bank_size: int = 3) -> None:
        """Initialize the inherited non-oracle coarse scorer and validate the bounded bank size."""

        if bank_size < 1:
            raise ValueError("bank_size must be positive")
        self._phase_helper = SamplePhaseLocalPilotDecoder(encoder)
        self._coarse_decoder = self._phase_helper._coarse_decoder
        self._pilot = encoder._pilot
        self._bank_size = bank_size

    def reconstruct(self, audio: PcmAudio, carrier_plan: CarrierPlan) -> BankDecision:
        """Build and rank a bounded blind offset bank, returning a unique RS-successful hypothesis or erasure."""

        frequencies, spectrum = self._pilot._stft(audio)
        lower_bin, upper_bin = self._pilot._frequency_bin_range(frequencies)
        nominal_frames = self._coarse_decoder._nominal_frame_count(audio.sample_rate)
        coarse = self._coarse_decoder._select_offset(spectrum, carrier_plan, lower_bin, upper_bin, nominal_frames)
        hypotheses: list[CoarseHypothesis] = []
        for offset, evidence, center_phase in self._banked_offsets(audio, coarse):
            reframed = self._phase_helper._reframe_audio(audio, center_phase)
            frequencies, reframed_spectrum = self._pilot._stft(reframed)
            lower_bin, upper_bin = self._pilot._frequency_bin_range(frequencies)
            reconstruction = self._coarse_decoder._reconstruct_at_offset(
                reframed_spectrum,
                carrier_plan,
                lower_bin,
                upper_bin,
                nominal_frames,
                offset,
            )
            hypotheses.append(CoarseHypothesis(offset, evidence, center_phase, reconstruction))
        selected = self._select_successful(tuple(hypotheses))
        return BankDecision(tuple(hypotheses), selected, coarse.accepted)

    def _banked_offsets(self, audio: PcmAudio, coarse) -> tuple[tuple[int, float, int], ...]:
        """Retain top duration-feasible offsets meeting existing pilot gates, without a global gap gate."""

        policy = self._coarse_decoder._policy
        eligible = tuple(
            (score, center_phase)
            for score in coarse.searched_scores
            if score.mean_pilot_evidence is not None
            and score.probe_score_count >= policy.minimum_probe_scores
            and score.mean_pilot_evidence >= policy.minimum_mean_pilot_evidence
            and (center_phase := self._phase_helper._edge_crop_phase_center(audio, score.offset_frames)) is not None
        )
        ranked = sorted(
            eligible,
            key=lambda item: (float(item[0].mean_pilot_evidence), -abs(item[0].offset_frames), -item[0].offset_frames),
            reverse=True,
        )[: self._bank_size]
        return tuple((score.offset_frames, float(score.mean_pilot_evidence), int(center_phase)) for score, center_phase in ranked)

    @staticmethod
    def _select_successful(hypotheses: tuple[CoarseHypothesis, ...]) -> CoarseHypothesis | None:
        """Select a unique lowest-damage RS success without consulting the expected opaque handle."""

        successful = tuple(
            hypothesis
            for hypothesis in hypotheses
            if hypothesis.reconstruction.extraction.recovery.token is not None
        )
        if not successful:
            return None
        def rank(hypothesis: CoarseHypothesis) -> tuple[int, int, int, float, int, int]:
            """Order successful candidates by decoder correction burden, framing damage, then pilot support."""

            recovery = hypothesis.reconstruction.extraction.recovery.channel_recovery
            return (
                len(recovery.corrected_positions),
                len(recovery.erasure_positions),
                recovery.synchronization_mismatches,
                -hypothesis.pilot_evidence,
                abs(hypothesis.offset_frames),
                hypothesis.offset_frames,
            )
        ranked = sorted(successful, key=rank)
        return ranked[0] if len(ranked) == 1 or rank(ranked[0]) != rank(ranked[1]) else None


def _allocation():
    """Return iteration 020's fixed four-byte registry handle and sixteen-parity allocation."""

    return next(allocation for allocation in _handle_allocations() if allocation.parity_symbols == 16)


def _measurement(encoder, embedding, reconstruction, handle: bytes) -> dict[str, object]:
    """Attach post-hoc handle equality and byte RS cost to one blind reconstruction only after selection."""

    return _extraction_record(encoder, embedding, _measured_extraction(reconstruction, handle))


def evaluate_variant(trial_index: int, attacks: Iterable[AttackDefinition]) -> tuple[BankTrial, ...]:
    """Pair single-winner and banked non-oracle decoders on one fresh cover and named crop attacks."""

    allocation = _allocation()
    handle = allocation.handle()
    cover_seed = 7200 + trial_index
    source = _cover_variant(30, cover_seed, _trial_offset_seconds(1100 + trial_index))
    configuration = SpectralPilotConfig(minimum_frequency_hz=500.0, maximum_frequency_hz=3800.0, relative_difference=0.95)
    watermark = AudioWatermarkConfig(attribution_token_bytes=4, parity_symbols=16)
    pilot = SpectralAudioPilot(b"audio-pilot-test-key", configuration, watermark)
    encoder = ContrastivePilotCalibratedExperiment(pilot, 0.01, _profile())
    baseline_decoder = DeterministicCenterPhaseDecoder(encoder)
    bank_decoder = CoarseHypothesisBankDecoder(encoder)
    embedding = encoder.embed(source, handle)
    wrong_pilot = SpectralAudioPilot(b"wrong-audio-pilot-test-key", configuration, watermark)
    wrong_encoder = ContrastivePilotCalibratedExperiment(wrong_pilot, 0.01, _profile())
    wrong_decoder = CoarseHypothesisBankDecoder(wrong_encoder)
    wrong_plan = wrong_pilot.schema.plan_attribution(handle)
    records: list[BankTrial] = []
    for attack in attacks:
        try:
            attacked = attack.transform(embedding.audio, 7600 + trial_index)
            baseline, _, _, _ = baseline_decoder.reconstruct(attacked, embedding.carrier_plan)
            decision = bank_decoder.reconstruct(attacked, embedding.carrier_plan)
            selected = decision.selected
            bank_measurement = _measurement(encoder, embedding, selected.reconstruction, handle) if selected else None
            unwatermarked = bank_decoder.reconstruct(attack.transform(source, 7600 + trial_index), embedding.carrier_plan)
            wrong_secret = wrong_decoder.reconstruct(attacked, wrong_plan)
            records.append(BankTrial(
                attack.name, trial_index, cover_seed, _measurement(encoder, embedding, baseline, handle), bank_measurement,
                len(decision.hypotheses), sum(h.reconstruction.extraction.recovery.token is not None for h in decision.hypotheses),
                sum(h.reconstruction.extraction.recovery.token == handle for h in decision.hypotheses),
                selected.offset_frames if selected else None, selected.center_phase_samples if selected else None,
                unwatermarked.selected is not None, wrong_secret.selected is not None, None,
            ))
        except Exception as error:
            records.append(BankTrial(attack.name, trial_index, cover_seed, {}, None, 0, 0, 0, None, None, False, False, f"{type(error).__name__}: {error}"))
    return tuple(records)


def _summary(attack: AttackDefinition, trials: tuple[BankTrial, ...]) -> dict[str, object]:
    """Aggregate paired recovery, selected byte RS cost, bank coverage, and control acceptance by crop."""

    baseline = tuple(trial.baseline_measurement for trial in trials if trial.baseline_measurement)
    selected = tuple(trial.bank_measurement for trial in trials if trial.bank_measurement is not None)
    return {
        "attack_name": attack.name,
        "trial_count": len(trials),
        "baseline_exact_recoveries": sum(bool(row["token_matches_input"]) for row in baseline),
        "bank_exact_recoveries": sum(bool(row["token_matches_input"]) for row in selected),
        "bank_selected_rs_costs_within_16": sum(int(row["rs_error_cost"]) <= 16 for row in selected),
        "median_bank_selected_rs_cost": median(int(row["rs_error_cost"]) for row in selected) if selected else None,
        "bank_candidates_with_correct_payload": sum(trial.bank_posthoc_correct_candidate_count > 0 for trial in trials),
        "bank_acceptances": len(selected),
        "unwatermarked_bank_acceptances": sum(trial.unwatermarked_bank_accepted for trial in trials),
        "wrong_secret_bank_acceptances": sum(trial.wrong_secret_bank_accepted for trial in trials),
        "execution_failures": sum(trial.error is not None for trial in trials),
    }


def run() -> dict[str, object]:
    """Run ten fresh paired crop trials and return the full reproducible non-oracle hypothesis-bank record."""

    attacks = _crop_attacks()
    trials = tuple(record for index in range(10) for record in evaluate_variant(index, attacks))
    return {
        "goal": "reduce all-erasure coarse synchronization failures while keeping selected correct payloads within the 16-symbol RS budget",
        "decoder_received_oracle_map": False,
        "allocation": asdict(_allocation()),
        "coarse_bank_size": 3,
        "phase_policy": "one deterministic edge-crop center per blind coarse hypothesis",
        "validation_cover_seeds": list(range(7200, 7210)),
        "summaries": [_summary(attack, tuple(trial for trial in trials if trial.attack_name == attack.name)) for attack in attacks],
        "trials": [asdict(trial) for trial in trials],
    }


def main() -> None:
    """Print the complete machine-readable iteration record for archival redirection to ``RESULTS.json``."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
