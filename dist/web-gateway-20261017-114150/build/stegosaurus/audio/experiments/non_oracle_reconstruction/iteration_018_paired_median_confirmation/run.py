"""Run iteration 018: paired fresh-seed confirmation of fixed median payload combining.

Experiment goal: resolve iteration 017's missing same-seed baseline. Every
fresh watermarked crop is decoded twice under unchanged conditions: once with
the deterministic center phase alone and once with the predeclared five-phase
median payload combiner. Both strategies run the same secret-pilot coarse
synchronization and deterministic center model; their paired outcomes isolate
payload aggregation after synchronization rather than comparing independent
seed sets or retuned strategies.

Pipeline state: no phase rank, telemetry label, payload outcome, carrier map,
or new threshold affects decoding. The source fixture is fresh seeds 7000-7009
and all controls remain independently decoded under each strategy. The primary
analysis stratifies by shared center feasibility because neither combiner can
repair a coarse synchronization rejection or incompatible center model.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
import json
from statistics import median

from ....pilot import SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioWatermarkConfig
from ...transport_optimization.iteration_004_four_frame_soft_combine.run import (
    FourFrameExtraction,
    _extraction_record,
)
from ...transport_optimization.iteration_006_duration_stability_bounds.run import (
    _cover_variant,
    _trial_offset_seconds,
)
from ..iteration_002_local_selection_pilot.run import LocalPilotProfile, _profiles
from ..iteration_005_contrastive_pilot_calibration.run import ContrastivePilotCalibratedExperiment
from ..iteration_010_constant_codeword_allocation.run import CodewordAllocation, _allocations
from ..iteration_011_blind_attack_validation.run import AttackDefinition, _attack_definitions
from ..iteration_016_center_neighborhood_soft_combine.run import (
    CenterNeighborhoodDecoder,
    CombinationStrategy,
    _strategies,
)


@dataclass(frozen=True, slots=True)
class PairedStrategyTrial:
    """Record one strategy's outcome on a fresh crop input shared with its paired comparison strategy."""

    attack_name: str
    strategy_name: str
    phase_offsets_samples: tuple[int, ...]
    aggregation: str
    trial_index: int
    cover_seed: int
    virtual_timeline_offset_seconds: float
    decoder_received_oracle_map: bool
    coarse_offset_frames: int | None
    coarse_scan_accepted: bool
    deterministic_center_phase_samples: int | None
    center_phase_feasible: bool
    embedding_snr_db: float | None
    measurement: dict[str, object] | None
    unwatermarked_control_handle_match: bool | None
    wrong_secret_control_handle_match: bool | None
    error: str | None


@dataclass(frozen=True, slots=True)
class PairedOutcome:
    """Record one same-input center-versus-median transition and byte-level cost delta for a crop trial."""

    attack_name: str
    trial_index: int
    cover_seed: int
    shared_center_feasible: bool
    center_only_recovered: bool | None
    median_recovered: bool | None
    center_only_rs_cost: int | None
    median_rs_cost: int | None
    median_minus_center_rs_cost: int | None


def _selected_allocation() -> CodewordAllocation:
    """Return the unchanged six-byte opaque handle and fourteen-parity allocation."""

    return next(allocation for allocation in _allocations() if allocation.name == "registry_handle_6_parity_14")


def _profile() -> LocalPilotProfile:
    """Return the frozen contrastive four-pilot / twelve-payload allocation."""

    return next(profile for profile in _profiles() if profile.name == "small_pilot_4_payload_12")


def _crop_attacks() -> tuple[AttackDefinition, ...]:
    """Return the unchanged bounded leading and trailing crop transformations."""

    crop_names = {"leading_crop_025s", "trailing_crop_025s"}
    return tuple(attack for attack in _attack_definitions() if attack.name in crop_names)


def _known_measurement(extraction: FourFrameExtraction, token: bytes) -> FourFrameExtraction:
    """Attach exact known-token equality to one strategy extraction for shared byte-level reporting."""

    return FourFrameExtraction(
        extraction.replica_scores,
        extraction.combined_scores,
        extraction.observed_carrier_bits,
        extraction.known_bit_errors,
        extraction.carrier_erasures,
        extraction.recovery,
        extraction.recovery.token == token,
    )


def evaluate_variant(trial_index: int, attacks: Iterable[AttackDefinition]) -> tuple[PairedStrategyTrial, ...]:
    """Embed one fresh cover and decode each unchanged crop and controls under both predeclared strategies."""

    allocation = _selected_allocation()
    token = allocation.token()
    cover_seed = 7000 + trial_index
    timeline_offset = _trial_offset_seconds(800 + trial_index)
    source = _cover_variant(30, cover_seed, timeline_offset)
    watermark_config = AudioWatermarkConfig(
        attribution_token_bytes=allocation.payload_bytes,
        parity_symbols=allocation.parity_symbols,
    )
    pilot_config = SpectralPilotConfig(
        minimum_frequency_hz=500.0,
        maximum_frequency_hz=3800.0,
        relative_difference=0.95,
    )
    attack_values = tuple(attacks)
    strategies = _strategies()
    pilot = SpectralAudioPilot(b"audio-pilot-test-key", pilot_config, watermark_config)
    encoder = ContrastivePilotCalibratedExperiment(pilot, 0.01, _profile())
    decoder = CenterNeighborhoodDecoder(encoder)
    try:
        embedding = encoder.embed(source, token)
        wrong_pilot = SpectralAudioPilot(b"wrong-audio-pilot-test-key", pilot_config, watermark_config)
        wrong_encoder = ContrastivePilotCalibratedExperiment(wrong_pilot, 0.01, _profile())
        wrong_decoder = CenterNeighborhoodDecoder(wrong_encoder)
        wrong_plan = wrong_pilot.schema.plan_attribution(token)
    except Exception as error:
        detail = str(error) or "no message"
        return tuple(
            PairedStrategyTrial(
                attack.name, strategy.name, strategy.phase_offsets_samples, strategy.aggregation, trial_index,
                cover_seed, timeline_offset, False, None, False, None, False, None, None, None, None,
                f"{type(error).__name__}: {detail}",
            )
            for attack in attack_values
            for strategy in strategies
        )
    records: list[PairedStrategyTrial] = []
    for attack in attack_values:
        seed = 7400 + trial_index
        attacked_audio = attack.transform(embedding.audio, seed)
        unwatermarked_audio = attack.transform(source, seed)
        wrong_secret_audio = attack.transform(embedding.audio, seed)
        for strategy in strategies:
            try:
                decoded = decoder.decode(attacked_audio, embedding.carrier_plan, strategy)
                measurement = _extraction_record(encoder, embedding, _known_measurement(decoded.extraction, token))
                unwatermarked = decoder.decode(unwatermarked_audio, embedding.carrier_plan, strategy)
                wrong_secret = wrong_decoder.decode(wrong_secret_audio, wrong_plan, strategy)
            except Exception as error:
                detail = str(error) or "no message"
                records.append(
                    PairedStrategyTrial(
                        attack.name, strategy.name, strategy.phase_offsets_samples, strategy.aggregation, trial_index,
                        cover_seed, timeline_offset, False, None, False, None, False, embedding.signal_to_noise_db,
                        None, None, None, f"{type(error).__name__}: {detail}",
                    )
                )
                continue
            records.append(
                PairedStrategyTrial(
                    attack.name,
                    strategy.name,
                    strategy.phase_offsets_samples,
                    strategy.aggregation,
                    trial_index,
                    cover_seed,
                    timeline_offset,
                    False,
                    decoded.coarse_offset_frames,
                    decoded.coarse_scan_accepted,
                    decoded.deterministic_center_phase_samples,
                    decoded.center_phase_feasible,
                    embedding.signal_to_noise_db,
                    measurement,
                    unwatermarked.extraction.recovery.token == token,
                    wrong_secret.extraction.recovery.token == token,
                    None,
                )
            )
    return tuple(records)


def _paired_outcomes(records: tuple[PairedStrategyTrial, ...]) -> tuple[PairedOutcome, ...]:
    """Join strategy records by shared attack and trial to calculate recovery transitions and RS-cost deltas."""

    grouped: dict[tuple[str, int], dict[str, PairedStrategyTrial]] = {}
    for record in records:
        grouped.setdefault((record.attack_name, record.trial_index), {})[record.strategy_name] = record
    outcomes: list[PairedOutcome] = []
    for (attack_name, trial_index), strategies in sorted(grouped.items()):
        center = strategies.get("center_only")
        median_strategy = strategies.get("median_neighborhood_5")
        if center is None or median_strategy is None:
            continue
        center_measurement = center.measurement
        median_measurement = median_strategy.measurement
        center_cost = int(center_measurement["rs_error_cost"]) if center_measurement is not None else None
        median_cost = int(median_measurement["rs_error_cost"]) if median_measurement is not None else None
        outcomes.append(
            PairedOutcome(
                attack_name,
                trial_index,
                center.cover_seed,
                center.center_phase_feasible and median_strategy.center_phase_feasible,
                bool(center_measurement and center_measurement["token_matches_input"]),
                bool(median_measurement and median_measurement["token_matches_input"]),
                center_cost,
                median_cost,
                median_cost - center_cost if center_cost is not None and median_cost is not None else None,
            )
        )
    return tuple(outcomes)


def _strategy_summary(
    attack: AttackDefinition,
    strategy: CombinationStrategy,
    trials: tuple[PairedStrategyTrial, ...],
) -> dict[str, object]:
    """Aggregate one strategy's recovery, alignment feasibility, RS damage, and controls for one crop direction."""

    measurements = tuple(trial.measurement for trial in trials if trial.measurement is not None)
    feasible = tuple(trial for trial in trials if trial.center_phase_feasible)
    return {
        "attack_name": attack.name,
        "strategy_name": strategy.name,
        "phase_offsets_samples": list(strategy.phase_offsets_samples),
        "aggregation": strategy.aggregation,
        "trial_count": len(trials),
        "execution_failures": sum(trial.error is not None for trial in trials),
        "coarse_scan_acceptances": sum(trial.coarse_scan_accepted for trial in trials),
        "deterministic_center_feasible": len(feasible),
        "exact_recoveries": sum(bool(measurement["token_matches_input"]) for measurement in measurements),
        "conditional_center_phase_recoveries": sum(
            bool(trial.measurement and trial.measurement["token_matches_input"])
            for trial in feasible
        ),
        "median_rs_cost": median(int(measurement["rs_error_cost"]) for measurement in measurements) if measurements else None,
        "maximum_rs_cost": max(int(measurement["rs_error_cost"]) for measurement in measurements) if measurements else None,
        "unwatermarked_control_false_accepts": sum(bool(trial.unwatermarked_control_handle_match) for trial in trials),
        "wrong_secret_control_false_accepts": sum(bool(trial.wrong_secret_control_handle_match) for trial in trials),
    }


def _paired_summary(attack: AttackDefinition, outcomes: tuple[PairedOutcome, ...]) -> dict[str, object]:
    """Aggregate same-input recovery transitions and RS-cost deltas for shared center-feasible paths only."""

    shared = tuple(outcome for outcome in outcomes if outcome.shared_center_feasible)
    deltas = tuple(outcome.median_minus_center_rs_cost for outcome in shared if outcome.median_minus_center_rs_cost is not None)
    return {
        "attack_name": attack.name,
        "paired_trial_count": len(outcomes),
        "shared_center_feasible_trials": len(shared),
        "both_recovered": sum(outcome.center_only_recovered and outcome.median_recovered for outcome in shared),
        "median_only_recovered": sum(not outcome.center_only_recovered and outcome.median_recovered for outcome in shared),
        "center_only_recovered": sum(outcome.center_only_recovered and not outcome.median_recovered for outcome in shared),
        "both_failed": sum(not outcome.center_only_recovered and not outcome.median_recovered for outcome in shared),
        "median_rs_cost_delta_median": median(deltas) if deltas else None,
        "median_rs_cost_delta_minimum": min(deltas) if deltas else None,
        "median_rs_cost_delta_maximum": max(deltas) if deltas else None,
    }


def run() -> dict[str, object]:
    """Run paired fresh-seed center-only versus fixed-median confirmation with shared-feasibility analysis."""

    attacks = _crop_attacks()
    strategies = _strategies()
    records = tuple(record for trial_index in range(10) for record in evaluate_variant(trial_index, attacks))
    outcomes = _paired_outcomes(records)
    allocation = _selected_allocation()
    return {
        "fixture": "ten fresh seeded 30-second synthetic music-like covers and unchanged 250 ms crop attacks",
        "mapping_mode": "blind_non_oracle_paired_center_vs_fixed_median",
        "decoder_received_oracle_map": False,
        "phase_selection": "deterministic_model_center_with_fixed_offsets",
        "allocation": asdict(allocation),
        "protected_codeword_bytes": allocation.payload_bytes + allocation.parity_symbols,
        "carrier_bit_count": 184,
        "physical_carrier_count": 736,
        "profile": asdict(_profile()),
        "validation_cover_seeds": list(range(7000, 7010)),
        "strategies": [asdict(strategy) for strategy in strategies],
        "strategy_summaries": [
            _strategy_summary(
                attack,
                strategy,
                tuple(
                    record
                    for record in records
                    if record.attack_name == attack.name and record.strategy_name == strategy.name
                ),
            )
            for attack in attacks
            for strategy in strategies
        ],
        "paired_summaries": [
            _paired_summary(attack, tuple(outcome for outcome in outcomes if outcome.attack_name == attack.name))
            for attack in attacks
        ],
        "trials": [asdict(record) for record in records],
        "paired_outcomes": [asdict(outcome) for outcome in outcomes],
    }


def main() -> None:
    """Print the complete reproducible paired median confirmation as formatted JSON."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
