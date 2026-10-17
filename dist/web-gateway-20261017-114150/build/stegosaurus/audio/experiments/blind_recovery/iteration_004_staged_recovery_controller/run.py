"""Run iteration 004: prototype a staged blind-recovery controller.

Goal: convert synchronized duration-bank experiments into a production-shaped
policy. Broad banks can recover named edge crops, but they cost runtime and
increase false-accept surface. This controller evaluates declared geometry
hypotheses in stages and stops at the first unique, low-burden RS success.

Toy flow:
    received audio -> received-duration stage -> 250 ms edge-loss stage
        -> broad edge-loss fallback -> unique RS-burden vote -> outcome

The decoder still receives a claimed carrier plan for one handle. This is a
claimed-plan recovery controller prototype, not unknown-handle discovery.
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
from ..iteration_002_duration_bank_voting.run import DurationCandidate


@dataclass(frozen=True, slots=True)
class ControllerStage:
    """Describe one ordered group of declared geometry hypotheses."""
    name: str
    loss_seconds: tuple[float, ...]
    description: str


@dataclass(frozen=True, slots=True)
class StageVote:
    """Record the controller decision for one received audio object."""
    accepted: bool
    stage_name: str | None
    selected: DurationCandidate | None
    measurement: dict[str, object] | None
    attempts: tuple[DurationCandidate, ...]
    ambiguous_successes: int
    rejection_reason: str | None


@dataclass(frozen=True, slots=True)
class ControllerTrial:
    """Record one attack through the staged controller and its controls."""
    attack_name: str
    trial_index: int
    cover_seed: int
    watermarked_vote: StageVote
    unwatermarked_vote: StageVote
    wrong_secret_vote: StageVote
    error: str | None


def _controller_stages() -> tuple[ControllerStage, ...]:
    """Return ordered stages from cheapest geometry assumption to broad fallback."""
    return (
        ControllerStage("received_only", (0.0,), "assume received duration is source duration"),
        ControllerStage("single_250ms_edge_loss", (0.25,), "allow one declared 250 ms edge loss"),
        ControllerStage(
            "broad_single_edge_loss",
            (0.125, 0.375, 0.5),
            "fallback edge-loss hypotheses up to 500 ms",
        ),
    )


def _attacks() -> tuple[AttackDefinition, ...]:
    """Return clean PCM plus the leading-edge crop stress case."""
    selected_names = {"clean_pcm", "leading_crop_025s"}
    return tuple(attack for attack in _attack_definitions() if attack.name in selected_names)


def _rank(hypothesis: object, inferred_loss_seconds: float) -> tuple[int, int, int, float]:
    """Rank a successful reconstruction using only decoder-visible burden."""
    recovery = hypothesis.reconstruction.extraction.recovery.channel_recovery
    return (len(recovery.corrected_positions), len(recovery.erasure_positions), recovery.synchronization_mismatches, inferred_loss_seconds)


def _candidate(
    audio: PcmAudio,
    encoder: ContrastivePilotCalibratedExperiment,
    carrier_plan: CarrierPlan,
    loss_seconds: float,
) -> tuple[DurationCandidate, object | None]:
    """Run one duration hypothesis and return the serializable candidate plus selected hypothesis."""
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
    return candidate, selected


def _select_stage(
    candidates: tuple[tuple[DurationCandidate, object | None], ...],
) -> tuple[tuple[DurationCandidate, object] | None, int]:
    """Choose a unique lowest-burden success from one controller stage."""
    successful = tuple(candidate for candidate in candidates if candidate[1] is not None)
    if not successful:
        return None, 0
    ranked = sorted(successful, key=lambda item: _rank(item[1], item[0].inferred_loss_seconds))
    best_rank = _rank(ranked[0][1], ranked[0][0].inferred_loss_seconds)
    tied = tuple(item for item in ranked if _rank(item[1], item[0].inferred_loss_seconds) == best_rank)
    return (ranked[0] if len(tied) == 1 else None, len(tied))


def _run_controller(
    audio: PcmAudio,
    encoder: ContrastivePilotCalibratedExperiment,
    carrier_plan: CarrierPlan,
    stages: Iterable[ControllerStage],
    measurement_context: tuple[object, bytes] | None = None,
    maximum_rs_cost: int = 8,
) -> StageVote:
    """Run stages until a unique low-burden result accepts or all stages abstain."""

    attempts: list[DurationCandidate] = []
    ambiguous_successes = 0
    for stage in stages:
        stage_pairs = tuple(_candidate(audio, encoder, carrier_plan, loss_seconds) for loss_seconds in stage.loss_seconds)
        attempts.extend(candidate for candidate, _ in stage_pairs)
        selected_pair, stage_ambiguity = _select_stage(stage_pairs)
        ambiguous_successes += stage_ambiguity if stage_ambiguity > 1 else 0
        if selected_pair is None:
            continue
        candidate, hypothesis = selected_pair
        correction_cost = sum(_rank(hypothesis, candidate.inferred_loss_seconds)[:2])
        if correction_cost > maximum_rs_cost:
            return StageVote(False, stage.name, candidate, None, tuple(attempts), ambiguous_successes, "rs_cost_gate")
        measurement = None
        if measurement_context is not None:
            embedding, handle = measurement_context
            measurement = _measurement(encoder, embedding, hypothesis.reconstruction, handle)
        return StageVote(True, stage.name, candidate, measurement, tuple(attempts), ambiguous_successes, None)
    return StageVote(False, None, None, None, tuple(attempts), ambiguous_successes, "no_unique_success")


def evaluate_variant(trial_index: int, attacks: Iterable[AttackDefinition]) -> tuple[ControllerTrial, ...]:
    """Evaluate one cover through the staged controller and two controls."""

    allocation = _allocation()
    handle = allocation.handle()
    cover_seed = 7900 + trial_index
    source = _cover_variant(30, cover_seed, _trial_offset_seconds(1800 + trial_index))
    configuration = SpectralPilotConfig(minimum_frequency_hz=500.0, maximum_frequency_hz=3800.0, relative_difference=0.95)
    watermark = AudioWatermarkConfig(attribution_token_bytes=4, parity_symbols=16)
    pilot = SpectralAudioPilot(b"audio-pilot-test-key", configuration, watermark)
    encoder = ContrastivePilotCalibratedExperiment(pilot, 0.01, _profile())
    embedding = encoder.embed(source, handle)
    wrong_pilot = SpectralAudioPilot(b"wrong-audio-pilot-test-key", configuration, watermark)
    wrong_encoder = ContrastivePilotCalibratedExperiment(wrong_pilot, 0.01, _profile())
    wrong_plan = wrong_pilot.schema.plan_attribution(handle)
    stages = _controller_stages()
    records: list[ControllerTrial] = []
    for attack in attacks:
        try:
            attacked_watermarked = attack.transform(embedding.audio, 8500 + trial_index)
            attacked_source = attack.transform(source, 8500 + trial_index)
            watermarked = _run_controller(attacked_watermarked, encoder, embedding.carrier_plan, stages, (embedding, handle))
            unwatermarked = _run_controller(attacked_source, encoder, embedding.carrier_plan, stages)
            wrong_secret = _run_controller(attacked_watermarked, wrong_encoder, wrong_plan, stages)
            records.append(ControllerTrial(attack.name, trial_index, cover_seed, watermarked, unwatermarked, wrong_secret, None))
        except Exception as error:
            empty = StageVote(False, None, None, None, (), 0, "execution_failure")
            records.append(ControllerTrial(attack.name, trial_index, cover_seed, empty, empty, empty, f"{type(error).__name__}: {error}"))
    return tuple(records)


def _summary(attack: AttackDefinition, trials: tuple[ControllerTrial, ...]) -> dict[str, object]:
    """Aggregate staged-controller outcomes for one attack."""

    measurements = tuple(trial.watermarked_vote.measurement for trial in trials if trial.watermarked_vote.measurement is not None)
    rs_costs = tuple(int(measurement["rs_error_cost"]) for measurement in measurements)
    attempts = tuple(len(trial.watermarked_vote.attempts) for trial in trials)
    stages = tuple(trial.watermarked_vote.stage_name for trial in trials if trial.watermarked_vote.stage_name is not None)
    return {
        "attack_name": attack.name,
        "trial_count": len(trials),
        "execution_failures": sum(trial.error is not None for trial in trials),
        "watermarked_acceptances": sum(trial.watermarked_vote.accepted for trial in trials),
        "exact_recoveries": sum(bool(measurement["token_matches_input"]) for measurement in measurements),
        "unwatermarked_acceptances": sum(trial.unwatermarked_vote.accepted for trial in trials),
        "wrong_secret_acceptances": sum(trial.wrong_secret_vote.accepted for trial in trials),
        "ambiguous_watermarked_votes": sum(trial.watermarked_vote.ambiguous_successes > 0 for trial in trials),
        "selected_stages": sorted(set(stages)),
        "median_watermarked_attempts": median(attempts) if attempts else None,
        "median_rs_cost": median(rs_costs) if rs_costs else None,
        "maximum_rs_cost": max(rs_costs) if rs_costs else None,
    }


def run(trial_count: int = 1) -> dict[str, object]:
    """Run the staged-controller prototype and return machine-readable records."""

    attacks = _attacks()
    trials = tuple(record for index in range(trial_count) for record in evaluate_variant(index, attacks))
    return {
        "goal": "prototype staged blind-recovery policy with explicit controls and runtime accounting",
        "decoder_received_oracle_map": False,
        "decoder_received_claimed_transport_plan": True,
        "acceptance_policy": "first stage with unique success and correction burden <= 8",
        "allocation": asdict(_allocation()),
        "profile": asdict(_profile()),
        "validation_cover_seeds": list(range(7900, 7900 + trial_count)),
        "stages": [asdict(stage) for stage in _controller_stages()],
        "attacks": [attack.name for attack in attacks],
        "summaries": [
            _summary(attack, tuple(trial for trial in trials if trial.attack_name == attack.name))
            for attack in attacks
        ],
        "trials": [asdict(trial) for trial in trials],
    }


def main() -> None:
    """Print the staged-controller prototype audit."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
