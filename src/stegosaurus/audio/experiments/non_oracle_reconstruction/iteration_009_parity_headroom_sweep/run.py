"""Run iteration 009: held-out Reed--Solomon parity headroom sweep.

Experiment goal: test the smallest transport-only change suggested by iteration
008's two near-budget misses. The contrastive 4-pilot / 12-payload encoder and
frozen blind decoder policy (absolute pilot threshold 0.00, pilot gap 0.24) are
unchanged. Fresh 30-second synthetic covers are embedded with 12, 14, and 16
Reed--Solomon parity symbols and decoded without encoder frame maps. This
measures both recovery headroom and the carrier-capacity cost of longer plans.

Pipeline state: iteration 008 recovered 8/10 fresh synthetic variants with a
12-symbol budget; its two misses cost 13 and 14. A parity increase changes the
codeword length, framed carrier count, interleaving, and candidate strata, so
this end-to-end experiment is required rather than assuming old observations
would decode under a larger parity budget.
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
class ParitySweepTrial:
    """Record one fresh parity configuration, blind extraction, map diagnostics, and controls."""

    parity_symbols: int
    trial_index: int
    cover_seed: int
    virtual_timeline_offset_seconds: float
    carrier_bit_count: int | None
    physical_carrier_count: int | None
    embedding_snr_db: float | None
    map_metrics: dict[str, object] | None
    measurement: dict[str, object] | None
    unwatermarked_control_token_match: bool | None
    wrong_secret_control_token_match: bool | None
    error: str | None


def _profile() -> LocalPilotProfile:
    """Return the contrastive 4-pilot / 12-payload allocation held fixed for the parity sweep."""

    return next(profile for profile in _profiles() if profile.name == "small_pilot_4_payload_12")


def _threshold_policy() -> PilotThresholds:
    """Return the held-out policy frozen by iteration 007 telemetry and validated in iteration 008."""

    return PilotThresholds(0.0, 0.24)


def _parity_options() -> tuple[int, ...]:
    """Return the declared minimum, boundary-covering, and safety-margin parity configurations."""

    return (12, 14, 16)


def evaluate_trial(parity_symbols: int, trial_index: int) -> ParitySweepTrial:
    """Blindly encode and decode one fresh cover with a specified Reed--Solomon parity budget."""

    token = bytes.fromhex("0123456789abcdef")
    cover_seed = 6400 + trial_index
    timeline_offset = _trial_offset_seconds(200 + trial_index)
    source = _cover_variant(30, cover_seed, timeline_offset)
    config = SpectralPilotConfig(
        minimum_frequency_hz=500.0,
        maximum_frequency_hz=3800.0,
        relative_difference=0.95,
    )
    watermark_config = AudioWatermarkConfig(parity_symbols=parity_symbols)
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
        return ParitySweepTrial(
            parity_symbols,
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
    return ParitySweepTrial(
        parity_symbols,
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


def _summary(parity_symbols: int, trials: tuple[ParitySweepTrial, ...]) -> dict[str, object]:
    """Aggregate recovery, capacity, map, RS, SNR, and control outcomes for one parity level."""

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
        "parity_symbols": parity_symbols,
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
        "unwatermarked_control_false_accepts": sum(bool(trial.unwatermarked_control_token_match) for trial in successful),
        "wrong_secret_control_false_accepts": sum(bool(trial.wrong_secret_control_token_match) for trial in successful),
    }


def run() -> dict[str, object]:
    """Run the fresh held-out parity sweep for all declared Reed--Solomon configurations."""

    parity_options = _parity_options()
    trials = tuple(
        trial
        for parity_symbols in parity_options
        for trial_index in range(10)
        for trial in (evaluate_trial(parity_symbols, trial_index),)
    )
    summaries = tuple(
        _summary(
            parity_symbols,
            tuple(trial for trial in trials if trial.parity_symbols == parity_symbols),
        )
        for parity_symbols in parity_options
    )
    return {
        "fixture": "ten fresh seeded 30-second music-like cover variants and virtual timeline offsets",
        "mapping_mode": "blind_non_oracle_held_out_parity_headroom_sweep",
        "decoder_received_oracle_map": False,
        "profile": asdict(_profile()),
        "frozen_policy": asdict(_threshold_policy()) | {"name": _threshold_policy().name},
        "parity_options": parity_options,
        "validation_cover_seeds": list(range(6400, 6410)),
        "carrier_band_hz": [500.0, 3800.0],
        "relative_difference": 0.95,
        "token_bytes": 8,
        "repetition": 4,
        "summaries": list(summaries),
        "trials": [asdict(trial) for trial in trials],
    }


def main() -> None:
    """Print the complete reproducible held-out parity headroom sweep as formatted JSON."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
