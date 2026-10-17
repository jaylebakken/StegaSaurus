"""Run iteration 032: validate a blind leading/trailing edge-mode coarse bank.

Goal: prevent a pilot-scored coarse offset near the leading-crop duration from
excluding the equally duration-consistent trailing-crop offset. Given received
length loss, construct only the bounded one-edge hypotheses:

    trailing crop -> coarse offset 0, residual phase 0
    leading crop  -> floor/ceil(missing_samples / hop), residual phase model

The decoder reconstructs each feasible mode with the unchanged local candidate
selector and ranks RS-successful outcomes without a retained map or expected
handle. Pilot evidence remains a tie-break diagnostic, not an exclusion gate.
This is a fixed named-crop experiment, not a general edit synchronizer.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
import json
import math
from statistics import median

from ....pilot import PcmAudio, SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioWatermarkConfig, CarrierPlan
from ...transport_optimization.iteration_006_duration_stability_bounds.run import _cover_variant, _trial_offset_seconds
from ..iteration_005_contrastive_pilot_calibration.run import ContrastivePilotCalibratedExperiment
from ..iteration_011_blind_attack_validation.run import AttackDefinition
from ..iteration_019_registry_handle_parity_tradeoff.run import _crop_attacks, _profile
from ..iteration_021_coarse_hypothesis_bank.run import BankDecision, CoarseHypothesis, CoarseHypothesisBankDecoder, _allocation, _measurement


@dataclass(frozen=True, slots=True)
class EdgeModeTrial:
    """Record one fresh edge-mode bank result, selected transport measurement, and negative-control outcome."""

    attack_name: str
    trial_index: int
    cover_seed: int
    edge_offsets: tuple[int, ...]
    hypothesis_count: int
    rs_success_count: int
    selected_offset_frames: int | None
    measurement: dict[str, object] | None
    unwatermarked_accepted: bool
    wrong_secret_accepted: bool
    error: str | None


class EdgeModeCoarseBankDecoder(CoarseHypothesisBankDecoder):
    """Reconstruct the small leading/trailing timeline bank implied by received-length loss before local mapping."""

    def reconstruct(self, audio: PcmAudio, carrier_plan: CarrierPlan) -> BankDecision:
        """Build every bounded edge-mode hypothesis, then return the uniquely best blind RS-successful result or erasure."""

        frequencies, spectrum = self._pilot._stft(audio)
        lower_bin, upper_bin = self._pilot._frequency_bin_range(frequencies)
        nominal_frames = self._coarse_decoder._nominal_frame_count(audio.sample_rate)
        coarse = self._coarse_decoder._select_offset(spectrum, carrier_plan, lower_bin, upper_bin, nominal_frames)
        score_by_offset = {score.offset_frames: score.mean_pilot_evidence for score in coarse.searched_scores}
        hypotheses: list[CoarseHypothesis] = []
        for offset in self.edge_offsets(audio):
            phase = self._phase_helper._edge_crop_phase_center(audio, offset)
            if phase is None:
                continue
            reframed = self._phase_helper._reframe_audio(audio, phase)
            frequencies, reframed_spectrum = self._pilot._stft(reframed)
            lower_bin, upper_bin = self._pilot._frequency_bin_range(frequencies)
            reconstruction = self._coarse_decoder._reconstruct_at_offset(
                reframed_spectrum, carrier_plan, lower_bin, upper_bin, nominal_frames, offset
            )
            evidence = score_by_offset.get(offset)
            hypotheses.append(CoarseHypothesis(offset, float("-inf") if evidence is None else float(evidence), phase, reconstruction))
        values = tuple(hypotheses)
        return BankDecision(values, self._select_successful(values), coarse.accepted)

    def edge_offsets(self, audio: PcmAudio) -> tuple[int, ...]:
        """Derive bounded trailing and leading one-edge offsets from received sample loss without pilot labels."""

        nominal_samples = int(round(self._phase_helper._nominal_duration_seconds * audio.sample_rate))
        missing_samples = nominal_samples - len(audio.samples)
        if missing_samples < 0:
            return ()
        hop_size = self._pilot._config.hop_size
        leading_position = missing_samples / hop_size
        offsets = {0, math.floor(leading_position), math.ceil(leading_position)}
        maximum_offset = self._coarse_decoder._policy.maximum_offset_frames
        return tuple(sorted(offset for offset in offsets if -maximum_offset <= offset <= maximum_offset))


def evaluate_variant(trial_index: int, attacks: Iterable[AttackDefinition]) -> tuple[EdgeModeTrial, ...]:
    """Evaluate duration-derived edge modes and independent controls on one fresh 30-second source cover."""

    allocation = _allocation()
    handle = allocation.handle()
    cover_seed = 7700 + trial_index
    source = _cover_variant(30, cover_seed, _trial_offset_seconds(1600 + trial_index))
    configuration = SpectralPilotConfig(minimum_frequency_hz=500.0, maximum_frequency_hz=3800.0, relative_difference=0.95)
    watermark = AudioWatermarkConfig(attribution_token_bytes=4, parity_symbols=16)
    pilot = SpectralAudioPilot(b"audio-pilot-test-key", configuration, watermark)
    encoder = ContrastivePilotCalibratedExperiment(pilot, 0.01, _profile())
    decoder = EdgeModeCoarseBankDecoder(encoder)
    embedding = encoder.embed(source, handle)
    wrong_pilot = SpectralAudioPilot(b"wrong-audio-pilot-test-key", configuration, watermark)
    wrong_encoder = ContrastivePilotCalibratedExperiment(wrong_pilot, 0.01, _profile())
    wrong_decoder = EdgeModeCoarseBankDecoder(wrong_encoder)
    wrong_plan = wrong_pilot.schema.plan_attribution(handle)
    records: list[EdgeModeTrial] = []
    for attack in attacks:
        try:
            attacked = attack.transform(embedding.audio, 8100 + trial_index)
            offsets = decoder.edge_offsets(attacked)
            decision = decoder.reconstruct(attacked, embedding.carrier_plan)
            unwatermarked = decoder.reconstruct(attack.transform(source, 8100 + trial_index), embedding.carrier_plan)
            wrong_secret = wrong_decoder.reconstruct(attacked, wrong_plan)
            records.append(EdgeModeTrial(
                attack.name, trial_index, cover_seed, offsets, len(decision.hypotheses),
                sum(h.reconstruction.extraction.recovery.token is not None for h in decision.hypotheses),
                decision.selected.offset_frames if decision.selected else None,
                _measurement(encoder, embedding, decision.selected.reconstruction, handle) if decision.selected else None,
                unwatermarked.selected is not None, wrong_secret.selected is not None, None,
            ))
        except Exception as error:
            records.append(EdgeModeTrial(attack.name, trial_index, cover_seed, (), 0, 0, None, None, False, False, f"{type(error).__name__}: {error}"))
    return tuple(records)


def _summary(attack: AttackDefinition, trials: tuple[EdgeModeTrial, ...]) -> dict[str, object]:
    """Aggregate exact recovery, RS budget compliance, selected modes, controls, and failures for one crop direction."""

    measurements = tuple(trial.measurement for trial in trials if trial.measurement is not None)
    selected_offsets = tuple(trial.selected_offset_frames for trial in trials if trial.selected_offset_frames is not None)
    return {
        "attack_name": attack.name,
        "trial_count": len(trials),
        "exact_recoveries": sum(bool(row["token_matches_input"]) for row in measurements),
        "selected_rs_costs_within_16": sum(int(row["rs_error_cost"]) <= 16 for row in measurements),
        "median_selected_rs_cost": median(int(row["rs_error_cost"]) for row in measurements) if measurements else None,
        "selected_offsets": sorted(set(selected_offsets)),
        "unwatermarked_acceptances": sum(trial.unwatermarked_accepted for trial in trials),
        "wrong_secret_acceptances": sum(trial.wrong_secret_accepted for trial in trials),
        "execution_failures": sum(trial.error is not None for trial in trials),
    }


def run() -> dict[str, object]:
    """Run ten new leading/trailing crop validations and return the complete edge-mode-bank archive."""

    attacks = _crop_attacks()
    trials = tuple(record for index in range(10) for record in evaluate_variant(index, attacks))
    return {
        "goal": "retain duration-derived leading and trailing coarse modes before blind candidate-map reconstruction",
        "decoder_received_oracle_map": False,
        "allocation": asdict(_allocation()),
        "edge_mode_policy": "offset zero plus floor/ceil of missing_samples divided by STFT hop size",
        "validation_cover_seeds": list(range(7700, 7710)),
        "summaries": [_summary(attack, tuple(trial for trial in trials if trial.attack_name == attack.name)) for attack in attacks],
        "trials": [asdict(trial) for trial in trials],
    }


def main() -> None:
    """Print the complete edge-mode-bank archive for redirection to ``RESULTS.json``."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
