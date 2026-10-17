"""Run iteration 019: fixed-codeword registry-handle payload-versus-parity tradeoff.

Experiment goal: compare the existing 6-byte opaque token with 14
Reed--Solomon parity symbols against a 5-byte versioned registry handle with
15 parity symbols. Both configurations preserve a 20-byte protected codeword,
the schema's three framing/checksum bytes, 184 logical carrier bits, and four
physical replicas. The compact value represents an external lookup handle whose
registry must collision-check issuance and retain authenticated provenance;
this experiment does not claim that forty bits alone is collision-resistant.

Pipeline state: the five-phase median combiner is frozen after iteration 018
and is not used. Both allocations use the same blind keyed coarse scan and
deterministic one-edge crop center model on fresh cover seeds 7100-7109. The
comparison reports exact known-handle recovery, RS byte damage, alignment
feasibility, fixed carrier demand, and independent unwatermarked/wrong-secret
controls for each named crop condition.
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
from ..iteration_011_blind_attack_validation.run import AttackDefinition, _attack_definitions
from ..iteration_015_center_phase_held_out_validation.run import DeterministicCenterPhaseDecoder


@dataclass(frozen=True, slots=True)
class HandleAllocation:
    """Declare one fixed-codeword opaque-handle representation and its Reed--Solomon parity budget."""

    name: str
    payload_bytes: int
    parity_symbols: int
    registry_semantics: str
    handle_hex: str

    def handle(self) -> bytes:
        """Return the fixed opaque handle bytes used for exact transport recovery checks."""

        return bytes.fromhex(self.handle_hex)


@dataclass(frozen=True, slots=True)
class RegistryParityTrial:
    """Record one allocation/crop fresh-cover decode, RS measurement, fixed capacity, and controls."""

    allocation_name: str
    payload_bytes: int
    parity_symbols: int
    protected_codeword_bytes: int
    attack_name: str
    trial_index: int
    cover_seed: int
    virtual_timeline_offset_seconds: float
    decoder_received_oracle_map: bool
    carrier_bit_count: int | None
    physical_carrier_count: int | None
    coarse_offset_frames: int | None
    coarse_scan_accepted: bool
    deterministic_center_phase_samples: int | None
    center_phase_feasible: bool
    embedding_snr_db: float | None
    measurement: dict[str, object] | None
    unwatermarked_control_handle_match: bool | None
    wrong_secret_control_handle_match: bool | None
    error: str | None


def _profile() -> LocalPilotProfile:
    """Return the frozen contrastive four-pilot / twelve-payload carrier allocation."""

    return next(profile for profile in _profiles() if profile.name == "small_pilot_4_payload_12")


def _crop_attacks() -> tuple[AttackDefinition, ...]:
    """Return the unchanged bounded leading and trailing crop transformations."""

    crop_names = {"leading_crop_025s", "trailing_crop_025s"}
    return tuple(attack for attack in _attack_definitions() if attack.name in crop_names)


def _handle_allocations() -> tuple[HandleAllocation, ...]:
    """Return the baseline token and compact collision-checked registry-handle allocations sharing twenty bytes."""

    return (
        HandleAllocation(
            "opaque_token_6_parity_14",
            6,
            14,
            "48-bit opaque registry handle retained from the current transport candidate.",
            "0123456789ab",
        ),
        HandleAllocation(
            "versioned_registry_handle_5_parity_15",
            5,
            15,
            "40-bit versioned external registry handle with unique issuance, collision detection, and reissue.",
            "0123456789",
        ),
    )


def _known_measurement(extraction: FourFrameExtraction, handle: bytes) -> FourFrameExtraction:
    """Attach exact known-handle equality to one blind extraction for standard byte-level measurement reporting."""

    return FourFrameExtraction(
        extraction.replica_scores,
        extraction.combined_scores,
        extraction.observed_carrier_bits,
        extraction.known_bit_errors,
        extraction.carrier_erasures,
        extraction.recovery,
        extraction.recovery.token == handle,
    )


def _allocation_trials(
    allocation: HandleAllocation,
    source,
    cover_seed: int,
    timeline_offset: float,
    trial_index: int,
    attacks: tuple[AttackDefinition, ...],
) -> tuple[RegistryParityTrial, ...]:
    """Embed one allocation once and evaluate every named crop plus independent controls on a shared source cover."""

    handle = allocation.handle()
    watermark_config = AudioWatermarkConfig(
        attribution_token_bytes=allocation.payload_bytes,
        parity_symbols=allocation.parity_symbols,
    )
    pilot_config = SpectralPilotConfig(
        minimum_frequency_hz=500.0,
        maximum_frequency_hz=3800.0,
        relative_difference=0.95,
    )
    pilot = SpectralAudioPilot(b"audio-pilot-test-key", pilot_config, watermark_config)
    encoder = ContrastivePilotCalibratedExperiment(pilot, 0.01, _profile())
    decoder = DeterministicCenterPhaseDecoder(encoder)
    try:
        embedding = encoder.embed(source, handle)
        wrong_pilot = SpectralAudioPilot(b"wrong-audio-pilot-test-key", pilot_config, watermark_config)
        wrong_encoder = ContrastivePilotCalibratedExperiment(wrong_pilot, 0.01, _profile())
        wrong_decoder = DeterministicCenterPhaseDecoder(wrong_encoder)
        wrong_plan = wrong_pilot.schema.plan_attribution(handle)
    except Exception as error:
        detail = str(error) or "no message"
        return tuple(
            RegistryParityTrial(
                allocation.name, allocation.payload_bytes, allocation.parity_symbols,
                allocation.payload_bytes + allocation.parity_symbols, attack.name, trial_index, cover_seed,
                timeline_offset, False, None, None, None, False, None, False, None, None, None, None,
                f"{type(error).__name__}: {detail}",
            )
            for attack in attacks
        )
    records: list[RegistryParityTrial] = []
    carrier_bit_count = len(embedding.carrier_plan.carrier_bits)
    for attack in attacks:
        try:
            seed = 7500 + trial_index
            decoded, coarse_offset, coarse_accepted, center_phase = decoder.reconstruct(
                attack.transform(embedding.audio, seed),
                embedding.carrier_plan,
            )
            measurement = _extraction_record(encoder, embedding, _known_measurement(decoded.extraction, handle))
            unwatermarked, _, _, _ = decoder.reconstruct(attack.transform(source, seed), embedding.carrier_plan)
            wrong_secret, _, _, _ = wrong_decoder.reconstruct(attack.transform(embedding.audio, seed), wrong_plan)
        except Exception as error:
            detail = str(error) or "no message"
            records.append(
                RegistryParityTrial(
                    allocation.name, allocation.payload_bytes, allocation.parity_symbols,
                    allocation.payload_bytes + allocation.parity_symbols, attack.name, trial_index, cover_seed,
                    timeline_offset, False, carrier_bit_count, carrier_bit_count * encoder._replica_count,
                    None, False, None, False, embedding.signal_to_noise_db, None, None, None,
                    f"{type(error).__name__}: {detail}",
                )
            )
            continue
        records.append(
            RegistryParityTrial(
                allocation.name,
                allocation.payload_bytes,
                allocation.parity_symbols,
                allocation.payload_bytes + allocation.parity_symbols,
                attack.name,
                trial_index,
                cover_seed,
                timeline_offset,
                False,
                carrier_bit_count,
                carrier_bit_count * encoder._replica_count,
                coarse_offset,
                coarse_accepted,
                center_phase,
                center_phase is not None,
                embedding.signal_to_noise_db,
                measurement,
                unwatermarked.extraction.recovery.token == handle,
                wrong_secret.extraction.recovery.token == handle,
                None,
            )
        )
    return tuple(records)


def evaluate_variant(trial_index: int, attacks: Iterable[AttackDefinition]) -> tuple[RegistryParityTrial, ...]:
    """Create one fresh shared cover and evaluate both fixed-codeword allocations under each requested crop attack."""

    cover_seed = 7100 + trial_index
    timeline_offset = _trial_offset_seconds(900 + trial_index)
    source = _cover_variant(30, cover_seed, timeline_offset)
    attack_values = tuple(attacks)
    return tuple(
        record
        for allocation in _handle_allocations()
        for record in _allocation_trials(allocation, source, cover_seed, timeline_offset, trial_index, attack_values)
    )


def _summary(
    allocation: HandleAllocation,
    attack: AttackDefinition,
    trials: tuple[RegistryParityTrial, ...],
) -> dict[str, object]:
    """Aggregate fixed-codeword capacity, blind alignment, exact recovery, RS damage, and controls by allocation/crop."""

    measurements = tuple(trial.measurement for trial in trials if trial.measurement is not None)
    feasible = tuple(trial for trial in trials if trial.center_phase_feasible)
    carrier_counts = tuple(trial.carrier_bit_count for trial in trials if trial.carrier_bit_count is not None)
    physical_counts = tuple(trial.physical_carrier_count for trial in trials if trial.physical_carrier_count is not None)
    return {
        "allocation_name": allocation.name,
        "payload_bytes": allocation.payload_bytes,
        "parity_symbols": allocation.parity_symbols,
        "protected_codeword_bytes": allocation.payload_bytes + allocation.parity_symbols,
        "attack_name": attack.name,
        "trial_count": len(trials),
        "execution_failures": sum(trial.error is not None for trial in trials),
        "carrier_bit_count": carrier_counts[0] if carrier_counts and len(set(carrier_counts)) == 1 else None,
        "physical_carrier_count": physical_counts[0] if physical_counts and len(set(physical_counts)) == 1 else None,
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
    """Run fresh fixed-codeword registry-handle parity comparison without changing the alignment or carrier plan."""

    allocations = _handle_allocations()
    attacks = _crop_attacks()
    trials = tuple(record for trial_index in range(10) for record in evaluate_variant(trial_index, attacks))
    return {
        "fixture": "ten fresh seeded 30-second synthetic music-like covers and unchanged 250 ms crop attacks",
        "mapping_mode": "blind_non_oracle_fixed_codeword_registry_handle_parity_tradeoff",
        "decoder_received_oracle_map": False,
        "alignment_policy": "blind_coarse_scan_plus_deterministic_center_phase",
        "registry_model": "Compact handles require unique external issuance, collision checks, reissue, retained provenance, and authentication.",
        "allocations": [asdict(allocation) for allocation in allocations],
        "framing_overhead_bytes": 3,
        "carrier_band_hz": [500.0, 3800.0],
        "relative_difference": 0.95,
        "validation_cover_seeds": list(range(7100, 7110)),
        "summaries": [
            _summary(
                allocation,
                attack,
                tuple(
                    trial
                    for trial in trials
                    if trial.allocation_name == allocation.name and trial.attack_name == attack.name
                ),
            )
            for allocation in allocations
            for attack in attacks
        ],
        "trials": [asdict(trial) for trial in trials],
    }


def main() -> None:
    """Print the complete reproducible fixed-codeword registry-handle parity tradeoff as formatted JSON."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
