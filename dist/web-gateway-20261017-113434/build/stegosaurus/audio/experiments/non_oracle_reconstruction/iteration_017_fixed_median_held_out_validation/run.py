"""Run iteration 017: fresh validation of the fixed five-phase median combiner.

Experiment goal: validate the exact median-neighborhood strategy recorded in
iteration 016, with no optimization or parameter selection in this runner.
The decoder retains the blind keyed coarse offset scan and deterministic
single-edge-crop center model. It then evaluates the fixed phase offsets
(-8, -4, 0, +4, +8), takes their per-physical-carrier median payload score,
and applies the existing four-replica and Reed--Solomon extraction path.

Pipeline state: all transport, pilot, frequency, crop, and control settings
are unchanged. The covers use disjoint seeds `6900-6909`; no telemetry labels,
pilot phase ranks, payload outcomes, encoder frame maps, or fresh tuning are
inputs to the decoder. The purpose is confirmation or rejection of one fully
specified strategy on new synthetic variants.
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
class FixedMedianTrial:
    """Record one new crop decode under the predeclared median strategy, RS measurement, and controls."""

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


def _selected_allocation() -> CodewordAllocation:
    """Return the unchanged six-byte handle plus fourteen-parity allocation."""

    return next(allocation for allocation in _allocations() if allocation.name == "registry_handle_6_parity_14")


def _profile() -> LocalPilotProfile:
    """Return the frozen four-pilot / twelve-payload carrier allocation."""

    return next(profile for profile in _profiles() if profile.name == "small_pilot_4_payload_12")


def _crop_attacks() -> tuple[AttackDefinition, ...]:
    """Return the unchanged bounded leading and trailing crop transformations."""

    crop_names = {"leading_crop_025s", "trailing_crop_025s"}
    return tuple(attack for attack in _attack_definitions() if attack.name in crop_names)


def _fixed_strategy() -> CombinationStrategy:
    """Return iteration 016's predeclared five-phase median strategy without modification."""

    return next(strategy for strategy in _strategies() if strategy.name == "median_neighborhood_5")


def _known_measurement(extraction: FourFrameExtraction, token: bytes) -> FourFrameExtraction:
    """Attach known-token equality to the fixed strategy extraction for standard byte-level reporting."""

    return FourFrameExtraction(
        extraction.replica_scores,
        extraction.combined_scores,
        extraction.observed_carrier_bits,
        extraction.known_bit_errors,
        extraction.carrier_erasures,
        extraction.recovery,
        extraction.recovery.token == token,
    )


def evaluate_variant(trial_index: int, attacks: Iterable[AttackDefinition]) -> tuple[FixedMedianTrial, ...]:
    """Embed one new cover and decode each unchanged crop plus controls with the fixed median strategy only."""

    allocation = _selected_allocation()
    strategy = _fixed_strategy()
    token = allocation.token()
    cover_seed = 6900 + trial_index
    timeline_offset = _trial_offset_seconds(700 + trial_index)
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
            FixedMedianTrial(
                attack.name, strategy.name, strategy.phase_offsets_samples, strategy.aggregation, trial_index,
                cover_seed, timeline_offset, False, None, False, None, False, None, None, None, None,
                f"{type(error).__name__}: {detail}",
            )
            for attack in attack_values
        )
    records: list[FixedMedianTrial] = []
    for attack in attack_values:
        try:
            seed = 7300 + trial_index
            decoded = decoder.decode(attack.transform(embedding.audio, seed), embedding.carrier_plan, strategy)
            measurement = _extraction_record(encoder, embedding, _known_measurement(decoded.extraction, token))
            unwatermarked = decoder.decode(attack.transform(source, seed), embedding.carrier_plan, strategy)
            wrong_secret = wrong_decoder.decode(attack.transform(embedding.audio, seed), wrong_plan, strategy)
        except Exception as error:
            detail = str(error) or "no message"
            records.append(
                FixedMedianTrial(
                    attack.name, strategy.name, strategy.phase_offsets_samples, strategy.aggregation, trial_index,
                    cover_seed, timeline_offset, False, None, False, None, False, embedding.signal_to_noise_db,
                    None, None, None, f"{type(error).__name__}: {detail}",
                )
            )
            continue
        records.append(
            FixedMedianTrial(
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


def _summary(attack: AttackDefinition, trials: tuple[FixedMedianTrial, ...]) -> dict[str, object]:
    """Aggregate fixed-strategy recovery, coarse/center feasibility, RS damage, and controls for one crop direction."""

    measurements = tuple(trial.measurement for trial in trials if trial.measurement is not None)
    feasible = tuple(trial for trial in trials if trial.center_phase_feasible)
    return {
        "attack_name": attack.name,
        "strategy_name": _fixed_strategy().name,
        "phase_offsets_samples": list(_fixed_strategy().phase_offsets_samples),
        "aggregation": _fixed_strategy().aggregation,
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
        "median_carrier_erasures": median(int(measurement["carrier_erasures"]) for measurement in measurements) if measurements else None,
        "unwatermarked_control_false_accepts": sum(bool(trial.unwatermarked_control_handle_match) for trial in trials),
        "wrong_secret_control_false_accepts": sum(bool(trial.wrong_secret_control_handle_match) for trial in trials),
    }


def run() -> dict[str, object]:
    """Run fresh-cover validation of the one predeclared median neighborhood strategy without optimization."""

    attacks = _crop_attacks()
    strategy = _fixed_strategy()
    trials = tuple(record for trial_index in range(10) for record in evaluate_variant(trial_index, attacks))
    allocation = _selected_allocation()
    return {
        "fixture": "ten fresh seeded 30-second synthetic music-like covers and unchanged 250 ms crop attacks",
        "mapping_mode": "blind_non_oracle_fixed_median_neighborhood_validation",
        "decoder_received_oracle_map": False,
        "strategy": asdict(strategy),
        "phase_selection": "deterministic_model_center_with_fixed_offsets",
        "allocation": asdict(allocation),
        "protected_codeword_bytes": allocation.payload_bytes + allocation.parity_symbols,
        "carrier_bit_count": 184,
        "physical_carrier_count": 736,
        "profile": asdict(_profile()),
        "validation_cover_seeds": list(range(6900, 6910)),
        "summaries": [
            _summary(attack, tuple(trial for trial in trials if trial.attack_name == attack.name))
            for attack in attacks
        ],
        "trials": [asdict(trial) for trial in trials],
    }


def main() -> None:
    """Print the complete reproducible fixed-median held-out validation as formatted JSON."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
