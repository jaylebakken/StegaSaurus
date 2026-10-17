"""Run iteration 006: estimate a feasible bound for unknown single-edge crops.

Goal: move from named `250 ms` crop recovery to a bounded unknown-crop policy.
The experiment treats unknown length as a declared search bank and asks how far
an early controller can expand before runtime and controls become unattractive.

Toy flow:
    received audio -> received-duration stage -> crop-length grid stages
        -> unique RS-success decision -> optional controls for recommended max

This remains claimed-plan recovery. The decoder receives the claimed carrier
plan and searches only bounded single-edge length hypotheses; it is not
unknown-handle discovery or a general edit synchronizer.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from statistics import median

from ....attribution_core.blind_policy import BlindRecoveryDecisionPolicy, BlindRecoveryStatus, BlindRecoveryVote
from ....pilot import PcmAudio, SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioWatermarkConfig
from ...non_oracle_reconstruction.iteration_005_contrastive_pilot_calibration.run import (
    ContrastivePilotCalibratedExperiment,
)
from ...non_oracle_reconstruction.iteration_019_registry_handle_parity_tradeoff.run import _profile
from ...non_oracle_reconstruction.iteration_021_coarse_hypothesis_bank.run import _allocation
from ...transport_optimization.iteration_006_duration_stability_bounds.run import (
    _cover_variant,
    _trial_offset_seconds,
)
from ..iteration_004_staged_recovery_controller.run import ControllerStage, StageVote, _run_controller


@dataclass(frozen=True, slots=True)
class CropSearchPolicy:
    """Describe one bounded unknown-crop search bank."""
    name: str
    maximum_crop_seconds: float
    step_seconds: float


@dataclass(frozen=True, slots=True)
class CropScenario:
    """Describe one synthetic single-edge crop condition."""
    name: str
    direction: str
    crop_seconds: float


@dataclass(frozen=True, slots=True)
class CropBoundTrial:
    """Record one crop scenario under one bounded search policy."""
    scenario_name: str
    policy_name: str
    decision: str
    reason: str
    selected_stage: str | None
    attempted_hypotheses: int
    exact_recovery: bool
    rs_cost: int | None
    controls_evaluated: bool
    unwatermarked_accepted: bool | None
    wrong_secret_accepted: bool | None
    error: str | None


def _policies() -> tuple[CropSearchPolicy, ...]:
    """Return candidate early-production unknown-crop bounds."""
    return (
        CropSearchPolicy("unknown_crop_to_250ms", 0.25, 0.125),
        CropSearchPolicy("unknown_crop_to_500ms", 0.5, 0.125),
    )


def _scenarios() -> tuple[CropScenario, ...]:
    """Return a compact length/direction grid for the first unknown-crop audit."""
    return (
        CropScenario("leading_125ms", "leading", 0.125),
        CropScenario("trailing_125ms", "trailing", 0.125),
        CropScenario("leading_250ms", "leading", 0.25),
        CropScenario("trailing_250ms", "trailing", 0.25),
        CropScenario("leading_500ms", "leading", 0.5),
        CropScenario("trailing_500ms", "trailing", 0.5),
    )


def _stages(policy: CropSearchPolicy) -> tuple[ControllerStage, ...]:
    """Convert one crop policy into staged duration-loss hypotheses."""
    count = int(policy.maximum_crop_seconds / policy.step_seconds)
    losses = tuple(round(index * policy.step_seconds, 6) for index in range(1, count + 1))
    received = (ControllerStage("received_only", (0.0,), "assume received duration is source duration"),)
    return received + tuple(ControllerStage(f"crop_loss_{loss:.3f}s", (loss,), f"allow one unknown edge crop of {loss:.3f} seconds") for loss in losses)


def _crop(audio: PcmAudio, scenario: CropScenario) -> PcmAudio:
    """Apply a deterministic leading or trailing crop."""
    sample_count = int(round(scenario.crop_seconds * audio.sample_rate))
    if sample_count >= len(audio.samples):
        raise ValueError("crop removes the complete audio")
    if scenario.direction == "leading":
        return PcmAudio(audio.samples[sample_count:], audio.sample_rate)
    if scenario.direction == "trailing":
        return PcmAudio(audio.samples[:-sample_count], audio.sample_rate)
    raise ValueError("scenario direction must be leading or trailing")


def _vote(stage_vote: StageVote) -> BlindRecoveryVote:
    """Convert controller output into the application decision policy model."""
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
    """Return compact archive spelling for a policy decision."""
    return {BlindRecoveryStatus.ACCEPTED: "accept", BlindRecoveryStatus.REJECTED: "reject", BlindRecoveryStatus.ABSTAINED: "abstain"}[status]


def _encoder(secret: bytes) -> tuple[bytes, SpectralAudioPilot, ContrastivePilotCalibratedExperiment]:
    """Create a fixed pilot and encoder for one secret."""
    configuration = SpectralPilotConfig(minimum_frequency_hz=500.0, maximum_frequency_hz=3800.0, relative_difference=0.95)
    watermark = AudioWatermarkConfig(attribution_token_bytes=4, parity_symbols=16)
    pilot = SpectralAudioPilot(secret, configuration, watermark)
    return _allocation().handle(), pilot, ContrastivePilotCalibratedExperiment(pilot, 0.01, _profile())


def _trial(scenario: CropScenario, policy: CropSearchPolicy, include_controls: bool) -> CropBoundTrial:
    """Evaluate one scenario and policy, optionally including negative controls."""
    handle, pilot, encoder = _encoder(b"audio-pilot-test-key")
    wrong_pilot = None
    wrong_encoder = None
    if include_controls:
        _, wrong_pilot, wrong_encoder = _encoder(b"wrong-audio-pilot-test-key")
    source = _cover_variant(30, 7900, _trial_offset_seconds(1800))
    embedding = encoder.embed(source, handle)
    stages = _stages(policy)
    watermarked = _run_controller(_crop(embedding.audio, scenario), encoder, embedding.carrier_plan, stages, (embedding, handle))
    controls: tuple[BlindRecoveryVote, ...] = ()
    unwatermarked_accepted = None
    wrong_secret_accepted = None
    if include_controls and wrong_pilot is not None and wrong_encoder is not None:
        unwatermarked = _run_controller(_crop(source, scenario), encoder, embedding.carrier_plan, stages)
        wrong_plan = wrong_pilot.schema.plan_attribution(handle)
        wrong_secret = _run_controller(_crop(embedding.audio, scenario), wrong_encoder, wrong_plan, stages)
        controls = (_vote(unwatermarked), _vote(wrong_secret))
        unwatermarked_accepted = unwatermarked.accepted
        wrong_secret_accepted = wrong_secret.accepted
    decision = BlindRecoveryDecisionPolicy(maximum_hypotheses=len(stages)).decide(_vote(watermarked), controls)
    measurement = watermarked.measurement or {}
    return CropBoundTrial(
        scenario.name,
        policy.name,
        _decision_name(decision.status),
        decision.reason,
        decision.selected_stage,
        len(watermarked.attempts),
        bool(measurement.get("token_matches_input", False)),
        int(measurement["rs_error_cost"]) if "rs_error_cost" in measurement else None,
        include_controls,
        unwatermarked_accepted,
        wrong_secret_accepted,
        None,
    )


def _safe_trial(scenario: CropScenario, policy: CropSearchPolicy, include_controls: bool) -> CropBoundTrial:
    """Evaluate one trial and preserve execution failures as data."""
    try:
        return _trial(scenario, policy, include_controls)
    except Exception as error:
        message = f"{type(error).__name__}: {error}"
        return CropBoundTrial(scenario.name, policy.name, "error", "execution_failure", None, 0, False, None, include_controls, None, None, message)


def _recommended_policy(trials: tuple[CropBoundTrial, ...]) -> str | None:
    """Choose the widest policy with full recovery and no ambiguity in the watermarked sweep."""
    recommended = None
    for policy in _policies():
        rows = tuple(trial for trial in trials if trial.policy_name == policy.name and not trial.controls_evaluated)
        if rows and all(trial.decision == "accept" and trial.exact_recovery for trial in rows):
            recommended = policy.name
    return recommended


def run() -> dict[str, object]:
    """Run the unknown-crop bound audit and return machine-readable evidence."""
    scenarios = _scenarios()
    policies = _policies()
    sweep = tuple(_safe_trial(scenario, policy, False) for policy in policies for scenario in scenarios)
    recommended = _recommended_policy(sweep) or "unknown_crop_to_500ms"
    control_policy = next(policy for policy in policies if policy.name == recommended)
    controls = tuple(
        _safe_trial(scenario, control_policy, True)
        for scenario in scenarios
        if scenario.crop_seconds in {0.25, control_policy.maximum_crop_seconds}
    )
    all_trials = sweep + controls
    return {
        "goal": "estimate an early-production maximum for bounded unknown single-edge crops",
        "decoder_received_oracle_map": False,
        "decoder_received_claimed_transport_plan": True,
        "cover_seed": 7900,
        "offset_seed": 1800,
        "policies": [asdict(policy) for policy in policies],
        "scenarios": [asdict(scenario) for scenario in scenarios],
        "recommended_policy": recommended,
        "summary": [_summary(policy.name, tuple(trial for trial in all_trials if trial.policy_name == policy.name)) for policy in policies],
        "trials": [asdict(trial) for trial in all_trials],
    }


def _summary(policy_name: str, trials: tuple[CropBoundTrial, ...]) -> dict[str, object]:
    """Aggregate recovery, attempts, and control behavior for one policy."""
    watermarked = tuple(trial for trial in trials if not trial.controls_evaluated)
    controls = tuple(trial for trial in trials if trial.controls_evaluated)
    attempts = tuple(trial.attempted_hypotheses for trial in watermarked if trial.attempted_hypotheses)
    return {
        "policy_name": policy_name,
        "watermarked_trials": len(watermarked),
        "watermarked_acceptances": sum(trial.decision == "accept" for trial in watermarked),
        "exact_recoveries": sum(trial.exact_recovery for trial in watermarked),
        "median_watermarked_attempts": median(attempts) if attempts else None,
        "maximum_watermarked_attempts": max(attempts) if attempts else None,
        "control_trials": len(controls),
        "control_acceptances": sum(bool(trial.unwatermarked_accepted) or bool(trial.wrong_secret_accepted) for trial in controls),
        "execution_failures": sum(trial.error is not None for trial in trials),
    }


def main() -> None:
    """Print the complete unknown-crop bound audit."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
