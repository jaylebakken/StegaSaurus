"""Run iteration 027: validate a fixed center-minus-24 sample phase rule on fresh crops.

Goal: test the simplest rule suggested by iteration 026: analyze every
duration-feasible coarse hypothesis at its blind model center minus 24 samples.
The calibration cover recovered both crop directions at RS cost 9 under this
rule; this script uses disjoint seeds `7500-7509` to determine whether that
observation generalizes.

Pipeline state: unchanged 4-byte/16-parity codeword, four replicas, carrier
selection, duration-feasible top-three coarse bank, and blind RS-success
ranking. The decoder does not receive a carrier map, source waveform, crop
label, crop displacement, expected handle, or any post-hoc diagnostic.
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
class NegativeBiasTrial:
    """Record one fresh crop reconstruction, byte RS result, and independent blind control acceptance."""

    attack_name: str
    trial_index: int
    cover_seed: int
    measurement: dict[str, object] | None
    hypothesis_count: int
    unwatermarked_accepted: bool
    wrong_secret_accepted: bool
    error: str | None


class NegativePhaseBiasDecoder(CoarseHypothesisBankDecoder):
    """Reframe each duration-feasible hypothesis at its deterministic center minus 24 samples before extraction."""

    def _banked_offsets(self, audio: PcmAudio, coarse) -> tuple[tuple[int, float, int], ...]:
        """Apply the fixed pre-registered negative phase bias after blind coarse filtering and ranking."""

        return tuple((offset, evidence, center - 24) for offset, evidence, center in super()._banked_offsets(audio, coarse))


def evaluate_variant(trial_index: int, attacks: Iterable[AttackDefinition]) -> tuple[NegativeBiasTrial, ...]:
    """Evaluate the fixed negative phase policy and controls on one fresh synthetic source cover."""

    allocation = _allocation()
    handle = allocation.handle()
    cover_seed = 7500 + trial_index
    source = _cover_variant(30, cover_seed, _trial_offset_seconds(1400 + trial_index))
    configuration = SpectralPilotConfig(minimum_frequency_hz=500.0, maximum_frequency_hz=3800.0, relative_difference=0.95)
    watermark = AudioWatermarkConfig(attribution_token_bytes=4, parity_symbols=16)
    pilot = SpectralAudioPilot(b"audio-pilot-test-key", configuration, watermark)
    encoder = ContrastivePilotCalibratedExperiment(pilot, 0.01, _profile())
    decoder = NegativePhaseBiasDecoder(encoder)
    embedding = encoder.embed(source, handle)
    wrong_pilot = SpectralAudioPilot(b"wrong-audio-pilot-test-key", configuration, watermark)
    wrong_encoder = ContrastivePilotCalibratedExperiment(wrong_pilot, 0.01, _profile())
    wrong_decoder = NegativePhaseBiasDecoder(wrong_encoder)
    wrong_plan = wrong_pilot.schema.plan_attribution(handle)
    records: list[NegativeBiasTrial] = []
    for attack in attacks:
        try:
            attacked = attack.transform(embedding.audio, 7900 + trial_index)
            decision = decoder.reconstruct(attacked, embedding.carrier_plan)
            unwatermarked = decoder.reconstruct(attack.transform(source, 7900 + trial_index), embedding.carrier_plan)
            wrong_secret = wrong_decoder.reconstruct(attacked, wrong_plan)
            records.append(NegativeBiasTrial(
                attack.name, trial_index, cover_seed,
                _measurement(encoder, embedding, decision.selected.reconstruction, handle) if decision.selected else None,
                len(decision.hypotheses), unwatermarked.selected is not None, wrong_secret.selected is not None, None,
            ))
        except Exception as error:
            records.append(NegativeBiasTrial(attack.name, trial_index, cover_seed, None, 0, False, False, f"{type(error).__name__}: {error}"))
    return tuple(records)


def _summary(attack: AttackDefinition, trials: tuple[NegativeBiasTrial, ...]) -> dict[str, object]:
    """Aggregate exact recovery, RS budget compliance, controls, and execution failures for one named crop."""

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
    """Run ten fresh crop validations and return the complete reproducible fixed-negative-bias archive."""

    attacks = _crop_attacks()
    trials = tuple(record for index in range(10) for record in evaluate_variant(index, attacks))
    return {
        "goal": "validate a fixed center-minus-24 phase rule under non-oracle coarse-map reconstruction and a 16-symbol RS budget",
        "decoder_received_oracle_map": False,
        "allocation": asdict(_allocation()),
        "phase_policy": "duration-feasible model center minus 24 samples",
        "validation_cover_seeds": list(range(7500, 7510)),
        "summaries": [_summary(attack, tuple(trial for trial in trials if trial.attack_name == attack.name)) for attack in attacks],
        "trials": [asdict(trial) for trial in trials],
    }


def main() -> None:
    """Print the complete fixed-negative-bias validation archive for redirection to ``RESULTS.json``."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
