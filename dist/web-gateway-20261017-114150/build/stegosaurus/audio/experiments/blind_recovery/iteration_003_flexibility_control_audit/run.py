"""Run iteration 003: audit flexible duration-bank recovery with controls.

Goal: move from "can a small duration bank recover the named crops?" to "how
much can the bank expand before control behavior or ambiguity becomes a concern?"
The experiment treats recovery as an application policy: run synchronized
decoder attempts for declared pipeline hypotheses, then select only a unique
lowest-burden Reed--Solomon success.

Toy flow:
    received audio -> narrow/broad duration bank -> per-duration edge decoder
        -> unique RS-success vote -> watermarked/control outcome

The decoder still receives a claimed transport plan. This is a controlled
claimed-handle recovery experiment, not unknown-handle discovery.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
import json
from statistics import median

from ....pilot import PcmAudio, SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioWatermarkConfig, CarrierPlan
from ...non_oracle_reconstruction.iteration_005_contrastive_pilot_calibration.run import (
    ContrastivePilotCalibratedExperiment,
)
from ...non_oracle_reconstruction.iteration_011_blind_attack_validation.run import (
    AttackDefinition,
    _attack_definitions,
)
from ...non_oracle_reconstruction.iteration_019_registry_handle_parity_tradeoff.run import _profile
from ...non_oracle_reconstruction.iteration_021_coarse_hypothesis_bank.run import _allocation, _measurement
from ...transport_optimization.iteration_006_duration_stability_bounds.run import (
    _cover_variant,
    _trial_offset_seconds,
)
from ..iteration_001_geometry_dependency_audit.run import GeometryAssumptionEdgeModeDecoder
from ..iteration_002_duration_bank_voting.run import DurationBank, DurationCandidate


@dataclass(frozen=True, slots=True)
class BankVote:
    """Represent the selected candidate from one duration bank or an abstention."""

    selected: DurationCandidate | None
    measurement: dict[str, object] | None
    candidates: tuple[DurationCandidate, ...]
    ambiguous_successes: int


@dataclass(frozen=True, slots=True)
class FlexControlTrial:
    """Record one bank policy against watermarked audio and two independent controls."""

    attack_name: str
    bank_name: str
    trial_index: int
    cover_seed: int
    watermarked_vote: BankVote
    unwatermarked_vote: BankVote
    wrong_secret_vote: BankVote
    error: str | None


def _duration_banks() -> tuple[DurationBank, ...]:
    """Return a narrow successful bank and a broader single-edge duration bank."""

    return (
        DurationBank("clean_or_250ms_edge_loss", (0.0, 0.25), "clean audio or one 250 ms edge loss"),
        DurationBank(
            "single_edge_loss_to_500ms",
            (0.0, 0.125, 0.25, 0.375, 0.5),
            "clean audio or one declared edge loss up to 500 ms",
        ),
    )


def _attacks() -> tuple[AttackDefinition, ...]:
    """Return clean PCM plus the named leading-edge crop stress transform."""

    selected_names = {"clean_pcm", "leading_crop_025s"}
    return tuple(attack for attack in _attack_definitions() if attack.name in selected_names)


def _run_bank(
    audio: PcmAudio,
    bank: DurationBank,
    encoder: ContrastivePilotCalibratedExperiment,
    carrier_plan: CarrierPlan,
    measurement_context: tuple[object, bytes] | None = None,
) -> BankVote:
    """Run every duration hypothesis in a bank and select a unique decoder-visible success."""

    candidates: list[tuple[DurationCandidate, object | None]] = []
    for loss_seconds in bank.loss_seconds:
        assumed_duration = audio.duration_seconds + loss_seconds
        decoder = GeometryAssumptionEdgeModeDecoder(encoder, assumed_duration)
        decision = decoder.reconstruct(audio, carrier_plan)
        selected = decision.selected
        candidate = DurationCandidate(
            assumed_duration,
            loss_seconds,
            decoder.edge_offsets(audio),
            selected.offset_frames if selected else None,
            sum(h.reconstruction.extraction.recovery.token is not None for h in decision.hypotheses),
            None,
        )
        candidates.append((candidate, selected))
    selected_pair, ambiguous_count = _select_unique(tuple(candidates))
    if selected_pair is None:
        return BankVote(None, None, tuple(candidate for candidate, _ in candidates), ambiguous_count)
    candidate, hypothesis = selected_pair
    measurement = None
    if measurement_context is not None:
        embedding, handle = measurement_context
        measurement = _measurement(encoder, embedding, hypothesis.reconstruction, handle)
    return BankVote(candidate, measurement, tuple(candidate for candidate, _ in candidates), ambiguous_count)


def _select_unique(candidates: tuple[tuple[DurationCandidate, object | None], ...]) -> tuple[tuple[DurationCandidate, object] | None, int]:
    """Return a unique lowest-burden success and count equal-rank successes."""

    successful = tuple(candidate for candidate in candidates if candidate[1] is not None)
    if not successful:
        return None, 0

    def rank(candidate: tuple[DurationCandidate, object]) -> tuple[int, int, int, float]:
        """Rank successes by correction burden, synchronization damage, and smaller loss."""

        recovery = candidate[1].reconstruction.extraction.recovery.channel_recovery
        return (
            len(recovery.corrected_positions),
            len(recovery.erasure_positions),
            recovery.synchronization_mismatches,
            candidate[0].inferred_loss_seconds,
        )

    ranked = sorted(successful, key=rank)
    best_rank = rank(ranked[0])
    tied = tuple(candidate for candidate in ranked if rank(candidate) == best_rank)
    return (ranked[0] if len(tied) == 1 else None, len(tied))


def evaluate_variant(
    trial_index: int,
    attacks: Iterable[AttackDefinition],
    banks: Iterable[DurationBank],
) -> tuple[FlexControlTrial, ...]:
    """Evaluate one cover against watermarked audio, unwatermarked controls, and wrong-secret controls."""

    allocation = _allocation()
    handle = allocation.handle()
    cover_seed = 7900 + trial_index
    source = _cover_variant(30, cover_seed, _trial_offset_seconds(1800 + trial_index))
    configuration = SpectralPilotConfig(
        minimum_frequency_hz=500.0,
        maximum_frequency_hz=3800.0,
        relative_difference=0.95,
    )
    watermark = AudioWatermarkConfig(attribution_token_bytes=4, parity_symbols=16)
    pilot = SpectralAudioPilot(b"audio-pilot-test-key", configuration, watermark)
    encoder = ContrastivePilotCalibratedExperiment(pilot, 0.01, _profile())
    embedding = encoder.embed(source, handle)
    wrong_pilot = SpectralAudioPilot(b"wrong-audio-pilot-test-key", configuration, watermark)
    wrong_encoder = ContrastivePilotCalibratedExperiment(wrong_pilot, 0.01, _profile())
    wrong_plan = wrong_pilot.schema.plan_attribution(handle)
    records: list[FlexControlTrial] = []
    for attack in attacks:
        attacked_watermarked = attack.transform(embedding.audio, 8400 + trial_index)
        attacked_source = attack.transform(source, 8400 + trial_index)
        for bank in banks:
            try:
                records.append(
                    FlexControlTrial(
                        attack.name,
                        bank.name,
                        trial_index,
                        cover_seed,
                        _run_bank(attacked_watermarked, bank, encoder, embedding.carrier_plan, (embedding, handle)),
                        _run_bank(attacked_source, bank, encoder, embedding.carrier_plan),
                        _run_bank(attacked_watermarked, bank, wrong_encoder, wrong_plan),
                        None,
                    )
                )
            except Exception as error:
                empty = BankVote(None, None, (), 0)
                records.append(
                    FlexControlTrial(
                        attack.name,
                        bank.name,
                        trial_index,
                        cover_seed,
                        empty,
                        empty,
                        empty,
                        f"{type(error).__name__}: {error}",
                    )
                )
    return tuple(records)


def _summary(attack: AttackDefinition, bank: DurationBank, trials: tuple[FlexControlTrial, ...]) -> dict[str, object]:
    """Aggregate recovery, controls, ambiguity, and correction burden for one bank."""

    measurements = tuple(trial.watermarked_vote.measurement for trial in trials if trial.watermarked_vote.measurement is not None)
    rs_costs = tuple(int(measurement["rs_error_cost"]) for measurement in measurements)
    return {
        "attack_name": attack.name,
        "bank_name": bank.name,
        "bank_description": bank.description,
        "candidate_count": len(bank.loss_seconds),
        "trial_count": len(trials),
        "execution_failures": sum(trial.error is not None for trial in trials),
        "watermarked_acceptances": sum(trial.watermarked_vote.selected is not None for trial in trials),
        "exact_recoveries": sum(bool(measurement["token_matches_input"]) for measurement in measurements),
        "unwatermarked_acceptances": sum(trial.unwatermarked_vote.selected is not None for trial in trials),
        "wrong_secret_acceptances": sum(trial.wrong_secret_vote.selected is not None for trial in trials),
        "ambiguous_watermarked_votes": sum(trial.watermarked_vote.ambiguous_successes > 1 for trial in trials),
        "median_rs_cost": median(rs_costs) if rs_costs else None,
        "maximum_rs_cost": max(rs_costs) if rs_costs else None,
    }


def run(trial_count: int = 1) -> dict[str, object]:
    """Run the flexibility-control audit and return machine-readable records."""

    attacks = _attacks()
    banks = _duration_banks()
    trials = tuple(
        record
        for index in range(trial_count)
        for record in evaluate_variant(index, attacks, banks)
    )
    return {
        "goal": "compare flexible duration-bank recovery against unwatermarked and wrong-secret controls",
        "decoder_received_oracle_map": False,
        "decoder_received_claimed_transport_plan": True,
        "selection_policy": "unique lowest decoder-visible RS correction burden across duration hypotheses",
        "allocation": asdict(_allocation()),
        "profile": asdict(_profile()),
        "validation_cover_seeds": list(range(7900, 7900 + trial_count)),
        "banks": [asdict(bank) for bank in banks],
        "attacks": [attack.name for attack in attacks],
        "summaries": [
            _summary(
                attack,
                bank,
                tuple(
                    trial
                    for trial in trials
                    if trial.attack_name == attack.name and trial.bank_name == bank.name
                ),
            )
            for attack in attacks
            for bank in banks
        ],
        "trials": [asdict(trial) for trial in trials],
    }


def main() -> None:
    """Print the complete flexibility-control audit for archival redirection."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
