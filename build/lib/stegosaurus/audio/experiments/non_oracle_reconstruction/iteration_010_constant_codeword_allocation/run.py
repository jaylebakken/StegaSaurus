"""Run iteration 010: constant-codeword payload-versus-parity allocation.

Experiment goal: measure whether reducing a registry-backed opaque identifier
from eight to seven or six bytes can reallocate bytes from non-parity payload
to Reed--Solomon parity without increasing the audio transport plan. All three
configurations hold the protected codeword at twenty bytes: 8 payload + 12
parity, 7 payload + 13 parity, and 6 payload + 14 parity. The schema's
three-byte framing/checksum overhead consequently preserves 184 framed bits
and four-replica 736 physical carrier placements for every allocation.

Pipeline state: iteration 009 showed that adding parity by lengthening an
eight-byte payload plan to 14 or 16 parity symbols increased carrier demand
and did not improve recovery on the bounded fixture. This study keeps the
contrastive 4-pilot / 12-payload encoder, 500--3800 Hz carrier band, 0.95
relative difference, and frozen blind thresholds (expected pilot >= 0.00;
best-minus-rival pilot gap >= 0.24) unchanged while measuring the alternative
allocation directly. Shorter values represent versioned registry handles, not
reconstructible identity data or unqualified truncated hashes.
"""

from __future__ import annotations

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
from ..iteration_002_local_selection_pilot.run import (
    LocalPilotProfile,
    _control_token_match,
    _map_metrics,
    _profiles,
)
from ..iteration_005_contrastive_pilot_calibration.run import ContrastivePilotCalibratedExperiment
from ..iteration_006_pilot_threshold_sweep.run import (
    PilotThresholds,
    ThresholdedLocalPilotDecoder,
)


@dataclass(frozen=True, slots=True)
class CodewordAllocation:
    """Declare one fixed-length protected codeword allocation and handle representation."""

    name: str
    payload_bytes: int
    parity_symbols: int
    registry_handle_hex: str

    def token(self) -> bytes:
        """Return the fixed-length opaque registry handle used for exact recovery checks."""

        return bytes.fromhex(self.registry_handle_hex)


@dataclass(frozen=True, slots=True)
class ConstantCodewordTrial:
    """Record one blind allocation trial, map diagnostics, recovery measurement, and controls."""

    allocation_name: str
    payload_bytes: int
    parity_symbols: int
    protected_codeword_bytes: int
    trial_index: int
    cover_seed: int
    virtual_timeline_offset_seconds: float
    carrier_bit_count: int | None
    physical_carrier_count: int | None
    embedding_snr_db: float | None
    map_metrics: dict[str, object] | None
    measurement: dict[str, object] | None
    unwatermarked_control_handle_match: bool | None
    wrong_secret_control_handle_match: bool | None
    error: str | None


def _profile() -> LocalPilotProfile:
    """Return the contrastive four-pilot / twelve-payload allocation frozen before this study."""

    return next(profile for profile in _profiles() if profile.name == "small_pilot_4_payload_12")


def _threshold_policy() -> PilotThresholds:
    """Return the pre-registered blind pilot policy selected in iteration 007 and validated in 008."""

    return PilotThresholds(0.0, 0.24)


def _allocations() -> tuple[CodewordAllocation, ...]:
    """Return compact opaque-handle allocations sharing one twenty-byte RS codeword length."""

    return (
        CodewordAllocation("opaque_token_8_parity_12", 8, 12, "0123456789abcdef"),
        CodewordAllocation("registry_handle_7_parity_13", 7, 13, "0123456789abcd"),
        CodewordAllocation("registry_handle_6_parity_14", 6, 14, "0123456789ab"),
    )


def evaluate_trial(allocation: CodewordAllocation, trial_index: int) -> ConstantCodewordTrial:
    """Blindly encode and decode one fresh cover under a fixed-length codeword allocation."""

    token = allocation.token()
    cover_seed = 6500 + trial_index
    timeline_offset = _trial_offset_seconds(300 + trial_index)
    source = _cover_variant(30, cover_seed, timeline_offset)
    config = SpectralPilotConfig(
        minimum_frequency_hz=500.0,
        maximum_frequency_hz=3800.0,
        relative_difference=0.95,
    )
    watermark_config = AudioWatermarkConfig(
        attribution_token_bytes=allocation.payload_bytes,
        parity_symbols=allocation.parity_symbols,
    )
    profile = _profile()
    policy = _threshold_policy()
    pilot = SpectralAudioPilot(b"audio-pilot-test-key", config, watermark_config)
    encoder = ContrastivePilotCalibratedExperiment(pilot, 0.01, profile)
    decoder = ThresholdedLocalPilotDecoder(encoder, 0.01, policy)
    try:
        embedding = encoder.embed(source, token)
        reconstruction = decoder.reconstruct(embedding.audio, embedding.carrier_plan)
        extraction = reconstruction.extraction
        measured_extraction = FourFrameExtraction(
            extraction.replica_scores,
            extraction.combined_scores,
            extraction.observed_carrier_bits,
            extraction.known_bit_errors,
            extraction.carrier_erasures,
            extraction.recovery,
            extraction.recovery.token == token,
        )
        measurement = _extraction_record(encoder, embedding, measured_extraction)
        unwatermarked = decoder.reconstruct(source, embedding.carrier_plan)
        wrong_pilot = SpectralAudioPilot(b"wrong-audio-pilot-test-key", config, watermark_config)
        wrong_encoder = ContrastivePilotCalibratedExperiment(wrong_pilot, 0.01, profile)
        wrong_decoder = ThresholdedLocalPilotDecoder(wrong_encoder, 0.01, policy)
        wrong_secret = wrong_decoder.reconstruct(embedding.audio, wrong_pilot.schema.plan_attribution(token))
    except Exception as error:
        detail = str(error) or "no message"
        return ConstantCodewordTrial(
            allocation.name,
            allocation.payload_bytes,
            allocation.parity_symbols,
            allocation.payload_bytes + allocation.parity_symbols,
            trial_index,
            cover_seed,
            timeline_offset,
            None,
            None,
            None,
            None,
            None,
            None,
            None,
            f"{type(error).__name__}: {detail}",
        )
    carrier_bit_count = len(embedding.carrier_plan.carrier_bits)
    return ConstantCodewordTrial(
        allocation.name,
        allocation.payload_bytes,
        allocation.parity_symbols,
        allocation.payload_bytes + allocation.parity_symbols,
        trial_index,
        cover_seed,
        timeline_offset,
        carrier_bit_count,
        carrier_bit_count * encoder._replica_count,
        embedding.signal_to_noise_db,
        _map_metrics(reconstruction, embedding),
        measurement,
        _control_token_match(unwatermarked, token),
        _control_token_match(wrong_secret, token),
        None,
    )


def _summary(allocation: CodewordAllocation, trials: tuple[ConstantCodewordTrial, ...]) -> dict[str, object]:
    """Aggregate recovery, capacity, map, RS, SNR, and negative-control outcomes by allocation."""

    successful = tuple(trial for trial in trials if trial.measurement is not None and trial.map_metrics is not None)
    measurements = tuple(trial.measurement for trial in successful if trial.measurement is not None)
    map_metrics = tuple(trial.map_metrics for trial in successful if trial.map_metrics is not None)
    carrier_counts = tuple(trial.carrier_bit_count for trial in successful if trial.carrier_bit_count is not None)
    physical_counts = tuple(trial.physical_carrier_count for trial in successful if trial.physical_carrier_count is not None)
    snr_values = tuple(trial.embedding_snr_db for trial in successful if trial.embedding_snr_db is not None)
    selected_accuracy = tuple(
        float(metric["selected_map_accuracy"])
        for metric in map_metrics
        if metric["selected_map_accuracy"] is not None
    )
    return {
        "allocation_name": allocation.name,
        "payload_bytes": allocation.payload_bytes,
        "parity_symbols": allocation.parity_symbols,
        "protected_codeword_bytes": allocation.payload_bytes + allocation.parity_symbols,
        "trial_count": len(trials),
        "execution_failures": sum(trial.error is not None for trial in trials),
        "carrier_bit_count": carrier_counts[0] if carrier_counts and len(set(carrier_counts)) == 1 else None,
        "physical_carrier_count": physical_counts[0] if physical_counts and len(set(physical_counts)) == 1 else None,
        "exact_recoveries": sum(bool(measurement["token_matches_input"]) for measurement in measurements),
        "median_rs_cost": median(int(measurement["rs_error_cost"]) for measurement in measurements) if measurements else None,
        "maximum_rs_cost": max(int(measurement["rs_error_cost"]) for measurement in measurements) if measurements else None,
        "median_known_bit_errors": median(int(measurement["known_bit_errors"]) for measurement in measurements) if measurements else None,
        "median_carrier_erasures": median(int(measurement["carrier_erasures"]) for measurement in measurements) if measurements else None,
        "median_unknown_byte_errors": median(int(measurement["unknown_byte_errors"]) for measurement in measurements) if measurements else None,
        "median_byte_erasures": median(int(measurement["byte_erasures"]) for measurement in measurements) if measurements else None,
        "median_selected_map_accuracy": median(selected_accuracy) if selected_accuracy else None,
        "median_selection_erasure_rate": median(float(metric["selection_erasure_rate"]) for metric in map_metrics) if map_metrics else None,
        "median_embedding_snr_db": median(snr_values) if snr_values else None,
        "unwatermarked_control_false_accepts": sum(bool(trial.unwatermarked_control_handle_match) for trial in successful),
        "wrong_secret_control_false_accepts": sum(bool(trial.wrong_secret_control_handle_match) for trial in successful),
    }


def run() -> dict[str, object]:
    """Run the fresh blind constant-codeword allocation study for all declared handle sizes."""

    allocations = _allocations()
    trials = tuple(
        trial
        for allocation in allocations
        for trial_index in range(10)
        for trial in (evaluate_trial(allocation, trial_index),)
    )
    summaries = tuple(
        _summary(
            allocation,
            tuple(trial for trial in trials if trial.allocation_name == allocation.name),
        )
        for allocation in allocations
    )
    return {
        "fixture": "ten fresh seeded 30-second music-like cover variants and virtual timeline offsets",
        "mapping_mode": "blind_non_oracle_constant_codeword_allocation",
        "decoder_received_oracle_map": False,
        "profile": asdict(_profile()),
        "frozen_policy": asdict(_threshold_policy()) | {"name": _threshold_policy().name},
        "allocations": [asdict(allocation) for allocation in allocations],
        "validation_cover_seeds": list(range(6500, 6510)),
        "carrier_band_hz": [500.0, 3800.0],
        "relative_difference": 0.95,
        "framing_overhead_bytes": 3,
        "repetition": 4,
        "handle_semantics": "Shortened payloads are versioned registry handles; a registry retains full provenance and handles collisions and authentication.",
        "summaries": list(summaries),
        "trials": [asdict(trial) for trial in trials],
    }


def main() -> None:
    """Print the complete reproducible constant-codeword allocation study as formatted JSON."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
