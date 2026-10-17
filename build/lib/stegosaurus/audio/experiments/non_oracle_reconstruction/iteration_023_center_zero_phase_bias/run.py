"""Run iteration 023: validate a fixed center-zero analysis-phase bias on fresh crops.

Goal: test whether adding +16 samples only when the blind duration model
derives a zero residual phase can recover the iteration 021-style trailing
edge case without harming leading-crop reconstruction. Iteration 022 observed
that the audited center-zero failure crossed from RS cost 17 to 14 at +16;
this script treats that as calibration only and validates the rule on new
seeds `7300-7309`.

Pipeline state: use iteration 021's duration-feasible top-three coarse bank,
current 4-byte/16-parity codeword, unchanged carrier selection, and blind
RS-success ranking. The decoder receives no retained frame map, source cover,
crop direction, crop displacement, or expected registry handle. Exact handle
equality remains post-hoc evaluation, while controls measure any blind bank
acceptance separately.
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
from ..iteration_021_coarse_hypothesis_bank.run import CoarseHypothesisBankDecoder, _allocation, _measurement


@dataclass(frozen=True, slots=True)
class PhaseBiasTrial:
    """Record paired center and center-zero-biased blind bank outcomes on one fresh transformed cover."""

    attack_name: str
    trial_index: int
    cover_seed: int
    baseline_measurement: dict[str, object] | None
    biased_measurement: dict[str, object] | None
    biased_hypothesis_count: int
    unwatermarked_biased_accepted: bool
    wrong_secret_biased_accepted: bool
    error: str | None


class CenterZeroPhaseBiasDecoder(CoarseHypothesisBankDecoder):
    """Use the normal duration-feasible bank but replace a derived zero phase with a fixed +16-sample origin."""

    def _banked_offsets(self, audio: PcmAudio, coarse) -> tuple[tuple[int, float, int], ...]:
        """Apply the pre-registered phase bias after blind feasibility and pilot ranking, not from a payload label."""

        offsets = super()._banked_offsets(audio, coarse)
        return tuple((offset, evidence, 16 if center == 0 else center) for offset, evidence, center in offsets)


def evaluate_variant(trial_index: int, attacks: Iterable[AttackDefinition]) -> tuple[PhaseBiasTrial, ...]:
    """Pair the frozen iteration 021 center rule and the phase-biased rule on one new source cover and controls."""

    allocation = _allocation()
    handle = allocation.handle()
    cover_seed = 7300 + trial_index
    source = _cover_variant(30, cover_seed, _trial_offset_seconds(1200 + trial_index))
    configuration = SpectralPilotConfig(minimum_frequency_hz=500.0, maximum_frequency_hz=3800.0, relative_difference=0.95)
    watermark = AudioWatermarkConfig(attribution_token_bytes=4, parity_symbols=16)
    pilot = SpectralAudioPilot(b"audio-pilot-test-key", configuration, watermark)
    encoder = ContrastivePilotCalibratedExperiment(pilot, 0.01, _profile())
    baseline = CoarseHypothesisBankDecoder(encoder)
    biased = CenterZeroPhaseBiasDecoder(encoder)
    embedding = encoder.embed(source, handle)
    wrong_pilot = SpectralAudioPilot(b"wrong-audio-pilot-test-key", configuration, watermark)
    wrong_encoder = ContrastivePilotCalibratedExperiment(wrong_pilot, 0.01, _profile())
    wrong_biased = CenterZeroPhaseBiasDecoder(wrong_encoder)
    wrong_plan = wrong_pilot.schema.plan_attribution(handle)
    records: list[PhaseBiasTrial] = []
    for attack in attacks:
        try:
            attacked = attack.transform(embedding.audio, 7700 + trial_index)
            baseline_decision = baseline.reconstruct(attacked, embedding.carrier_plan)
            biased_decision = biased.reconstruct(attacked, embedding.carrier_plan)
            unwatermarked = biased.reconstruct(attack.transform(source, 7700 + trial_index), embedding.carrier_plan)
            wrong_secret = wrong_biased.reconstruct(attacked, wrong_plan)
            records.append(PhaseBiasTrial(
                attack.name, trial_index, cover_seed,
                _measurement(encoder, embedding, baseline_decision.selected.reconstruction, handle) if baseline_decision.selected else None,
                _measurement(encoder, embedding, biased_decision.selected.reconstruction, handle) if biased_decision.selected else None,
                len(biased_decision.hypotheses), unwatermarked.selected is not None, wrong_secret.selected is not None, None,
            ))
        except Exception as error:
            records.append(PhaseBiasTrial(attack.name, trial_index, cover_seed, None, None, 0, False, False, f"{type(error).__name__}: {error}"))
    return tuple(records)


def _summary(attack: AttackDefinition, trials: tuple[PhaseBiasTrial, ...]) -> dict[str, object]:
    """Aggregate paired exact recovery, byte RS cost, and blind control acceptance for one crop direction."""

    baseline = tuple(trial.baseline_measurement for trial in trials if trial.baseline_measurement is not None)
    biased = tuple(trial.biased_measurement for trial in trials if trial.biased_measurement is not None)
    return {
        "attack_name": attack.name,
        "trial_count": len(trials),
        "baseline_exact_recoveries": sum(bool(row["token_matches_input"]) for row in baseline),
        "biased_exact_recoveries": sum(bool(row["token_matches_input"]) for row in biased),
        "biased_selected_rs_costs_within_16": sum(int(row["rs_error_cost"]) <= 16 for row in biased),
        "median_biased_selected_rs_cost": median(int(row["rs_error_cost"]) for row in biased) if biased else None,
        "unwatermarked_biased_acceptances": sum(trial.unwatermarked_biased_accepted for trial in trials),
        "wrong_secret_biased_acceptances": sum(trial.wrong_secret_biased_accepted for trial in trials),
        "execution_failures": sum(trial.error is not None for trial in trials),
    }


def run() -> dict[str, object]:
    """Run ten disjoint paired crop trials and return the complete pre-registered phase-bias validation archive."""

    attacks = _crop_attacks()
    trials = tuple(record for index in range(10) for record in evaluate_variant(index, attacks))
    return {
        "goal": "validate a fixed +16-sample bias only for blind duration-model center phase zero",
        "decoder_received_oracle_map": False,
        "allocation": asdict(_allocation()),
        "phase_policy": "duration-feasible center, plus 16 samples when and only when center equals zero",
        "validation_cover_seeds": list(range(7300, 7310)),
        "summaries": [_summary(attack, tuple(trial for trial in trials if trial.attack_name == attack.name)) for attack in attacks],
        "trials": [asdict(trial) for trial in trials],
    }


def main() -> None:
    """Print the complete machine-readable phase-bias validation record for archival redirection to ``RESULTS.json``."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
