"""Run iteration 004: oracle-map upper bound for joint-calibrated split-pair payloads.

Experiment goal: separate payload-channel damage from non-oracle map-selection
damage after iteration 003. The encoder and pair allocations are unchanged:
each selected frame holds a disjoint local-pilot group and payload group, and
candidate ranks are selected by the weaker post-round-trip pilot/payload
margin. Extraction receives the retained encoder frame map, reads payload pairs
only, and soft-combines four copies. No non-oracle candidate reconstruction,
pilot selection, transform, or false-positive claim is made in this upper bound.

Pipeline state: iteration 003 restored approximately 84% median non-oracle map
selection accuracy yet recovered no tokens. This experiment determines whether
the exact split-pair payload channel can recover under its known best alignment
on the same clean synthetic fixture.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from statistics import median

from ....pilot import SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioWatermarkConfig
from ...transport_optimization.iteration_004_four_frame_soft_combine.run import _extraction_record
from ...transport_optimization.iteration_006_duration_stability_bounds.run import (
    _cover_variant,
    _trial_offset_seconds,
)
from ..iteration_002_local_selection_pilot.run import LocalPilotProfile, _profiles
from ..iteration_003_joint_pilot_payload_calibration.run import JointCalibratedLocalPilotExperiment


@dataclass(frozen=True, slots=True)
class OracleUpperBoundTrial:
    """Record one clean split-pair embedding and its retained-map payload recovery outcome."""

    profile_name: str
    trial_index: int
    embedding_snr_db: float | None
    measurement: dict[str, object] | None
    error: str | None


def evaluate_trial(profile: LocalPilotProfile, trial_index: int) -> OracleUpperBoundTrial:
    """Embed one clean cover and recover its payload using the retained exact encoder frame map."""

    token = bytes.fromhex("0123456789abcdef")
    source = _cover_variant(30, 6100 + trial_index, _trial_offset_seconds(trial_index))
    pilot = SpectralAudioPilot(
        b"audio-pilot-test-key",
        SpectralPilotConfig(
            minimum_frequency_hz=500.0,
            maximum_frequency_hz=3800.0,
            relative_difference=0.95,
        ),
        AudioWatermarkConfig(parity_symbols=12),
    )
    experiment = JointCalibratedLocalPilotExperiment(pilot, 0.01, profile)
    try:
        embedding = experiment.embed(source, token)
        extraction = experiment.extract(embedding.audio, embedding)
        measurement = _extraction_record(experiment, embedding, extraction)
    except Exception as error:
        detail = str(error) or "no message"
        return OracleUpperBoundTrial(profile.name, trial_index, None, None, f"{type(error).__name__}: {detail}")
    return OracleUpperBoundTrial(
        profile.name,
        trial_index,
        embedding.signal_to_noise_db,
        measurement,
        None,
    )


def _summary(profile: LocalPilotProfile, trials: tuple[OracleUpperBoundTrial, ...]) -> dict[str, object]:
    """Aggregate exact recovery, byte damage, RS burden, and SNR for one retained-map profile."""

    successful = tuple(trial for trial in trials if trial.measurement is not None)
    measurements = tuple(trial.measurement for trial in successful if trial.measurement is not None)
    snr_values = tuple(trial.embedding_snr_db for trial in successful if trial.embedding_snr_db is not None)
    return {
        "profile_name": profile.name,
        "pilot_pair_count": profile.pilot_pair_count,
        "payload_pair_count": 16 - profile.pilot_pair_count,
        "minimum_pilot_pairs": profile.minimum_pilot_pairs,
        "minimum_payload_pairs": profile.minimum_payload_pairs,
        "minimum_pilot_margin": profile.minimum_pilot_margin,
        "trial_count": len(trials),
        "execution_failures": sum(trial.error is not None for trial in trials),
        "exact_recoveries": sum(bool(measurement["token_matches_input"]) for measurement in measurements),
        "median_rs_cost": median(int(measurement["rs_error_cost"]) for measurement in measurements) if measurements else None,
        "maximum_rs_cost": max(int(measurement["rs_error_cost"]) for measurement in measurements) if measurements else None,
        "median_known_bit_errors": median(int(measurement["known_bit_errors"]) for measurement in measurements) if measurements else None,
        "median_carrier_erasures": median(int(measurement["carrier_erasures"]) for measurement in measurements) if measurements else None,
        "median_unknown_byte_errors": median(int(measurement["unknown_byte_errors"]) for measurement in measurements) if measurements else None,
        "median_byte_erasures": median(int(measurement["byte_erasures"]) for measurement in measurements) if measurements else None,
        "median_embedding_snr_db": median(snr_values) if snr_values else None,
    }


def run() -> dict[str, object]:
    """Run retained-map clean payload extraction for both joint-calibrated split-pair profiles."""

    profiles = _profiles()
    trials = tuple(
        trial
        for profile in profiles
        for trial_index in range(10)
        for trial in (evaluate_trial(profile, trial_index),)
    )
    summaries = tuple(
        _summary(profile, tuple(trial for trial in trials if trial.profile_name == profile.name))
        for profile in profiles
    )
    return {
        "fixture": "ten seeded 30-second music-like cover variants and virtual timeline offsets",
        "mapping_mode": "retained_encoder_frame_map_payload_upper_bound",
        "decoder_received_oracle_map": True,
        "calibration_objective": "maximize min(signed_payload_margin, signed_pilot_margin)",
        "carrier_band_hz": [500.0, 3800.0],
        "relative_difference": 0.95,
        "parity_symbols": 12,
        "repetition": 4,
        "profiles": [asdict(profile) for profile in profiles],
        "summaries": list(summaries),
        "trials": [asdict(trial) for trial in trials],
    }


def main() -> None:
    """Print the complete reproducible retained-map split-pair upper-bound study as JSON."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
