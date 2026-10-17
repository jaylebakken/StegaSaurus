"""Run iteration 028: validate a non-oracle residual-phase fallback bank on fresh crops.

Goal: preserve iteration 021's normal duration-feasible center reconstruction
when it produces a blind RS-successful candidate, but try five bounded phase
offsets only when that primary path has no candidate. This follows failed
fixed-bias validations: phases can rescue individual abstentions, but one
global offset does not generalize.

Pipeline state: retain the 4-byte external handle, 16 RS parity symbols,
duration-feasible top-three keyed coarse bank, local carrier selection, and
blind RS-success ranking. The fallback receives no carrier map, expected
handle, crop label, source audio, or post-hoc error diagnostic. It ranks only
decoder-visible recovery burden and pilot evidence; equality to the embedded
handle is recorded solely after selection.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
import json
from statistics import median

from ....pilot import PcmAudio, SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioWatermarkConfig, CarrierPlan
from ...transport_optimization.iteration_006_duration_stability_bounds.run import _cover_variant, _trial_offset_seconds
from ..iteration_005_contrastive_pilot_calibration.run import ContrastivePilotCalibratedExperiment
from ..iteration_011_blind_attack_validation.run import AttackDefinition
from ..iteration_019_registry_handle_parity_tradeoff.run import _crop_attacks, _profile
from ..iteration_021_coarse_hypothesis_bank.run import (
    BankDecision,
    CoarseHypothesis,
    CoarseHypothesisBankDecoder,
    _allocation,
    _measurement,
)


FALLBACK_PHASE_DELTAS = (-24, -16, -12, 12, 16)


@dataclass(frozen=True, slots=True)
class FallbackTrial:
    """Record a fresh primary/fallback decode, byte RS result, and independent blind control acceptance."""

    attack_name: str
    trial_index: int
    cover_seed: int
    measurement: dict[str, object] | None
    primary_hypothesis_count: int
    fallback_used: bool
    fallback_hypothesis_count: int
    unwatermarked_accepted: bool
    wrong_secret_accepted: bool
    error: str | None


class AdaptivePhaseFallbackDecoder(CoarseHypothesisBankDecoder):
    """Expand a normal duration-feasible center bank into a phase list only when it has no blind RS success."""

    def reconstruct(self, audio: PcmAudio, carrier_plan: CarrierPlan) -> BankDecision:
        """Return the primary center result or select a bounded blind phase fallback without changing coarse offsets."""

        primary = super().reconstruct(audio, carrier_plan)
        self._last_primary_hypothesis_count = len(primary.hypotheses)
        if primary.selected is not None:
            self._last_fallback_hypothesis_count = 0
            return primary
        fallback = self._fallback_hypotheses(audio, carrier_plan, primary.hypotheses)
        self._last_fallback_hypothesis_count = len(fallback)
        all_hypotheses = primary.hypotheses + fallback
        return BankDecision(all_hypotheses, self._select_successful(all_hypotheses), primary.coarse_scan_accepted)

    @property
    def last_hypothesis_counts(self) -> tuple[int, int]:
        """Return the primary and fallback hypothesis counts recorded by the most recent reconstruction."""

        return (
            getattr(self, "_last_primary_hypothesis_count", 0),
            getattr(self, "_last_fallback_hypothesis_count", 0),
        )

    def _fallback_hypotheses(
        self,
        audio: PcmAudio,
        carrier_plan: CarrierPlan,
        primary: tuple[CoarseHypothesis, ...],
    ) -> tuple[CoarseHypothesis, ...]:
        """Reconstruct declared phase deltas around primary duration-feasible centers without rescreening offsets."""

        nominal_frames = self._coarse_decoder._nominal_frame_count(audio.sample_rate)
        fallback: list[CoarseHypothesis] = []
        for hypothesis in primary:
            for delta in FALLBACK_PHASE_DELTAS:
                phase = hypothesis.center_phase_samples + delta
                if not -self._pilot._config.hop_size < phase < self._pilot._config.hop_size:
                    continue
                reframed = self._phase_helper._reframe_audio(audio, phase)
                frequencies, spectrum = self._pilot._stft(reframed)
                lower_bin, upper_bin = self._pilot._frequency_bin_range(frequencies)
                reconstruction = self._coarse_decoder._reconstruct_at_offset(
                    spectrum, carrier_plan, lower_bin, upper_bin, nominal_frames, hypothesis.offset_frames
                )
                fallback.append(CoarseHypothesis(hypothesis.offset_frames, hypothesis.pilot_evidence, phase, reconstruction))
        return tuple(fallback)


def evaluate_variant(trial_index: int, attacks: Iterable[AttackDefinition]) -> tuple[FallbackTrial, ...]:
    """Evaluate the adaptive blind fallback and independent controls on one fresh synthetic source cover."""

    allocation = _allocation()
    handle = allocation.handle()
    cover_seed = 7600 + trial_index
    source = _cover_variant(30, cover_seed, _trial_offset_seconds(1500 + trial_index))
    configuration = SpectralPilotConfig(minimum_frequency_hz=500.0, maximum_frequency_hz=3800.0, relative_difference=0.95)
    watermark = AudioWatermarkConfig(attribution_token_bytes=4, parity_symbols=16)
    pilot = SpectralAudioPilot(b"audio-pilot-test-key", configuration, watermark)
    encoder = ContrastivePilotCalibratedExperiment(pilot, 0.01, _profile())
    decoder = AdaptivePhaseFallbackDecoder(encoder)
    embedding = encoder.embed(source, handle)
    wrong_pilot = SpectralAudioPilot(b"wrong-audio-pilot-test-key", configuration, watermark)
    wrong_encoder = ContrastivePilotCalibratedExperiment(wrong_pilot, 0.01, _profile())
    wrong_decoder = AdaptivePhaseFallbackDecoder(wrong_encoder)
    wrong_plan = wrong_pilot.schema.plan_attribution(handle)
    records: list[FallbackTrial] = []
    for attack in attacks:
        try:
            attacked = attack.transform(embedding.audio, 8000 + trial_index)
            decision = decoder.reconstruct(attacked, embedding.carrier_plan)
            primary_count, fallback_count = decoder.last_hypothesis_counts
            unwatermarked = decoder.reconstruct(attack.transform(source, 8000 + trial_index), embedding.carrier_plan)
            wrong_secret = wrong_decoder.reconstruct(attacked, wrong_plan)
            records.append(FallbackTrial(
                attack.name, trial_index, cover_seed,
                _measurement(encoder, embedding, decision.selected.reconstruction, handle) if decision.selected else None,
                primary_count, fallback_count > 0, fallback_count,
                unwatermarked.selected is not None, wrong_secret.selected is not None, None,
            ))
        except Exception as error:
            records.append(FallbackTrial(attack.name, trial_index, cover_seed, None, 0, False, 0, False, False, f"{type(error).__name__}: {error}"))
    return tuple(records)


def _summary(attack: AttackDefinition, trials: tuple[FallbackTrial, ...]) -> dict[str, object]:
    """Aggregate exact recovery, RS budget compliance, fallback use, controls, and failures by crop direction."""

    measurements = tuple(trial.measurement for trial in trials if trial.measurement is not None)
    return {
        "attack_name": attack.name,
        "trial_count": len(trials),
        "exact_recoveries": sum(bool(row["token_matches_input"]) for row in measurements),
        "selected_rs_costs_within_16": sum(int(row["rs_error_cost"]) <= 16 for row in measurements),
        "median_selected_rs_cost": median(int(row["rs_error_cost"]) for row in measurements) if measurements else None,
        "fallback_uses": sum(trial.fallback_used for trial in trials),
        "unwatermarked_acceptances": sum(trial.unwatermarked_accepted for trial in trials),
        "wrong_secret_acceptances": sum(trial.wrong_secret_accepted for trial in trials),
        "execution_failures": sum(trial.error is not None for trial in trials),
    }


def run() -> dict[str, object]:
    """Run ten fresh crop validations and return the complete reproducible adaptive-fallback archive."""

    attacks = _crop_attacks()
    trials = tuple(record for index in range(10) for record in evaluate_variant(index, attacks))
    return {
        "goal": "recover center-phase abstentions with a bounded non-oracle phase fallback while retaining the 16-symbol RS budget",
        "decoder_received_oracle_map": False,
        "allocation": asdict(_allocation()),
        "fallback_phase_deltas": list(FALLBACK_PHASE_DELTAS),
        "validation_cover_seeds": list(range(7600, 7610)),
        "summaries": [_summary(attack, tuple(trial for trial in trials if trial.attack_name == attack.name)) for attack in attacks],
        "trials": [asdict(trial) for trial in trials],
    }


def main() -> None:
    """Print the complete adaptive-fallback validation archive for redirection to ``RESULTS.json``."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
