"""Run iteration 008: held-out contrastive local-pilot gap-policy validation.

Experiment goal: validate a frozen decoder policy on variants not used for
iteration 007's exploratory score telemetry. The calibration replay evaluated a
declared wider grid of absolute-pilot thresholds ``0.00`` through ``0.40`` and
pilot-gap thresholds ``0.08`` through ``1.00`` using the iteration 007 tables.
It selected absolute threshold ``0.00`` and gap threshold ``0.24`` by maximum
exact recovery, then minimum median RS cost. This script does not revisit that
selection; it applies the fixed policy blindly to ten fresh cover seeds.

Pipeline state: iteration 004 proves the split-pair payload channel recovers
with an exact map. Iteration 007 establishes that pilot gaps distinguish many
correct and wrong map choices, but threshold selection was exploratory. This
experiment is the first held-out check of the frozen gap-focused policy. Oracle
maps and known tokens remain post-hoc diagnostics, never decoder inputs.
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
class HeldOutValidationTrial:
    """Record one fresh blind-policy validation result plus post-hoc map and control diagnostics."""

    trial_index: int
    cover_seed: int
    virtual_timeline_offset_seconds: float
    embedding_snr_db: float | None
    map_metrics: dict[str, object] | None
    measurement: dict[str, object] | None
    unwatermarked_control_token_match: bool | None
    wrong_secret_control_token_match: bool | None
    error: str | None


def _profile() -> LocalPilotProfile:
    """Return the leading contrastive 4-pilot / 12-payload allocation fixed for held-out validation."""

    return next(profile for profile in _profiles() if profile.name == "small_pilot_4_payload_12")


def _threshold_policy() -> PilotThresholds:
    """Return the threshold policy frozen from iteration 007 telemetry before held-out evaluation."""

    return PilotThresholds(0.0, 0.24)


def evaluate_trial(trial_index: int) -> HeldOutValidationTrial:
    """Blindly decode one fresh cover under the frozen policy and record oracle diagnostics afterward."""

    token = bytes.fromhex("0123456789abcdef")
    cover_seed = 6300 + trial_index
    timeline_offset = _trial_offset_seconds(100 + trial_index)
    source = _cover_variant(30, cover_seed, timeline_offset)
    config = SpectralPilotConfig(
        minimum_frequency_hz=500.0,
        maximum_frequency_hz=3800.0,
        relative_difference=0.95,
    )
    watermark_config = AudioWatermarkConfig(parity_symbols=12)
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
        return HeldOutValidationTrial(
            trial_index,
            cover_seed,
            timeline_offset,
            None,
            None,
            None,
            None,
            None,
            f"{type(error).__name__}: {detail}",
        )
    return HeldOutValidationTrial(
        trial_index,
        cover_seed,
        timeline_offset,
        embedding.signal_to_noise_db,
        _map_metrics(reconstruction, embedding),
        measurement,
        _control_token_match(unwatermarked, token),
        _control_token_match(wrong_secret, token),
        None,
    )


def run() -> dict[str, object]:
    """Run the frozen held-out local-pilot policy over ten fresh clean synthetic cover variants."""

    policy = _threshold_policy()
    trials = tuple(evaluate_trial(trial_index) for trial_index in range(10))
    successful = tuple(trial for trial in trials if trial.measurement is not None and trial.map_metrics is not None)
    measurements = tuple(trial.measurement for trial in successful if trial.measurement is not None)
    map_metrics = tuple(trial.map_metrics for trial in successful if trial.map_metrics is not None)
    selected_accuracy = tuple(
        float(metric["selected_map_accuracy"])
        for metric in map_metrics
        if metric["selected_map_accuracy"] is not None
    )
    snr_values = tuple(trial.embedding_snr_db for trial in successful if trial.embedding_snr_db is not None)
    return {
        "fixture": "ten fresh seeded 30-second music-like cover variants and virtual timeline offsets",
        "mapping_mode": "blind_non_oracle_held_out_gap_policy_validation",
        "decoder_received_oracle_map": False,
        "profile": asdict(_profile()),
        "frozen_policy": asdict(policy) | {"name": policy.name},
        "policy_selection": {
            "calibration_source": "iteration_007_pilot_score_telemetry",
            "calibration_cover_seeds": list(range(6100, 6110)),
            "replayed_absolute_thresholds": [0.0, 0.1, 0.2, 0.3, 0.4],
            "replayed_gap_thresholds": [0.08, 0.12, 0.16, 0.24, 0.32, 0.48, 0.64, 0.8, 1.0],
            "selection_rule": "maximum exact recovery, then minimum median RS cost",
        },
        "validation_cover_seeds": [trial.cover_seed for trial in trials],
        "carrier_band_hz": [500.0, 3800.0],
        "relative_difference": 0.95,
        "parity_symbols": 12,
        "repetition": 4,
        "trial_count": len(trials),
        "execution_failures": sum(trial.error is not None for trial in trials),
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
        "unwatermarked_control_false_accepts": sum(bool(trial.unwatermarked_control_token_match) for trial in successful),
        "wrong_secret_control_false_accepts": sum(bool(trial.wrong_secret_control_token_match) for trial in successful),
        "trials": [asdict(trial) for trial in trials],
    }


def main() -> None:
    """Print the complete reproducible held-out gap-policy validation study as formatted JSON."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
