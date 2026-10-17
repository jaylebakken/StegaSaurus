"""Run iteration 013: low-pass-aware carrier-band profile study.

Experiment goal: determine whether restricting the carrier frequency band below
the 4 kHz low-pass cutoff closes iteration 010's low-pass recovery gap without
breaking clean, MP3, or bounded leading-crop recovery. The study holds token
size, parity, repetition, embedding strength, calibrated selection, and the
oracle-map synchronization procedure constant while changing only carrier-band
limits.

Pipeline state: iteration 011 recovered a bounded leading crop with a sync-only
oracle-map scan, while iteration 010 failed a 4 kHz low-pass condition because
the baseline carrier band extends to 6 kHz. This experiment remains synthetic,
oracle aligned, and limited to named transformations; it does not establish
blind synchronization or production codec robustness.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass
import json
from statistics import median

from ....attacks import low_pass_filter, mp3_round_trip, trim_audio
from ....pilot import PcmAudio, SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioWatermarkConfig
from ..iteration_004_four_frame_soft_combine.run import _extraction_record
from ..iteration_006_duration_stability_bounds.run import (
    _cover_variant,
    _trial_offset_seconds,
)
from ..iteration_011_oracle_map_offset_sync.run import OffsetAlignedCalibratedMarginExperiment


AudioTransform = Callable[[PcmAudio], PcmAudio]


@dataclass(frozen=True, slots=True)
class CarrierBandProfile:
    """Describe one fixed minimum and maximum carrier-frequency band for comparison."""

    name: str
    minimum_frequency_hz: float
    maximum_frequency_hz: float


@dataclass(frozen=True, slots=True)
class AttackDefinition:
    """Describe one named transformation and whether it needs the leading-crop offset scan."""

    name: str
    mapping_mode: str
    transform: AudioTransform
    offset_scan: bool = False


@dataclass(frozen=True, slots=True)
class BandTrialRecord:
    """Record exact recovery and byte-level diagnostics for one band profile and attack trial."""

    profile_name: str
    attack_name: str
    mapping_mode: str
    trial_index: int
    embedding_snr_db: float | None
    measurement: Mapping[str, object] | None
    selected_sample_offset: int | None
    error: str | None


def _profiles() -> tuple[CarrierBandProfile, ...]:
    """Return the fixed baseline and low-pass-aware carrier frequency profiles."""

    return (
        CarrierBandProfile("baseline_500_6000hz", 500.0, 6000.0),
        CarrierBandProfile("guarded_500_3800hz", 500.0, 3800.0),
        CarrierBandProfile("lowpass_safe_500_3200hz", 500.0, 3200.0),
    )


def _attacks() -> tuple[AttackDefinition, ...]:
    """Return the fixed clean and named transformation conditions for every band profile."""

    return (
        AttackDefinition("clean_pcm", "preserved_source_frame_map", lambda audio: audio),
        AttackDefinition("mp3_64k", "preserved_source_frame_map", lambda audio: mp3_round_trip(audio, 64)),
        AttackDefinition(
            "low_pass_4khz",
            "preserved_source_frame_map",
            lambda audio: low_pass_filter(audio, 4000.0),
        ),
        AttackDefinition(
            "leading_crop_025s",
            "sync_only_oracle_map_offset_scan",
            lambda audio: trim_audio(audio, 0.25, audio.duration_seconds),
            True,
        ),
    )


def evaluate_variant(
    profile: CarrierBandProfile,
    trial_index: int,
    attacks: Iterable[AttackDefinition],
) -> tuple[BandTrialRecord, ...]:
    """Calibrate one cover under a profile, then apply every named transformation once."""

    source = _cover_variant(30, 6100 + trial_index, _trial_offset_seconds(trial_index))
    pilot = SpectralAudioPilot(
        b"audio-pilot-test-key",
        SpectralPilotConfig(
            minimum_frequency_hz=profile.minimum_frequency_hz,
            maximum_frequency_hz=profile.maximum_frequency_hz,
            relative_difference=0.95,
        ),
        AudioWatermarkConfig(parity_symbols=12),
    )
    experiment = OffsetAlignedCalibratedMarginExperiment(pilot, 0.01)
    attack_values = tuple(attacks)
    try:
        embedding = experiment.embed(source, bytes.fromhex("0123456789abcdef"))
    except Exception as error:
        detail = str(error) or "no message"
        return tuple(
            BandTrialRecord(profile.name, attack.name, attack.mapping_mode, trial_index, None, None, None, f"{type(error).__name__}: {detail}")
            for attack in attack_values
        )
    records: list[BandTrialRecord] = []
    for attack in attack_values:
        try:
            attacked_audio = attack.transform(embedding.audio)
            if attack.offset_scan:
                aligned = experiment.extract_with_offset_scan(attacked_audio, embedding, 32)
                extraction = aligned.extraction
                selected_sample_offset = aligned.alignment.sample_offset
            else:
                extraction = experiment.extract(attacked_audio, embedding)
                selected_sample_offset = None
            measurement = _extraction_record(experiment, embedding, extraction)
        except Exception as error:
            detail = str(error) or "no message"
            records.append(
                BandTrialRecord(
                    profile.name,
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
            BandTrialRecord(
                profile.name,
                attack.name,
                attack.mapping_mode,
                trial_index,
                embedding.signal_to_noise_db,
                measurement,
                selected_sample_offset,
                None,
            )
        )
    return tuple(records)


def _aggregate(
    profile: CarrierBandProfile,
    attack: AttackDefinition,
    trials: Iterable[BandTrialRecord],
) -> dict[str, object]:
    """Summarize exact recovery, RS burden, SNR, and tool failures for one profile condition."""

    trial_values = tuple(trials)
    measurements = tuple(trial.measurement for trial in trial_values if trial.measurement is not None)
    snr_values = tuple(trial.embedding_snr_db for trial in trial_values if trial.embedding_snr_db is not None)
    rs_costs = tuple(int(measurement["rs_error_cost"]) for measurement in measurements)
    byte_errors = tuple(int(measurement["unknown_byte_errors"]) for measurement in measurements)
    byte_erasures = tuple(int(measurement["byte_erasures"]) for measurement in measurements)
    exact_recoveries = sum(measurement["token_matches_input"] for measurement in measurements)
    return {
        "profile_name": profile.name,
        "minimum_frequency_hz": profile.minimum_frequency_hz,
        "maximum_frequency_hz": profile.maximum_frequency_hz,
        "attack_name": attack.name,
        "mapping_mode": attack.mapping_mode,
        "trial_count": len(trial_values),
        "execution_failures": sum(trial.error is not None for trial in trial_values),
        "exact_recoveries": exact_recoveries,
        "exact_recovery_rate": exact_recoveries / len(trial_values),
        "median_rs_cost": median(rs_costs) if rs_costs else None,
        "maximum_rs_cost": max(rs_costs) if rs_costs else None,
        "median_unknown_byte_errors": median(byte_errors) if byte_errors else None,
        "median_byte_erasures": median(byte_erasures) if byte_erasures else None,
        "median_embedding_snr_db": median(snr_values) if snr_values else None,
    }


def run() -> dict[str, object]:
    """Execute all profile and transformation combinations over ten calibrated cover variants."""

    profiles = _profiles()
    attacks = _attacks()
    trial_count = 10
    trials = tuple(
        record
        for profile in profiles
        for trial_index in range(trial_count)
        for record in evaluate_variant(profile, trial_index, attacks)
    )
    summaries = tuple(
        _aggregate(
            profile,
            attack,
            tuple(
                trial
                for trial in trials
                if trial.profile_name == profile.name and trial.attack_name == attack.name
            ),
        )
        for profile in profiles
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
        "profiles": [asdict(profile) for profile in profiles],
        "attacks": [asdict(attack) | {"transform": None} for attack in attacks],
        "summaries": list(summaries),
        "trials": [asdict(trial) for trial in trials],
    }


def main() -> None:
    """Print the complete reproducible carrier-band profile study as formatted JSON."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
