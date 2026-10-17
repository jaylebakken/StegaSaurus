"""Run iteration 002: synchronized duration-bank voting for blind recovery.

Goal: reduce the exact-original-duration requirement found in iteration 001
without changing the watermark carrier pipeline. A caller may know something
about its distribution pipeline, such as "the received file may be clean or may
have lost one 250 ms edge." This experiment runs synchronized recovery attempts
for those plausible original-duration hypotheses and votes only among
decoder-visible Reed--Solomon successes.

Toy flow:
    received audio -> duration bank -> edge-mode decoder per duration
        -> uniquely best RS success -> post-hoc attribution measurement

The decoder still receives a claimed transport plan. The experiment studies how
to apply the current pipeline with less exact geometry, not unknown-handle
discovery or broad edit synchronization.
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
from ...transport_optimization.iteration_006_duration_stability_bounds.run import (
    _cover_variant,
    _trial_offset_seconds,
)
from ..iteration_001_geometry_dependency_audit.run import GeometryAssumptionEdgeModeDecoder


@dataclass(frozen=True, slots=True)
class DurationBank:
    """Describe a caller policy for plausible original-duration hypotheses."""

    name: str
    loss_seconds: tuple[float, ...]
    description: str


@dataclass(frozen=True, slots=True)
class DurationCandidate:
    """Record one synchronized decoder run under one assumed source duration."""

    assumed_duration_seconds: float
    inferred_loss_seconds: float
    edge_offsets: tuple[int, ...]
    selected_offset_frames: int | None
    rs_success_count: int
    measurement: dict[str, object] | None


@dataclass(frozen=True, slots=True)
class DurationBankTrial:
    """Record one attack, one duration bank, selected hypothesis, and post-hoc measurement."""

    attack_name: str
    bank_name: str
    trial_index: int
    cover_seed: int
    received_duration_seconds: float | None
    candidate_count: int
    selected_assumed_duration_seconds: float | None
    selected_loss_seconds: float | None
    selected_offset_frames: int | None
    measurement: dict[str, object] | None
    candidates: tuple[DurationCandidate, ...]
    error: str | None


def _duration_banks() -> tuple[DurationBank, ...]:
    """Return minimal and pipeline-informed duration policies for the first voting pass."""

    return (
        DurationBank("received_only", (0.0,), "assume the received duration is the original duration"),
        DurationBank("clean_or_250ms_edge_loss", (0.0, 0.25), "assume clean audio or one 250 ms edge loss"),
        DurationBank(
            "clean_or_250ms_edge_loss_jittered",
            (0.0, 0.24, 0.25, 0.26),
            "allow a narrow around-250 ms edge-loss tolerance",
        ),
    )


def _attacks() -> tuple[AttackDefinition, ...]:
    """Return clean PCM plus the named 250 ms single-edge crop transforms."""

    selected_names = {"clean_pcm", "leading_crop_025s", "trailing_crop_025s"}
    return tuple(attack for attack in _attack_definitions() if attack.name in selected_names)


def _select_candidate(
    candidates: tuple[tuple[DurationCandidate, object], ...],
) -> tuple[DurationCandidate, object] | None:
    """Select a unique lowest-burden RS success across synchronized duration runs."""

    successful = tuple(candidate for candidate in candidates if candidate[1] is not None)
    if not successful:
        return None

    def rank(candidate: tuple[DurationCandidate, object]) -> tuple[int, int, int, float]:
        """Rank by decoder-visible correction burden, then smaller inferred pipeline loss."""

        recovery = candidate[1].reconstruction.extraction.recovery.channel_recovery
        return (
            len(recovery.corrected_positions),
            len(recovery.erasure_positions),
            recovery.synchronization_mismatches,
            candidate[0].inferred_loss_seconds,
        )

    ranked = sorted(successful, key=rank)
    return ranked[0] if len(ranked) == 1 or rank(ranked[0]) != rank(ranked[1]) else None


def _evaluate_bank(
    attacked: PcmAudio,
    bank: DurationBank,
    encoder: ContrastivePilotCalibratedExperiment,
    embedding,
    handle: bytes,
) -> tuple[DurationBankTrial | None, tuple[DurationCandidate, ...]]:
    """Run a duration bank and return the selected measurement plus every candidate record."""

    candidates: list[DurationCandidate] = []
    candidate_pairs: list[tuple[DurationCandidate, object | None]] = []
    for loss_seconds in bank.loss_seconds:
        assumed_duration = attacked.duration_seconds + loss_seconds
        decoder = GeometryAssumptionEdgeModeDecoder(encoder, assumed_duration)
        decision = decoder.reconstruct(attacked, embedding.carrier_plan)
        selected = decision.selected
        measurement = _measurement(encoder, embedding, selected.reconstruction, handle) if selected else None
        candidate = DurationCandidate(
            assumed_duration,
            loss_seconds,
            decoder.edge_offsets(attacked),
            selected.offset_frames if selected else None,
            sum(h.reconstruction.extraction.recovery.token is not None for h in decision.hypotheses),
            measurement,
        )
        candidates.append(candidate)
        candidate_pairs.append((candidate, selected))
    chosen = _select_candidate(tuple(candidate_pairs))
    if chosen is None:
        return None, tuple(candidates)
    chosen_candidate, chosen_hypothesis = chosen
    chosen_measurement = _measurement(encoder, embedding, chosen_hypothesis.reconstruction, handle)
    return (
        DurationBankTrial(
            "",
            bank.name,
            0,
            0,
            attacked.duration_seconds,
            len(candidates),
            chosen_candidate.assumed_duration_seconds,
            chosen_candidate.inferred_loss_seconds,
            chosen_candidate.selected_offset_frames,
            chosen_measurement,
            tuple(candidates),
            None,
        ),
        tuple(candidates),
    )


def evaluate_variant(
    trial_index: int,
    attacks: Iterable[AttackDefinition],
    banks: Iterable[DurationBank],
) -> tuple[DurationBankTrial, ...]:
    """Evaluate one fresh source cover under each named attack and duration-bank policy."""

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
    records: list[DurationBankTrial] = []
    for attack in attacks:
        for bank in banks:
            try:
                attacked = attack.transform(embedding.audio, 8300 + trial_index)
                selected, candidates = _evaluate_bank(attacked, bank, encoder, embedding, handle)
                if selected is None:
                    records.append(
                        DurationBankTrial(
                            attack.name,
                            bank.name,
                            trial_index,
                            cover_seed,
                            attacked.duration_seconds,
                            len(candidates),
                            None,
                            None,
                            None,
                            None,
                            candidates,
                            None,
                        )
                    )
                    continue
                records.append(
                    DurationBankTrial(
                        attack.name,
                        bank.name,
                        trial_index,
                        cover_seed,
                        attacked.duration_seconds,
                        len(candidates),
                        selected.selected_assumed_duration_seconds,
                        selected.selected_loss_seconds,
                        selected.selected_offset_frames,
                        selected.measurement,
                        candidates,
                        None,
                    )
                )
            except Exception as error:
                records.append(
                    DurationBankTrial(
                        attack.name,
                        bank.name,
                        trial_index,
                        cover_seed,
                        None,
                        0,
                        None,
                        None,
                        None,
                        None,
                        (),
                        f"{type(error).__name__}: {error}",
                    )
                )
    return tuple(records)


def _summary(attack: AttackDefinition, bank: DurationBank, trials: tuple[DurationBankTrial, ...]) -> dict[str, object]:
    """Aggregate selected recovery and geometry choices for one attack and duration bank."""

    measurements = tuple(trial.measurement for trial in trials if trial.measurement is not None)
    rs_costs = tuple(int(measurement["rs_error_cost"]) for measurement in measurements)
    selected_losses = tuple(trial.selected_loss_seconds for trial in trials if trial.selected_loss_seconds is not None)
    return {
        "attack_name": attack.name,
        "bank_name": bank.name,
        "bank_description": bank.description,
        "trial_count": len(trials),
        "execution_failures": sum(trial.error is not None for trial in trials),
        "bank_acceptances": len(measurements),
        "exact_recoveries": sum(bool(measurement["token_matches_input"]) for measurement in measurements),
        "median_rs_cost": median(rs_costs) if rs_costs else None,
        "maximum_rs_cost": max(rs_costs) if rs_costs else None,
        "selected_loss_seconds": sorted(set(selected_losses)),
    }


def run(trial_count: int = 1) -> dict[str, object]:
    """Run the duration-bank voting experiment and return machine-readable records."""

    attacks = _attacks()
    banks = _duration_banks()
    trials = tuple(
        record
        for index in range(trial_count)
        for record in evaluate_variant(index, attacks, banks)
    )
    return {
        "goal": "test whether synchronized duration-bank runs reduce exact original-geometry requirements",
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
    """Print the complete duration-bank voting audit for archival redirection."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
