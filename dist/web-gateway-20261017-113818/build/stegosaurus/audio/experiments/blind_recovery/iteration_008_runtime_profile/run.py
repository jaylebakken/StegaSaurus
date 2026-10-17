"""Run iteration 008: profile runtime across blind-recovery search modes.

Goal: measure where the current bounded recovery pipeline spends time. Runtime
matters because unknown crop search and future watermark localization both scale
with the number of geometry/window hypotheses.

Toy flow:
    build one watermarked fixture -> run named search modes with perf counters
        -> record attempts, decision, recovery, and elapsed milliseconds

This is a local timing audit on one synthetic fixture. It is not a benchmark
claim across machines, corpora, codecs, or production infrastructure.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from statistics import median
from time import perf_counter

from ....attribution_core.blind_policy import BlindRecoveryDecisionPolicy, BlindRecoveryStatus, BlindRecoveryVote
from ....pilot import PcmAudio, SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioWatermarkConfig
from ...non_oracle_reconstruction.iteration_005_contrastive_pilot_calibration.run import ContrastivePilotCalibratedExperiment
from ...non_oracle_reconstruction.iteration_019_registry_handle_parity_tradeoff.run import _profile
from ...non_oracle_reconstruction.iteration_021_coarse_hypothesis_bank.run import _allocation
from ...transport_optimization.iteration_006_duration_stability_bounds.run import _cover_variant, _trial_offset_seconds
from ..iteration_004_staged_recovery_controller.run import ControllerStage, StageVote, _run_controller
from ..iteration_007_dual_edge_crop_search.run import _crop as _dual_crop
from ..iteration_007_dual_edge_crop_search.run import _run_search as _dual_search
from ..iteration_007_dual_edge_crop_search.run import DualCropScenario


@dataclass(frozen=True, slots=True)
class RuntimeTrial:
    """Record one timed recovery mode."""
    mode_name: str
    decision: str
    reason: str
    attempted_hypotheses: int
    exact_recovery: bool
    elapsed_ms: float


def _encoder() -> tuple[bytes, SpectralAudioPilot, ContrastivePilotCalibratedExperiment]:
    """Create the fixed pilot and encoder for the runtime profile."""

    config = SpectralPilotConfig(minimum_frequency_hz=500.0, maximum_frequency_hz=3800.0, relative_difference=0.95)
    pilot = SpectralAudioPilot(b"audio-pilot-test-key", config, AudioWatermarkConfig(attribution_token_bytes=4, parity_symbols=16))
    return _allocation().handle(), pilot, ContrastivePilotCalibratedExperiment(pilot, 0.01, _profile())


def _single_edge_stages() -> tuple[ControllerStage, ...]:
    """Return the iteration 006 recommended 500 ms single-edge grid."""

    return (
        ControllerStage("received_only", (0.0,), "assume received duration"),
        ControllerStage("crop_loss_0.125s", (0.125,), "allow 125 ms crop"),
        ControllerStage("crop_loss_0.250s", (0.25,), "allow 250 ms crop"),
        ControllerStage("crop_loss_0.375s", (0.375,), "allow 375 ms crop"),
        ControllerStage("crop_loss_0.500s", (0.5,), "allow 500 ms crop"),
    )


def _crop(audio: PcmAudio, leading_seconds: float = 0.0, trailing_seconds: float = 0.0) -> PcmAudio:
    """Apply a simple deterministic edge crop for timing modes."""

    lead = int(round(leading_seconds * audio.sample_rate))
    trail = int(round(trailing_seconds * audio.sample_rate))
    end = len(audio.samples) - trail if trail else len(audio.samples)
    return PcmAudio(audio.samples[lead:end], audio.sample_rate)


def _vote(stage_vote: StageVote) -> BlindRecoveryVote:
    """Convert staged output into the shared decision policy model."""

    measurement = stage_vote.measurement or {}
    return BlindRecoveryVote(stage_vote.accepted, len(stage_vote.attempts), stage_vote.stage_name, int(measurement["rs_error_cost"]) if "rs_error_cost" in measurement else None, stage_vote.ambiguous_successes, stage_vote.rejection_reason)


def _decision_name(status: BlindRecoveryStatus) -> str:
    """Return compact archive spelling."""

    return {BlindRecoveryStatus.ACCEPTED: "accept", BlindRecoveryStatus.REJECTED: "reject", BlindRecoveryStatus.ABSTAINED: "abstain"}[status]


def _timed(mode_name: str, stage_vote: StageVote, started_at: float) -> RuntimeTrial:
    """Convert one timed staged vote into an archive row."""

    decision = BlindRecoveryDecisionPolicy(maximum_hypotheses=max(1, len(stage_vote.attempts))).decide(_vote(stage_vote))
    measurement = stage_vote.measurement or {}
    return RuntimeTrial(
        mode_name,
        _decision_name(decision.status),
        decision.reason,
        len(stage_vote.attempts),
        bool(measurement.get("token_matches_input", False)),
        (perf_counter() - started_at) * 1000.0,
    )


def run() -> dict[str, object]:
    """Run a compact runtime profile for current blind-recovery modes."""

    handle, pilot, encoder = _encoder()
    source = _cover_variant(30, 7900, _trial_offset_seconds(1800))
    embedding = encoder.embed(source, handle)
    rows: list[RuntimeTrial] = []
    started = perf_counter()
    rows.append(_timed("clean_received_only", _run_controller(embedding.audio, encoder, embedding.carrier_plan, (_single_edge_stages()[0],), (embedding, handle)), started))
    started = perf_counter()
    rows.append(_timed("leading_250ms_single_edge_grid", _run_controller(_crop(embedding.audio, 0.25), encoder, embedding.carrier_plan, _single_edge_stages(), (embedding, handle)), started))
    started = perf_counter()
    dual = DualCropScenario("lead250_trail250", 0.25, 0.25)
    rows.append(_timed("lead250_trail250_dual_grid", _dual_search(_dual_crop(embedding.audio, dual), encoder, embedding.carrier_plan, (embedding, handle)), started))
    return {
        "goal": "profile runtime of bounded blind-recovery search modes",
        "cover_seed": 7900,
        "summary": _summary(tuple(rows)),
        "trials": [asdict(row) for row in rows],
    }


def _summary(rows: tuple[RuntimeTrial, ...]) -> dict[str, object]:
    """Aggregate timing and attempt counts."""

    return {
        "median_elapsed_ms": median(row.elapsed_ms for row in rows),
        "maximum_elapsed_ms": max(row.elapsed_ms for row in rows),
        "total_elapsed_ms": sum(row.elapsed_ms for row in rows),
        "total_attempted_hypotheses": sum(row.attempted_hypotheses for row in rows),
    }


def main() -> None:
    """Print the compact runtime profile."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
