"""Run iteration 001: audit original-geometry assumptions for blind recovery.

Goal: measure how much the current best non-oracle edge-mode decoder depends on
knowing the original sample geometry. Iteration 032 recovered named 250 ms edge
crops by deriving leading/trailing timing modes from received length loss, but
that requires an assumed original duration. This experiment keeps the encoder,
transport, local-pilot selector, 4-byte handle, 16 parity symbols, and attacks
fixed while varying only that decoder geometry assumption.

Toy flow:
    embed 30 s synthetic cover -> attack -> choose assumed original duration
        -> reconstruct edge modes without retained map -> record RS recovery

The decoder still receives the claimed transport plan. This is therefore a
claimed-handle non-oracle geometry audit, not unknown-handle discovery or a
general edit synchronizer.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
import json
from statistics import median

from ....pilot import PcmAudio, SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioWatermarkConfig
from ...non_oracle_reconstruction.iteration_005_contrastive_pilot_calibration.run import (
    ContrastivePilotCalibratedExperiment,
)
from ...non_oracle_reconstruction.iteration_011_blind_attack_validation.run import (
    AttackDefinition,
    _attack_definitions,
)
from ...non_oracle_reconstruction.iteration_019_registry_handle_parity_tradeoff.run import _profile
from ...non_oracle_reconstruction.iteration_021_coarse_hypothesis_bank.run import _allocation, _measurement
from ...non_oracle_reconstruction.iteration_032_edge_mode_coarse_bank.run import EdgeModeCoarseBankDecoder
from ...transport_optimization.iteration_006_duration_stability_bounds.run import (
    _cover_variant,
    _trial_offset_seconds,
)


SOURCE_DURATION_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class GeometryAssumption:
    """Describe one decoder-side belief about the original waveform duration."""

    name: str
    assumed_duration_seconds: float | None
    description: str

    def resolve(self, attacked_audio: PcmAudio) -> float:
        """Return the duration supplied to the decoder for one received waveform."""

        return attacked_audio.duration_seconds if self.assumed_duration_seconds is None else self.assumed_duration_seconds


@dataclass(frozen=True, slots=True)
class GeometryTrial:
    """Record one recovery attempt under one attack and decoder geometry assumption."""

    attack_name: str
    assumption_name: str
    trial_index: int
    cover_seed: int
    received_duration_seconds: float | None
    assumed_duration_seconds: float
    duration_error_ms: float
    edge_offsets: tuple[int, ...]
    hypothesis_count: int
    rs_success_count: int
    selected_offset_frames: int | None
    measurement: dict[str, object] | None
    unwatermarked_accepted: bool | None
    wrong_secret_accepted: bool | None
    error: str | None


class GeometryAssumptionEdgeModeDecoder(EdgeModeCoarseBankDecoder):
    """Run iteration 032's edge-mode policy with an explicit original-duration assumption."""

    def __init__(self, encoder: ContrastivePilotCalibratedExperiment, assumed_duration_seconds: float) -> None:
        """Initialize the inherited decoder and set both nominal-duration helpers."""

        if assumed_duration_seconds <= 0:
            raise ValueError("assumed_duration_seconds must be positive")
        super().__init__(encoder)
        self._phase_helper._nominal_duration_seconds = assumed_duration_seconds
        self._coarse_decoder._nominal_duration_seconds = assumed_duration_seconds


def _geometry_assumptions() -> tuple[GeometryAssumption, ...]:
    """Return exact, received-only, and near-miss duration assumptions for the first audit."""

    return (
        GeometryAssumption("exact_original_30s", SOURCE_DURATION_SECONDS, "original duration is known exactly"),
        GeometryAssumption("received_duration_only", None, "only the received waveform duration is known"),
        GeometryAssumption("original_minus_10ms", SOURCE_DURATION_SECONDS - 0.010, "original duration is underestimated by 10 ms"),
        GeometryAssumption("original_plus_10ms", SOURCE_DURATION_SECONDS + 0.010, "original duration is overestimated by 10 ms"),
        GeometryAssumption("original_minus_50ms", SOURCE_DURATION_SECONDS - 0.050, "original duration is underestimated by 50 ms"),
        GeometryAssumption("original_plus_50ms", SOURCE_DURATION_SECONDS + 0.050, "original duration is overestimated by 50 ms"),
    )


def _attacks() -> tuple[AttackDefinition, ...]:
    """Return clean PCM plus the named 250 ms single-edge crop transforms."""

    selected_names = {"clean_pcm", "leading_crop_025s", "trailing_crop_025s"}
    return tuple(attack for attack in _attack_definitions() if attack.name in selected_names)


def evaluate_variant(
    trial_index: int,
    attacks: Iterable[AttackDefinition],
    assumptions: Iterable[GeometryAssumption],
    include_controls: bool = False,
) -> tuple[GeometryTrial, ...]:
    """Evaluate one fresh source cover under every attack and duration assumption."""

    allocation = _allocation()
    handle = allocation.handle()
    cover_seed = 7800 + trial_index
    source = _cover_variant(30, cover_seed, _trial_offset_seconds(1700 + trial_index))
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
    records: list[GeometryTrial] = []
    for attack in attacks:
        for assumption in assumptions:
            try:
                attacked = attack.transform(embedding.audio, 8200 + trial_index)
                assumed_duration = assumption.resolve(attacked)
                decoder = GeometryAssumptionEdgeModeDecoder(encoder, assumed_duration)
                wrong_decoder = GeometryAssumptionEdgeModeDecoder(wrong_encoder, assumed_duration)
                edge_offsets = decoder.edge_offsets(attacked)
                decision = decoder.reconstruct(attacked, embedding.carrier_plan)
                unwatermarked_accepted = None
                wrong_secret_accepted = None
                if include_controls:
                    unwatermarked = decoder.reconstruct(
                        attack.transform(source, 8200 + trial_index),
                        embedding.carrier_plan,
                    )
                    wrong_secret = wrong_decoder.reconstruct(attacked, wrong_plan)
                    unwatermarked_accepted = unwatermarked.selected is not None
                    wrong_secret_accepted = wrong_secret.selected is not None
                selected = decision.selected
                measurement = _measurement(encoder, embedding, selected.reconstruction, handle) if selected else None
                records.append(
                    GeometryTrial(
                        attack.name,
                        assumption.name,
                        trial_index,
                        cover_seed,
                        attacked.duration_seconds,
                        assumed_duration,
                        (assumed_duration - SOURCE_DURATION_SECONDS) * 1000.0,
                        edge_offsets,
                        len(decision.hypotheses),
                        sum(h.reconstruction.extraction.recovery.token is not None for h in decision.hypotheses),
                        selected.offset_frames if selected else None,
                        measurement,
                        unwatermarked_accepted,
                        wrong_secret_accepted,
                        None,
                    )
                )
            except Exception as error:
                records.append(
                    GeometryTrial(
                        attack.name,
                        assumption.name,
                        trial_index,
                        cover_seed,
                        None,
                        assumption.assumed_duration_seconds or SOURCE_DURATION_SECONDS,
                        0.0,
                        (),
                        0,
                        0,
                        None,
                        None,
                        False,
                        False,
                        f"{type(error).__name__}: {error}",
                    )
                )
    return tuple(records)


def _summary(attack: AttackDefinition, assumption: GeometryAssumption, trials: tuple[GeometryTrial, ...]) -> dict[str, object]:
    """Aggregate recovery, selected offsets, RS costs, controls, and failures for one assumption."""

    measurements = tuple(trial.measurement for trial in trials if trial.measurement is not None)
    rs_costs = tuple(int(measurement["rs_error_cost"]) for measurement in measurements)
    selected_offsets = tuple(trial.selected_offset_frames for trial in trials if trial.selected_offset_frames is not None)
    controls_evaluated = any(
        trial.unwatermarked_accepted is not None or trial.wrong_secret_accepted is not None
        for trial in trials
    )
    return {
        "attack_name": attack.name,
        "assumption_name": assumption.name,
        "assumption_description": assumption.description,
        "trial_count": len(trials),
        "execution_failures": sum(trial.error is not None for trial in trials),
        "recoveries": len(measurements),
        "exact_recoveries": sum(bool(row["token_matches_input"]) for row in measurements),
        "median_rs_cost": median(rs_costs) if rs_costs else None,
        "maximum_rs_cost": max(rs_costs) if rs_costs else None,
        "selected_offsets": sorted(set(selected_offsets)),
        "unwatermarked_acceptances": (
            sum(bool(trial.unwatermarked_accepted) for trial in trials)
            if controls_evaluated
            else None
        ),
        "wrong_secret_acceptances": (
            sum(bool(trial.wrong_secret_accepted) for trial in trials)
            if controls_evaluated
            else None
        ),
    }


def run(trial_count: int = 1, include_controls: bool = False) -> dict[str, object]:
    """Run the first blind-recovery geometry audit and return machine-readable records."""

    attacks = _attacks()
    assumptions = _geometry_assumptions()
    trials = tuple(
        record
        for index in range(trial_count)
        for record in evaluate_variant(index, attacks, assumptions, include_controls)
    )
    return {
        "goal": "measure how much current non-oracle recovery depends on original-duration geometry",
        "decoder_received_oracle_map": False,
        "decoder_received_claimed_transport_plan": True,
        "source_duration_seconds": SOURCE_DURATION_SECONDS,
        "controls_evaluated": include_controls,
        "allocation": asdict(_allocation()),
        "profile": asdict(_profile()),
        "attacks": [attack.name for attack in attacks],
        "assumptions": [asdict(assumption) for assumption in assumptions],
        "validation_cover_seeds": list(range(7800, 7800 + trial_count)),
        "summaries": [
            _summary(
                attack,
                assumption,
                tuple(
                    trial
                    for trial in trials
                    if trial.attack_name == attack.name and trial.assumption_name == assumption.name
                ),
            )
            for attack in attacks
            for assumption in assumptions
        ],
        "trials": [asdict(trial) for trial in trials],
    }


def main() -> None:
    """Print the complete geometry-dependency audit for archival redirection."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
