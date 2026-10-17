"""Run iteration 010: calibrated-selector transformation study.

Experiment goal: measure exact token recovery and byte-level Reed--Solomon
damage after named transformations of iteration 009's calibrated 30-second
carrier plan. The attack list, cover variants, token, parity, threshold, and
mapping modes are fixed before execution.

Pipeline state: iteration 009 achieved clean exact recovery across ten seeded
variants with oracle frame maps. This study preserves that source map for
mapping-preserving attacks, records trailing crop erasures separately, and
labels leading-crop results as alignment-limited because no crop realignment
algorithm exists. It does not claim independent decoder synchronization.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
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
from ..iteration_004_four_frame_soft_combine.run import _extraction_record
from ..iteration_006_duration_stability_bounds.run import (
    _cover_variant,
    _trial_offset_seconds,
)
from ..iteration_009_calibrated_margin_selection.run import CalibratedMarginExperiment


AudioTransform = Callable[[PcmAudio, int], PcmAudio]


@dataclass(frozen=True, slots=True)
class AttackDefinition:
    """Describe one pre-registered transformation and its oracle frame-map interpretation."""

    name: str
    mapping_mode: str
    transform: AudioTransform


@dataclass(frozen=True, slots=True)
class AttackTrialRecord:
    """Record one source variant, attack output, and exact token recovery diagnostics."""

    attack_name: str
    mapping_mode: str
    trial_index: int
    embedding_snr_db: float | None
    output_duration_seconds: float | None
    measurement: Mapping[str, object] | None
    error: str | None


def _attack_definitions() -> tuple[AttackDefinition, ...]:
    """Return the fixed clean and transformed conditions for this pre-registered study."""

    return (
        AttackDefinition("clean_pcm", "preserved_source_frame_map", lambda audio, seed: audio),
        AttackDefinition("mp3_64k", "preserved_source_frame_map", lambda audio, seed: mp3_round_trip(audio, 64)),
        AttackDefinition("mp3_96k", "preserved_source_frame_map", lambda audio, seed: mp3_round_trip(audio, 96)),
        AttackDefinition("mp3_128k", "preserved_source_frame_map", lambda audio, seed: mp3_round_trip(audio, 128)),
        AttackDefinition(
            "resample_44k1_round_trip",
            "preserved_source_frame_map",
            lambda audio, seed: resample_audio(resample_audio(audio, 44100), 16000),
        ),
        AttackDefinition(
            "peak_normalize_090",
            "preserved_source_frame_map",
            lambda audio, seed: normalize_peak(audio, 0.90),
        ),
        AttackDefinition(
            "noise_30db",
            "preserved_source_frame_map",
            lambda audio, seed: add_white_noise(audio, 30.0, seed),
        ),
        AttackDefinition(
            "low_pass_4khz",
            "preserved_source_frame_map",
            lambda audio, seed: low_pass_filter(audio, 4000.0),
        ),
        AttackDefinition(
            "trailing_crop_025s",
            "trailing_erasures_with_original_map",
            lambda audio, seed: trim_audio(audio, 0.0, audio.duration_seconds - 0.25),
        ),
        AttackDefinition(
            "leading_crop_025s",
            "unrealigned_original_map_alignment_limited",
            lambda audio, seed: trim_audio(audio, 0.25, audio.duration_seconds),
        ),
    )


def evaluate_variant(
    trial_index: int,
    attacks: Iterable[AttackDefinition],
) -> tuple[AttackTrialRecord, ...]:
    """Calibrate and embed one cover once, then measure every declared transformation from it."""

    seed = 6100 + trial_index
    source = _cover_variant(30, seed, _trial_offset_seconds(trial_index))
    pilot = SpectralAudioPilot(
        b"audio-pilot-test-key",
        SpectralPilotConfig(relative_difference=0.95),
        AudioWatermarkConfig(parity_symbols=12),
    )
    experiment = CalibratedMarginExperiment(pilot, 0.01)
    try:
        embedding = experiment.embed(source, bytes.fromhex("0123456789abcdef"))
    except Exception as error:
        detail = str(error) or "no message"
        return tuple(
            AttackTrialRecord(
                attack.name,
                attack.mapping_mode,
                trial_index,
                None,
                None,
                None,
                f"{type(error).__name__}: {detail}",
            )
            for attack in attacks
        )
    records: list[AttackTrialRecord] = []
    for attack in attacks:
        try:
            attacked_audio = attack.transform(embedding.audio, 10000 + trial_index)
            extraction = experiment.extract(attacked_audio, embedding)
            measurement = _extraction_record(experiment, embedding, extraction)
        except Exception as error:
            detail = str(error) or "no message"
            records.append(
                AttackTrialRecord(
                    attack.name,
                    attack.mapping_mode,
                    trial_index,
                    embedding.signal_to_noise_db,
                    None,
                    None,
                    f"{type(error).__name__}: {detail}",
                )
            )
            continue
        records.append(
            AttackTrialRecord(
                attack.name,
                attack.mapping_mode,
                trial_index,
                embedding.signal_to_noise_db,
                attacked_audio.duration_seconds,
                measurement,
                None,
            )
        )
    return tuple(records)


def _aggregate_attack(attack: AttackDefinition, trials: Iterable[AttackTrialRecord]) -> dict[str, object]:
    """Summarize exact recovery, RS damage, encoding SNR, and execution failures for one attack."""

    trial_records = tuple(trials)
    measurements = tuple(trial.measurement for trial in trial_records if trial.measurement is not None)
    snr_values = tuple(trial.embedding_snr_db for trial in trial_records if trial.embedding_snr_db is not None)
    duration_values = tuple(
        trial.output_duration_seconds for trial in trial_records if trial.output_duration_seconds is not None
    )
    rs_costs = tuple(int(measurement["rs_error_cost"]) for measurement in measurements)
    byte_erasures = tuple(int(measurement["byte_erasures"]) for measurement in measurements)
    unknown_byte_errors = tuple(int(measurement["unknown_byte_errors"]) for measurement in measurements)
    exact_recoveries = sum(measurement["token_matches_input"] for measurement in measurements)
    return {
        "attack_name": attack.name,
        "mapping_mode": attack.mapping_mode,
        "trial_count": len(trial_records),
        "execution_failures": sum(trial.error is not None for trial in trial_records),
        "exact_recoveries": exact_recoveries,
        "exact_recovery_rate": exact_recoveries / len(trial_records),
        "median_rs_cost": median(rs_costs) if rs_costs else None,
        "maximum_rs_cost": max(rs_costs) if rs_costs else None,
        "median_unknown_byte_errors": median(unknown_byte_errors) if unknown_byte_errors else None,
        "median_byte_erasures": median(byte_erasures) if byte_erasures else None,
        "median_embedding_snr_db": median(snr_values) if snr_values else None,
        "median_output_duration_seconds": median(duration_values) if duration_values else None,
    }


def run() -> dict[str, object]:
    """Execute all declared attacks over ten calibrated 30-second cover variants."""

    attacks = _attack_definitions()
    trial_count = 10
    trials = tuple(
        record
        for trial_index in range(trial_count)
        for record in evaluate_variant(trial_index, attacks)
    )
    summaries = tuple(
        _aggregate_attack(
            attack,
            tuple(trial for trial in trials if trial.attack_name == attack.name),
        )
        for attack in attacks
    )
    return {
        "fixture": "ten seeded 30-second music-like cover variants and virtual timeline offsets",
        "sample_rate": 16000,
        "token_bytes": 8,
        "parity_symbols": 12,
        "repetition": 4,
        "relative_difference": 0.95,
        "threshold": 0.01,
        "calibration_candidates_per_stratum": 2,
        "trial_count": trial_count,
        "attacks": [
            {"name": attack.name, "mapping_mode": attack.mapping_mode} for attack in attacks
        ],
        "summaries": list(summaries),
        "trials": [asdict(trial) for trial in trials],
    }


def main() -> None:
    """Print the complete reproducible calibrated-selector transformation study as JSON."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
