"""Run iteration 011: blind attack validation for the compact registry handle.

Experiment goal: validate iteration 010's selected six-byte opaque registry
handle plus fourteen Reed--Solomon parity symbols under named codec, DSP, and
bounded crop transformations. Every decode reconstructs the candidate map from
the observed audio, secret-derived pilots, and frozen decoder thresholds; it
never receives the encoder-selected frame map. Exact known-handle recovery,
RS byte damage, selected-map diagnostics, audio duration, SNR, and exact-token
negative controls are reported separately for every attack.

Pipeline state: iteration 010 established that 6 payload + 14 parity recovers
10/10 clean, fresh synthetic covers with a constant 20-byte codeword and 184
logical carrier bits. The repository has no licensed recorded-audio corpus, so
this pre-registered continuation uses disjoint synthetic music-like covers.
It establishes only named-transformation smoke evidence and explicitly avoids
claims about real speech, music, arbitrary codecs, DSP, or perceptual quality.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import asdict, dataclass
import json
from statistics import median

from ....attacks import (
    add_white_noise,
    low_pass_filter,
    mp3_round_trip,
    normalize_peak,
    resample_audio,
    trim_audio,
)
from ....pilot import PcmAudio, SpectralAudioPilot, SpectralPilotConfig
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
from ..iteration_006_pilot_threshold_sweep.run import PilotThresholds, ThresholdedLocalPilotDecoder
from ..iteration_010_constant_codeword_allocation.run import CodewordAllocation, _allocations


AudioTransform = Callable[[PcmAudio, int], PcmAudio]


@dataclass(frozen=True, slots=True)
class AttackDefinition:
    """Declare one reproducible named transform and whether original-frame diagnostics remain comparable."""

    name: str
    map_diagnostic_mode: str
    transform: AudioTransform


@dataclass(frozen=True, slots=True)
class BlindAttackTrial:
    """Record one attacked blind decode, post-hoc diagnostics, and exact-handle controls."""

    attack_name: str
    map_diagnostic_mode: str
    trial_index: int
    cover_seed: int
    virtual_timeline_offset_seconds: float
    decoder_received_oracle_map: bool
    output_duration_seconds: float | None
    embedding_snr_db: float | None
    map_metrics: dict[str, object] | None
    measurement: dict[str, object] | None
    unwatermarked_control_handle_match: bool | None
    wrong_secret_control_handle_match: bool | None
    error: str | None


def _selected_allocation() -> CodewordAllocation:
    """Return the six-byte opaque registry handle and fourteen-parity allocation selected by iteration 010."""

    return next(allocation for allocation in _allocations() if allocation.name == "registry_handle_6_parity_14")


def _threshold_policy() -> PilotThresholds:
    """Return the frozen blind pilot thresholds selected before this validation study."""

    return PilotThresholds(0.0, 0.24)


def _attack_definitions() -> tuple[AttackDefinition, ...]:
    """Return the pre-registered clean, codec, DSP, and bounded-crop transformations."""

    return (
        AttackDefinition("clean_pcm", "posthoc_original_timeline", lambda audio, seed: audio),
        AttackDefinition("mp3_64k", "posthoc_original_timeline", lambda audio, seed: mp3_round_trip(audio, 64)),
        AttackDefinition("mp3_96k", "posthoc_original_timeline", lambda audio, seed: mp3_round_trip(audio, 96)),
        AttackDefinition("mp3_128k", "posthoc_original_timeline", lambda audio, seed: mp3_round_trip(audio, 128)),
        AttackDefinition(
            "resample_44k1_round_trip",
            "posthoc_original_timeline",
            lambda audio, seed: resample_audio(resample_audio(audio, 44100), audio.sample_rate),
        ),
        AttackDefinition("peak_normalize_090", "posthoc_original_timeline", lambda audio, seed: normalize_peak(audio, 0.90)),
        AttackDefinition("noise_30db", "posthoc_original_timeline", lambda audio, seed: add_white_noise(audio, 30.0, seed)),
        AttackDefinition("low_pass_4khz", "posthoc_original_timeline", lambda audio, seed: low_pass_filter(audio, 4000.0)),
        AttackDefinition(
            "trailing_crop_025s",
            "timeline_unaligned_not_scored",
            lambda audio, seed: trim_audio(audio, 0.0, audio.duration_seconds - 0.25),
        ),
        AttackDefinition(
            "leading_crop_025s",
            "timeline_unaligned_not_scored",
            lambda audio, seed: trim_audio(audio, 0.25, audio.duration_seconds),
        ),
    )


def _decoder(audio_config: AudioWatermarkConfig) -> tuple[ContrastivePilotCalibratedExperiment, ThresholdedLocalPilotDecoder]:
    """Build the fixed encoder calibration and frozen blind decoder for one secret and schema."""

    pilot = SpectralAudioPilot(
        b"audio-pilot-test-key",
        SpectralPilotConfig(
            minimum_frequency_hz=500.0,
            maximum_frequency_hz=3800.0,
            relative_difference=0.95,
        ),
        audio_config,
    )
    encoder = ContrastivePilotCalibratedExperiment(pilot, 0.01, _profile())
    return encoder, ThresholdedLocalPilotDecoder(encoder, 0.01, _threshold_policy())


def _profile() -> LocalPilotProfile:
    """Return the frozen four-pilot / twelve-payload spectral-pair allocation from iteration 005."""

    return next(profile for profile in _profiles() if profile.name == "small_pilot_4_payload_12")


def _measured_extraction(reconstruction, token: bytes) -> FourFrameExtraction:
    """Convert one blind decoder output into the shared transport-measurement record shape."""

    extraction = reconstruction.extraction
    return FourFrameExtraction(
        extraction.replica_scores,
        extraction.combined_scores,
        extraction.observed_carrier_bits,
        extraction.known_bit_errors,
        extraction.carrier_erasures,
        extraction.recovery,
        extraction.recovery.token == token,
    )


def evaluate_variant(trial_index: int, attacks: Iterable[AttackDefinition]) -> tuple[BlindAttackTrial, ...]:
    """Embed one disjoint cover once and blindly evaluate every requested named transformation."""

    allocation = _selected_allocation()
    token = allocation.token()
    cover_seed = 6600 + trial_index
    timeline_offset = _trial_offset_seconds(400 + trial_index)
    source = _cover_variant(30, cover_seed, timeline_offset)
    watermark_config = AudioWatermarkConfig(
        attribution_token_bytes=allocation.payload_bytes,
        parity_symbols=allocation.parity_symbols,
    )
    attack_values = tuple(attacks)
    encoder, decoder = _decoder(watermark_config)
    try:
        embedding = encoder.embed(source, token)
        wrong_pilot = SpectralAudioPilot(
            b"wrong-audio-pilot-test-key",
            SpectralPilotConfig(
                minimum_frequency_hz=500.0,
                maximum_frequency_hz=3800.0,
                relative_difference=0.95,
            ),
            watermark_config,
        )
        wrong_encoder = ContrastivePilotCalibratedExperiment(wrong_pilot, 0.01, _profile())
        wrong_decoder = ThresholdedLocalPilotDecoder(wrong_encoder, 0.01, _threshold_policy())
        wrong_plan = wrong_pilot.schema.plan_attribution(token)
    except Exception as error:
        detail = str(error) or "no message"
        return tuple(
            BlindAttackTrial(
                attack.name,
                attack.map_diagnostic_mode,
                trial_index,
                cover_seed,
                timeline_offset,
                False,
                None,
                None,
                None,
                None,
                None,
                None,
                f"{type(error).__name__}: {detail}",
            )
            for attack in attack_values
        )
    records: list[BlindAttackTrial] = []
    for attack in attack_values:
        try:
            attack_seed = 7000 + trial_index
            attacked_audio = attack.transform(embedding.audio, attack_seed)
            reconstruction = decoder.reconstruct(attacked_audio, embedding.carrier_plan)
            measurement = _extraction_record(encoder, embedding, _measured_extraction(reconstruction, token))
            unwatermarked = decoder.reconstruct(attack.transform(source, attack_seed), embedding.carrier_plan)
            wrong_secret = wrong_decoder.reconstruct(attack.transform(embedding.audio, attack_seed), wrong_plan)
            map_metrics = (
                _map_metrics(reconstruction, embedding)
                if attack.map_diagnostic_mode == "posthoc_original_timeline"
                else None
            )
        except Exception as error:
            detail = str(error) or "no message"
            records.append(
                BlindAttackTrial(
                    attack.name,
                    attack.map_diagnostic_mode,
                    trial_index,
                    cover_seed,
                    timeline_offset,
                    False,
                    None,
                    embedding.signal_to_noise_db,
                    None,
                    None,
                    None,
                    None,
                    f"{type(error).__name__}: {detail}",
                )
            )
            continue
        records.append(
            BlindAttackTrial(
                attack.name,
                attack.map_diagnostic_mode,
                trial_index,
                cover_seed,
                timeline_offset,
                False,
                attacked_audio.duration_seconds,
                embedding.signal_to_noise_db,
                map_metrics,
                measurement,
                _control_token_match(unwatermarked, token),
                _control_token_match(wrong_secret, token),
                None,
            )
        )
    return tuple(records)


def _summary(attack: AttackDefinition, trials: tuple[BlindAttackTrial, ...]) -> dict[str, object]:
    """Aggregate exact recovery, RS cost, post-hoc map diagnostics, and controls for one named attack."""

    measurements = tuple(trial.measurement for trial in trials if trial.measurement is not None)
    map_metrics = tuple(trial.map_metrics for trial in trials if trial.map_metrics is not None)
    rs_costs = tuple(int(measurement["rs_error_cost"]) for measurement in measurements)
    selected_accuracy = tuple(
        float(metric["selected_map_accuracy"])
        for metric in map_metrics
        if metric["selected_map_accuracy"] is not None
    )
    return {
        "attack_name": attack.name,
        "map_diagnostic_mode": attack.map_diagnostic_mode,
        "trial_count": len(trials),
        "execution_failures": sum(trial.error is not None for trial in trials),
        "exact_recoveries": sum(bool(measurement["token_matches_input"]) for measurement in measurements),
        "median_rs_cost": median(rs_costs) if rs_costs else None,
        "maximum_rs_cost": max(rs_costs) if rs_costs else None,
        "median_known_bit_errors": median(int(measurement["known_bit_errors"]) for measurement in measurements) if measurements else None,
        "median_carrier_erasures": median(int(measurement["carrier_erasures"]) for measurement in measurements) if measurements else None,
        "median_unknown_byte_errors": median(int(measurement["unknown_byte_errors"]) for measurement in measurements) if measurements else None,
        "median_byte_erasures": median(int(measurement["byte_erasures"]) for measurement in measurements) if measurements else None,
        "median_selected_map_accuracy": median(selected_accuracy) if selected_accuracy else None,
        "median_selection_erasure_rate": median(float(metric["selection_erasure_rate"]) for metric in map_metrics) if map_metrics else None,
        "median_embedding_snr_db": median(
            trial.embedding_snr_db for trial in trials if trial.embedding_snr_db is not None
        ) if measurements else None,
        "unwatermarked_control_false_accepts": sum(bool(trial.unwatermarked_control_handle_match) for trial in trials),
        "wrong_secret_control_false_accepts": sum(bool(trial.wrong_secret_control_handle_match) for trial in trials),
    }


def run() -> dict[str, object]:
    """Run all named blind attacks over ten disjoint synthetic cover variants and archive their outcomes."""

    allocation = _selected_allocation()
    attacks = _attack_definitions()
    trials = tuple(
        record
        for trial_index in range(10)
        for record in evaluate_variant(trial_index, attacks)
    )
    return {
        "fixture": "ten fresh seeded 30-second synthetic music-like cover variants and virtual timeline offsets",
        "mapping_mode": "blind_non_oracle_named_attack_validation",
        "decoder_received_oracle_map": False,
        "posthoc_map_diagnostics": "Original source-map comparisons are diagnostics only and are omitted for cropped timelines.",
        "allocation": asdict(allocation),
        "protected_codeword_bytes": allocation.payload_bytes + allocation.parity_symbols,
        "framing_overhead_bytes": 3,
        "carrier_bit_count": 184,
        "physical_carrier_count": 736,
        "profile_name": _profile().name,
        "frozen_policy": asdict(_threshold_policy()) | {"name": _threshold_policy().name},
        "carrier_band_hz": [500.0, 3800.0],
        "relative_difference": 0.95,
        "validation_cover_seeds": list(range(6600, 6610)),
        "attacks": [attack.name for attack in attacks],
        "summaries": [
            _summary(attack, tuple(trial for trial in trials if trial.attack_name == attack.name))
            for attack in attacks
        ],
        "trials": [asdict(trial) for trial in trials],
    }


def main() -> None:
    """Print the complete reproducible blind attack validation as formatted JSON."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
