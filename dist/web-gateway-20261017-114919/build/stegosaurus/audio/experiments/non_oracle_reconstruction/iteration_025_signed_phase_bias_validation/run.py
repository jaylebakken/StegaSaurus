"""Run iteration 025: validate a fixed signed residual-phase bias on fresh crop covers.

Goal: test one fully specified phase rule selected from two prior single-case
audits: use +16 samples when the blind duration model center is zero, otherwise
use center +12 samples. It retains iteration 021's duration-feasible top-three
coarse beam, its 4-byte/16-parity codeword, and blind RS-success ranking.

Pipeline state: iteration 023 validated the zero-center +16 rule on a fresh
trailing crop set but left one leading abstention. Iteration 024 showed that
the failed leading case recovered at center +12 with RS cost 16. This separate
validation uses seeds `7400-7409`; no carrier map, source audio, crop label,
expected handle, or audit label reaches the decoder.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
import json
from statistics import median

from ....pilot import PcmAudio, SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioWatermarkConfig
from ...transport_optimization.iteration_006_duration_stability_bounds.run import _cover_variant, _trial_offset_seconds
from ..iteration_005_contrastive_pilot_calibration.run import ContrastivePilotCalibratedExperiment
from ..iteration_011_blind_attack_validation.run import AttackDefinition
from ..iteration_019_registry_handle_parity_tradeoff.run import _crop_attacks, _profile
from ..iteration_021_coarse_hypothesis_bank.run import CoarseHypothesisBankDecoder, _allocation, _measurement


@dataclass(frozen=True, slots=True)
class SignedBiasTrial:
    """Record one fresh crop decode, byte RS diagnostics, and blind negative-control acceptance."""

    attack_name: str
    trial_index: int
    cover_seed: int
    measurement: dict[str, object] | None
    hypothesis_count: int
    unwatermarked_accepted: bool
    wrong_secret_accepted: bool
    error: str | None


class SignedPhaseBiasDecoder(CoarseHypothesisBankDecoder):
    """Apply a fixed phase bias after blind duration-feasible offset selection and before payload extraction."""

    def _banked_offsets(self, audio: PcmAudio, coarse) -> tuple[tuple[int, float, int], ...]:
        """Convert every retained model center to the pre-registered zero/nonzero phase origin without payload feedback."""

        offsets = super()._banked_offsets(audio, coarse)
        return tuple((offset, evidence, 16 if center == 0 else center + 12) for offset, evidence, center in offsets)


def evaluate_variant(trial_index: int, attacks: Iterable[AttackDefinition]) -> tuple[SignedBiasTrial, ...]:
    """Evaluate the signed phase rule and independent controls on one fresh 30-second source cover."""

    allocation = _allocation()
    handle = allocation.handle()
    cover_seed = 7400 + trial_index
    source = _cover_variant(30, cover_seed, _trial_offset_seconds(1300 + trial_index))
    configuration = SpectralPilotConfig(minimum_frequency_hz=500.0, maximum_frequency_hz=3800.0, relative_difference=0.95)
    watermark = AudioWatermarkConfig(attribution_token_bytes=4, parity_symbols=16)
    pilot = SpectralAudioPilot(b"audio-pilot-test-key", configuration, watermark)
    encoder = ContrastivePilotCalibratedExperiment(pilot, 0.01, _profile())
    decoder = SignedPhaseBiasDecoder(encoder)
    embedding = encoder.embed(source, handle)
    wrong_pilot = SpectralAudioPilot(b"wrong-audio-pilot-test-key", configuration, watermark)
    wrong_encoder = ContrastivePilotCalibratedExperiment(wrong_pilot, 0.01, _profile())
    wrong_decoder = SignedPhaseBiasDecoder(wrong_encoder)
    wrong_plan = wrong_pilot.schema.plan_attribution(handle)
    records: list[SignedBiasTrial] = []
    for attack in attacks:
        try:
            attacked = attack.transform(embedding.audio, 7800 + trial_index)
            decision = decoder.reconstruct(attacked, embedding.carrier_plan)
            unwatermarked = decoder.reconstruct(attack.transform(source, 7800 + trial_index), embedding.carrier_plan)
            wrong_secret = wrong_decoder.reconstruct(attacked, wrong_plan)
            records.append(SignedBiasTrial(
                attack.name, trial_index, cover_seed,
                _measurement(encoder, embedding, decision.selected.reconstruction, handle) if decision.selected else None,
                len(decision.hypotheses), unwatermarked.selected is not None, wrong_secret.selected is not None, None,
            ))
        except Exception as error:
            records.append(SignedBiasTrial(attack.name, trial_index, cover_seed, None, 0, False, False, f"{type(error).__name__}: {error}"))
    return tuple(records)


def _summary(attack: AttackDefinition, trials: tuple[SignedBiasTrial, ...]) -> dict[str, object]:
    """Aggregate exact recovery, RS-cost budget compliance, controls, and execution failures for one named crop."""

    measurements = tuple(trial.measurement for trial in trials if trial.measurement is not None)
    return {
        "attack_name": attack.name,
        "trial_count": len(trials),
        "exact_recoveries": sum(bool(row["token_matches_input"]) for row in measurements),
        "selected_rs_costs_within_16": sum(int(row["rs_error_cost"]) <= 16 for row in measurements),
        "median_selected_rs_cost": median(int(row["rs_error_cost"]) for row in measurements) if measurements else None,
        "unwatermarked_acceptances": sum(trial.unwatermarked_accepted for trial in trials),
        "wrong_secret_acceptances": sum(trial.wrong_secret_accepted for trial in trials),
        "execution_failures": sum(trial.error is not None for trial in trials),
    }


def run() -> dict[str, object]:
    """Run ten new paired crop paths and return the full reproducible signed-phase validation record."""

    attacks = _crop_attacks()
    trials = tuple(record for index in range(10) for record in evaluate_variant(index, attacks))
    return {
        "goal": "validate the fixed signed phase rule while maintaining non-oracle map reconstruction and a 16-symbol RS budget",
        "decoder_received_oracle_map": False,
        "allocation": asdict(_allocation()),
        "phase_policy": "center + 16 samples when center is zero; otherwise center + 12 samples",
        "validation_cover_seeds": list(range(7400, 7410)),
        "summaries": [_summary(attack, tuple(trial for trial in trials if trial.attack_name == attack.name)) for attack in attacks],
        "trials": [asdict(trial) for trial in trials],
    }


def main() -> None:
    """Print the complete signed-phase validation archive for redirection to ``RESULTS.json``."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
