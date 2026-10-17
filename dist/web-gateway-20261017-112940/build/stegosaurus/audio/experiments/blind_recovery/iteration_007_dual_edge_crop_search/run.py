"""Run iteration 007: search bounded leading-plus-trailing crop hypotheses.

Goal: extend the unknown-crop search from one-edge loss to dual-edge loss. A
received file may be shorter because samples were removed from both the leading
and trailing edges, so the verifier must search total source-duration loss and
the leading-loss offset separately.

Toy flow:
    dual-cropped audio -> total-loss/leading-loss grid -> explicit edge decoder
        -> unique low-burden RS success -> accept | abstain

This remains claimed-plan recovery with bounded geometry hypotheses. It is not
unknown-handle discovery, arbitrary edit synchronization, or localization in a
longer unrelated recording.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from statistics import median

from ....attribution_core.blind_policy import BlindRecoveryDecisionPolicy, BlindRecoveryStatus, BlindRecoveryVote
from ....pilot import PcmAudio, SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioWatermarkConfig, CarrierPlan
from ...non_oracle_reconstruction.iteration_005_contrastive_pilot_calibration.run import ContrastivePilotCalibratedExperiment
from ...non_oracle_reconstruction.iteration_019_registry_handle_parity_tradeoff.run import _profile
from ...non_oracle_reconstruction.iteration_021_coarse_hypothesis_bank.run import _allocation, _measurement
from ...transport_optimization.iteration_006_duration_stability_bounds.run import _cover_variant, _trial_offset_seconds
from ..iteration_001_geometry_dependency_audit.run import GeometryAssumptionEdgeModeDecoder
from ..iteration_002_duration_bank_voting.run import DurationCandidate
from ..iteration_004_staged_recovery_controller.run import StageVote, _rank


@dataclass(frozen=True, slots=True)
class DualCropScenario:
    """Describe one bounded leading-plus-trailing crop condition."""
    name: str
    leading_seconds: float
    trailing_seconds: float


@dataclass(frozen=True, slots=True)
class DualCropTrial:
    """Record one dual-edge crop recovery and optional controls."""
    scenario_name: str
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


class ExplicitLeadingLossDecoder(GeometryAssumptionEdgeModeDecoder):
    """Run edge-mode recovery with an explicit leading-loss offset hypothesis."""

    def __init__(self, encoder: ContrastivePilotCalibratedExperiment, assumed_duration_seconds: float, leading_loss_seconds: float) -> None:
        """Initialize the duration assumption and leading crop offset."""

        super().__init__(encoder, assumed_duration_seconds)
        self._leading_loss_seconds = leading_loss_seconds

    def edge_offsets(self, audio: PcmAudio) -> tuple[int, ...]:
        """Return floor/ceil offsets for the explicit leading crop duration."""

        hop_size = self._pilot._config.hop_size
        position = self._leading_loss_seconds * audio.sample_rate / hop_size
        offsets = {round(position), int(position // 1), int(-(-position // 1))}
        maximum_offset = self._coarse_decoder._policy.maximum_offset_frames
        return tuple(sorted(offset for offset in offsets if -maximum_offset <= offset <= maximum_offset))


def _scenarios() -> tuple[DualCropScenario, ...]:
    """Return compact dual-edge crop cases within the iteration 006 bound."""

    return (
        DualCropScenario("lead125_trail125", 0.125, 0.125),
        DualCropScenario("lead250_trail250", 0.25, 0.25),
        DualCropScenario("lead125_trail375", 0.125, 0.375),
        DualCropScenario("lead375_trail125", 0.375, 0.125),
    )


def _geometry_grid(step_seconds: float = 0.125, maximum_total_seconds: float = 0.5) -> tuple[tuple[float, float], ...]:
    """Return total-loss and leading-loss hypotheses for bounded dual crops."""

    steps = range(0, int(maximum_total_seconds / step_seconds) + 1)
    return tuple((total * step_seconds, leading * step_seconds) for total in steps for leading in range(total + 1))


def _crop(audio: PcmAudio, scenario: DualCropScenario) -> PcmAudio:
    """Apply deterministic leading and trailing crops to one audio object."""

    lead = int(round(scenario.leading_seconds * audio.sample_rate))
    trail = int(round(scenario.trailing_seconds * audio.sample_rate))
    if lead + trail >= len(audio.samples):
        raise ValueError("dual crop removes the complete audio")
    end = len(audio.samples) - trail if trail else len(audio.samples)
    return PcmAudio(audio.samples[lead:end], audio.sample_rate)


def _candidate(audio: PcmAudio, encoder: ContrastivePilotCalibratedExperiment, plan: CarrierPlan, total_loss: float, leading_loss: float) -> tuple[DurationCandidate, object | None]:
    """Evaluate one explicit dual-edge geometry hypothesis."""

    decoder = ExplicitLeadingLossDecoder(encoder, audio.duration_seconds + total_loss, leading_loss)
    decision = decoder.reconstruct(audio, plan)
    selected = decision.selected
    return (
        DurationCandidate(audio.duration_seconds + total_loss, leading_loss, decoder.edge_offsets(audio), selected.offset_frames if selected else None, sum(h.reconstruction.extraction.recovery.token is not None for h in decision.hypotheses), None),
        selected,
    )


def _select(pairs: tuple[tuple[DurationCandidate, object | None], ...]) -> tuple[DurationCandidate, object] | None:
    """Return a unique lowest-burden successful hypothesis."""

    successes = tuple(pair for pair in pairs if pair[1] is not None)
    if not successes:
        return None
    ranked = sorted(successes, key=lambda item: _rank(item[1], item[0].inferred_loss_seconds))
    return ranked[0] if len(ranked) == 1 or _rank(ranked[0][1], ranked[0][0].inferred_loss_seconds) != _rank(ranked[1][1], ranked[1][0].inferred_loss_seconds) else None


def _run_search(audio: PcmAudio, encoder: ContrastivePilotCalibratedExperiment, plan: CarrierPlan, context: tuple[object, bytes] | None = None) -> StageVote:
    """Search the bounded dual-edge grid and return one staged vote."""

    pairs = tuple(_candidate(audio, encoder, plan, total, leading) for total, leading in _geometry_grid())
    selected = _select(pairs)
    attempts = tuple(candidate for candidate, _ in pairs)
    if selected is None:
        return StageVote(False, None, None, None, attempts, 0, "no_unique_success")
    candidate, hypothesis = selected
    measurement = None
    if context is not None:
        embedding, handle = context
        measurement = _measurement(encoder, embedding, hypothesis.reconstruction, handle)
    return StageVote(True, f"total_{candidate.assumed_duration_seconds - audio.duration_seconds:.3f}s_lead_{candidate.inferred_loss_seconds:.3f}s", candidate, measurement, attempts, 0, None)


def _vote(stage_vote: StageVote) -> BlindRecoveryVote:
    """Convert a staged search vote into the application policy model."""

    measurement = stage_vote.measurement or {}
    return BlindRecoveryVote(stage_vote.accepted, len(stage_vote.attempts), stage_vote.stage_name, int(measurement["rs_error_cost"]) if "rs_error_cost" in measurement else None, stage_vote.ambiguous_successes, stage_vote.rejection_reason)


def _decision_name(status: BlindRecoveryStatus) -> str:
    """Return compact archive spelling."""

    return {BlindRecoveryStatus.ACCEPTED: "accept", BlindRecoveryStatus.REJECTED: "reject", BlindRecoveryStatus.ABSTAINED: "abstain"}[status]


def _encoder(secret: bytes) -> tuple[bytes, SpectralAudioPilot, ContrastivePilotCalibratedExperiment]:
    """Create the fixed pilot and encoder for one secret."""

    config = SpectralPilotConfig(minimum_frequency_hz=500.0, maximum_frequency_hz=3800.0, relative_difference=0.95)
    pilot = SpectralAudioPilot(secret, config, AudioWatermarkConfig(attribution_token_bytes=4, parity_symbols=16))
    return _allocation().handle(), pilot, ContrastivePilotCalibratedExperiment(pilot, 0.01, _profile())


def _trial(scenario: DualCropScenario, include_controls: bool) -> DualCropTrial:
    """Evaluate one dual-edge crop scenario and optional controls."""

    handle, pilot, encoder = _encoder(b"audio-pilot-test-key")
    source = _cover_variant(30, 7900, _trial_offset_seconds(1800))
    embedding = encoder.embed(source, handle)
    watermarked = _run_search(_crop(embedding.audio, scenario), encoder, embedding.carrier_plan, (embedding, handle))
    controls: tuple[BlindRecoveryVote, ...] = ()
    unwatermarked_accepted = None
    wrong_secret_accepted = None
    if include_controls:
        _, wrong_pilot, wrong_encoder = _encoder(b"wrong-audio-pilot-test-key")
        unwatermarked = _run_search(_crop(source, scenario), encoder, embedding.carrier_plan)
        wrong_secret = _run_search(_crop(embedding.audio, scenario), wrong_encoder, wrong_pilot.schema.plan_attribution(handle))
        controls = (_vote(unwatermarked), _vote(wrong_secret))
        unwatermarked_accepted = unwatermarked.accepted
        wrong_secret_accepted = wrong_secret.accepted
    decision = BlindRecoveryDecisionPolicy(maximum_hypotheses=len(_geometry_grid())).decide(_vote(watermarked), controls)
    measurement = watermarked.measurement or {}
    return DualCropTrial(scenario.name, _decision_name(decision.status), decision.reason, decision.selected_stage, len(watermarked.attempts), bool(measurement.get("token_matches_input", False)), int(measurement["rs_error_cost"]) if "rs_error_cost" in measurement else None, include_controls, unwatermarked_accepted, wrong_secret_accepted, None)


def _safe_trial(scenario: DualCropScenario, include_controls: bool) -> DualCropTrial:
    """Evaluate one scenario and keep execution failures visible."""

    try:
        return _trial(scenario, include_controls)
    except Exception as error:
        return DualCropTrial(scenario.name, "error", "execution_failure", None, 0, False, None, include_controls, None, None, f"{type(error).__name__}: {error}")


def run() -> dict[str, object]:
    """Run the dual-edge crop search audit."""

    scenarios = _scenarios()
    watermarked = tuple(_safe_trial(scenario, False) for scenario in scenarios)
    controls = tuple(_safe_trial(scenario, True) for scenario in scenarios[:2])
    return {
        "goal": "search bounded leading-plus-trailing crop geometry hypotheses",
        "decoder_received_oracle_map": False,
        "decoder_received_claimed_transport_plan": True,
        "geometry_hypotheses": len(_geometry_grid()),
        "scenarios": [asdict(scenario) for scenario in scenarios],
        "summary": _summary(watermarked, controls),
        "trials": [asdict(trial) for trial in watermarked + controls],
    }


def _summary(watermarked: tuple[DualCropTrial, ...], controls: tuple[DualCropTrial, ...]) -> dict[str, object]:
    """Aggregate recovery, controls, and attempt counts."""

    attempts = tuple(trial.attempted_hypotheses for trial in watermarked if trial.attempted_hypotheses)
    return {
        "watermarked_trials": len(watermarked),
        "watermarked_acceptances": sum(trial.decision == "accept" for trial in watermarked),
        "exact_recoveries": sum(trial.exact_recovery for trial in watermarked),
        "median_attempts": median(attempts) if attempts else None,
        "control_trials": len(controls),
        "control_acceptances": sum(bool(trial.unwatermarked_accepted) or bool(trial.wrong_secret_accepted) for trial in controls),
        "execution_failures": sum(trial.error is not None for trial in watermarked + controls),
    }


def main() -> None:
    """Print the complete dual-edge crop audit."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
