"""Run iteration 005: audit production-shaped accept/abstain decisions.

Goal: test whether the staged blind-recovery controller is a workable prototype
decision policy, not just a successful fixture. The policy accepts only a
unique low-burden RS success, keeps unwatermarked and wrong-secret controls
quiet, and otherwise returns a bounded abstention instead of expanding search
without evidence.

Toy flow:
    scenario -> staged controller -> watermarked/control votes
        -> accept, control-risk, or bounded-abstain decision

This remains claimed-plan attribution recovery. Unknown-handle discovery,
registry authentication, codecs, DSP, recorded audio, and adversarial false
positive rates are outside this iteration.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json

from ....pilot import SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioWatermarkConfig
from ....attribution_core.blind_policy import BlindRecoveryDecisionPolicy, BlindRecoveryStatus, BlindRecoveryVote
from ...non_oracle_reconstruction.iteration_005_contrastive_pilot_calibration.run import (
    ContrastivePilotCalibratedExperiment,
)
from ...non_oracle_reconstruction.iteration_011_blind_attack_validation.run import _attack_definitions
from ...non_oracle_reconstruction.iteration_019_registry_handle_parity_tradeoff.run import _profile
from ...non_oracle_reconstruction.iteration_021_coarse_hypothesis_bank.run import _allocation
from ...transport_optimization.iteration_006_duration_stability_bounds.run import (
    _cover_variant,
    _trial_offset_seconds,
)
from ..iteration_004_staged_recovery_controller.run import (
    StageVote,
    _controller_stages,
    _run_controller,
)


@dataclass(frozen=True, slots=True)
class DecisionScenario:
    """Describe one seed, offset recipe, and transform for prototype auditing."""
    name: str
    cover_seed: int
    offset_seed: int
    attack_name: str


@dataclass(frozen=True, slots=True)
class PrototypeDecision:
    """Record the production-facing decision and the evidence behind it."""
    scenario_name: str
    attack_name: str
    cover_seed: int
    decision: str
    reason: str
    selected_stage: str | None
    attempted_hypotheses: int
    exact_recovery: bool
    watermarked_accepted: bool
    unwatermarked_accepted: bool
    wrong_secret_accepted: bool
    rs_cost: int | None
    error: str | None


def _scenarios() -> tuple[DecisionScenario, ...]:
    """Return known-good cases plus the clean seed-failure probe from iteration 003."""

    return (
        DecisionScenario("known_good_clean", 7900, 1800, "clean_pcm"),
        DecisionScenario("known_good_leading_crop", 7900, 1800, "leading_crop_025s"),
        DecisionScenario("weak_clean_probe", 8000, 1900, "clean_pcm"),
    )


def _attack(name: str):
    """Return one named attack definition from the archived attack suite."""

    return next(attack for attack in _attack_definitions() if attack.name == name)


def _encoder() -> tuple[bytes, SpectralAudioPilot, ContrastivePilotCalibratedExperiment]:
    """Create the fixed pilot and encoder used by the blind-recovery track."""

    allocation = _allocation()
    configuration = SpectralPilotConfig(
        minimum_frequency_hz=500.0,
        maximum_frequency_hz=3800.0,
        relative_difference=0.95,
    )
    watermark = AudioWatermarkConfig(attribution_token_bytes=4, parity_symbols=16)
    pilot = SpectralAudioPilot(b"audio-pilot-test-key", configuration, watermark)
    return allocation.handle(), pilot, ContrastivePilotCalibratedExperiment(pilot, 0.01, _profile())


def _wrong_encoder() -> tuple[SpectralAudioPilot, ContrastivePilotCalibratedExperiment]:
    """Create the wrong-secret pilot and encoder control."""

    configuration = SpectralPilotConfig(
        minimum_frequency_hz=500.0,
        maximum_frequency_hz=3800.0,
        relative_difference=0.95,
    )
    watermark = AudioWatermarkConfig(attribution_token_bytes=4, parity_symbols=16)
    pilot = SpectralAudioPilot(b"wrong-audio-pilot-test-key", configuration, watermark)
    return pilot, ContrastivePilotCalibratedExperiment(pilot, 0.01, _profile())


def _vote(stage_vote: StageVote) -> BlindRecoveryVote:
    """Convert an experiment controller vote into the application policy model."""

    measurement = stage_vote.measurement or {}
    return BlindRecoveryVote(
        stage_vote.accepted,
        len(stage_vote.attempts),
        stage_vote.stage_name,
        int(measurement["rs_error_cost"]) if "rs_error_cost" in measurement else None,
        stage_vote.ambiguous_successes,
        stage_vote.rejection_reason,
    )


def _decision_name(status: BlindRecoveryStatus) -> str:
    """Return the short archive spelling used by this experiment."""

    return {
        BlindRecoveryStatus.ACCEPTED: "accept",
        BlindRecoveryStatus.REJECTED: "reject",
        BlindRecoveryStatus.ABSTAINED: "abstain",
    }[status]


def evaluate_scenario(scenario: DecisionScenario) -> PrototypeDecision:
    """Evaluate one scenario through the staged controller and controls."""

    handle, pilot, encoder = _encoder()
    wrong_pilot, wrong_encoder = _wrong_encoder()
    source = _cover_variant(30, scenario.cover_seed, _trial_offset_seconds(scenario.offset_seed))
    embedding = encoder.embed(source, handle)
    attack = _attack(scenario.attack_name)
    stages = _controller_stages()
    attacked_watermarked = attack.transform(embedding.audio, 8600 + scenario.cover_seed)
    attacked_source = attack.transform(source, 8600 + scenario.cover_seed)
    wrong_plan = wrong_pilot.schema.plan_attribution(handle)
    watermarked = _run_controller(attacked_watermarked, encoder, embedding.carrier_plan, stages, (embedding, handle))
    unwatermarked = _run_controller(attacked_source, encoder, embedding.carrier_plan, stages)
    wrong_secret = _run_controller(attacked_watermarked, wrong_encoder, wrong_plan, stages)
    policy_decision = BlindRecoveryDecisionPolicy().decide(_vote(watermarked), (_vote(unwatermarked), _vote(wrong_secret)))
    measurement = watermarked.measurement or {}
    return PrototypeDecision(
        scenario.name,
        scenario.attack_name,
        scenario.cover_seed,
        _decision_name(policy_decision.status),
        policy_decision.reason,
        policy_decision.selected_stage,
        len(watermarked.attempts),
        bool(measurement.get("token_matches_input", False)),
        watermarked.accepted,
        unwatermarked.accepted,
        wrong_secret.accepted,
        int(measurement["rs_error_cost"]) if "rs_error_cost" in measurement else None,
        None,
    )


def _safe_evaluate(scenario: DecisionScenario) -> PrototypeDecision:
    """Evaluate one scenario and preserve failures as data."""

    try:
        return evaluate_scenario(scenario)
    except Exception as error:
        return PrototypeDecision(
            scenario.name,
            scenario.attack_name,
            scenario.cover_seed,
            "error",
            "execution_failure",
            None,
            0,
            False,
            False,
            False,
            False,
            None,
            f"{type(error).__name__}: {error}",
        )


def run() -> dict[str, object]:
    """Run the production-shaped prototype decision audit."""

    decisions = tuple(_safe_evaluate(scenario) for scenario in _scenarios())
    return {
        "goal": "test staged blind recovery as a bounded accept/abstain prototype",
        "decoder_received_oracle_map": False,
        "decoder_received_claimed_transport_plan": True,
        "acceptance_policy": "accept unique low-burden controller success only when controls abstain",
        "stages": [asdict(stage) for stage in _controller_stages()],
        "scenarios": [asdict(scenario) for scenario in _scenarios()],
        "summary": {
            "accepted": sum(decision.decision == "accept" for decision in decisions),
            "abstained": sum(decision.decision == "abstain" for decision in decisions),
            "rejected": sum(decision.decision == "reject" for decision in decisions),
            "errors": sum(decision.decision == "error" for decision in decisions),
            "control_acceptances": sum(decision.unwatermarked_accepted or decision.wrong_secret_accepted for decision in decisions),
            "exact_recoveries": sum(decision.exact_recovery for decision in decisions),
        },
        "decisions": [asdict(decision) for decision in decisions],
    }


def main() -> None:
    """Print the complete production-shaped decision audit."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
