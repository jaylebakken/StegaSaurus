"""Run iteration 015: held-out deterministic model-center residual validation.

Experiment goal: validate the center-phase residual model on fresh synthetic
covers without importing iteration 014's phase telemetry, phase ranks, or
post-hoc labels. Each received crop first undergoes the unchanged secret-pilot
coarse frame-offset scan. When that offset fits the bounded one-edge-crop
duration model, the decoder computes one deterministic sample-domain analysis
origin, recomputes the STFT there, and performs ordinary blind local-pilot
candidate reconstruction. A missing coarse decision or infeasible center
produces deliberate erasures rather than a guessed phase.

Pipeline state: the encoder, transport, four replicas, 6-byte opaque handle,
14 Reed--Solomon parity symbols, carrier band, pilot split, payload thresholds,
and crop attacks remain fixed. Cover seeds `6700-6709` are disjoint from the
direct-comparison and telemetry seeds `6600-6609` used in iterations 011-014.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import asdict, dataclass
import json
from statistics import median

from ....pilot import PcmAudio, SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioWatermarkConfig, CarrierPlan
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
    LocalPilotReconstruction,
    _control_token_match,
    _profiles,
)
from ..iteration_005_contrastive_pilot_calibration.run import ContrastivePilotCalibratedExperiment
from ..iteration_006_pilot_threshold_sweep.run import PilotThresholds
from ..iteration_010_constant_codeword_allocation.run import CodewordAllocation, _allocations
from ..iteration_011_blind_attack_validation.run import AttackDefinition, _attack_definitions
from ..iteration_013_sample_phase_crop_realignment.run import (
    SamplePhaseLocalPilotDecoder,
    _measured_extraction,
)
from ..iteration_014_residual_phase_telemetry.run import _threshold_policy


@dataclass(frozen=True, slots=True)
class CenterPhaseTrial:
    """Record one fresh crop decode using only blind coarse synchronization and its deterministic residual center."""

    attack_name: str
    trial_index: int
    cover_seed: int
    virtual_timeline_offset_seconds: float
    decoder_received_oracle_map: bool
    residual_phase_selection: str
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
    """Return the six-byte handle plus fourteen-parity transport allocation held fixed for validation."""

    return next(allocation for allocation in _allocations() if allocation.name == "registry_handle_6_parity_14")


def _profile() -> LocalPilotProfile:
    """Return the frozen contrastive four-pilot / twelve-payload local carrier allocation."""

    return next(profile for profile in _profiles() if profile.name == "small_pilot_4_payload_12")


def _crop_attacks() -> tuple[AttackDefinition, ...]:
    """Return the unchanged leading and trailing 250 ms crop definitions for held-out validation."""

    crop_names = {"leading_crop_025s", "trailing_crop_025s"}
    return tuple(attack for attack in _attack_definitions() if attack.name in crop_names)


class DeterministicCenterPhaseDecoder:
    """Decode with the blind coarse scan followed by exactly one duration-model residual center and no phase ranking."""

    def __init__(self, encoder: ContrastivePilotCalibratedExperiment) -> None:
        """Initialize the unchanged coarse scanner and expose no residual telemetry or phase-selection policy."""

        self._phase_helper = SamplePhaseLocalPilotDecoder(encoder)
        self._encoder = encoder
        self._pilot = encoder._pilot

    def reconstruct(
        self,
        audio: PcmAudio,
        carrier_plan: CarrierPlan,
    ) -> tuple[LocalPilotReconstruction, int | None, bool, int | None]:
        """Blindly select a coarse offset, derive one center phase, and reconstruct or intentionally erase on infeasibility."""

        frequencies, spectrum = self._pilot._stft(audio)
        lower_bin, upper_bin = self._pilot._frequency_bin_range(frequencies)
        nominal_frame_count = self._phase_helper._coarse_decoder._nominal_frame_count(audio.sample_rate)
        coarse = self._phase_helper._coarse_decoder._select_offset(
            spectrum,
            carrier_plan,
            lower_bin,
            upper_bin,
            nominal_frame_count,
        )
        if coarse.selected_offset_frames is None:
            return self._phase_helper._coarse_decoder._erasure_reconstruction(carrier_plan), None, False, None
        center_phase = self._phase_helper._edge_crop_phase_center(audio, coarse.selected_offset_frames)
        if center_phase is None:
            return (
                self._phase_helper._coarse_decoder._erasure_reconstruction(carrier_plan),
                coarse.selected_offset_frames,
                True,
                None,
            )
        reframed_audio = self._phase_helper._reframe_audio(audio, center_phase)
        frequencies, reframed_spectrum = self._pilot._stft(reframed_audio)
        lower_bin, upper_bin = self._pilot._frequency_bin_range(frequencies)
        reconstruction = self._phase_helper._coarse_decoder._reconstruct_at_offset(
            reframed_spectrum,
            carrier_plan,
            lower_bin,
            upper_bin,
            nominal_frame_count,
            coarse.selected_offset_frames,
        )
        return reconstruction, coarse.selected_offset_frames, True, center_phase


def _measured(reconstruction: LocalPilotReconstruction, token: bytes) -> FourFrameExtraction:
    """Convert deterministic-center reconstruction output into the common byte-level transport measurement format."""

    return _measured_extraction(reconstruction, token)


def evaluate_variant(trial_index: int, attacks: Iterable[AttackDefinition]) -> tuple[CenterPhaseTrial, ...]:
    """Embed one fresh cover and validate deterministic center-phase decoding for every unchanged crop and control."""

    allocation = _selected_allocation()
    token = allocation.token()
    cover_seed = 6700 + trial_index
    timeline_offset = _trial_offset_seconds(500 + trial_index)
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
    decoder = DeterministicCenterPhaseDecoder(encoder)
    try:
        embedding = encoder.embed(source, token)
        wrong_pilot = SpectralAudioPilot(b"wrong-audio-pilot-test-key", pilot_config, watermark_config)
        wrong_encoder = ContrastivePilotCalibratedExperiment(wrong_pilot, 0.01, _profile())
        wrong_decoder = DeterministicCenterPhaseDecoder(wrong_encoder)
        wrong_plan = wrong_pilot.schema.plan_attribution(token)
    except Exception as error:
        detail = str(error) or "no message"
        return tuple(
            CenterPhaseTrial(
                attack.name, trial_index, cover_seed, timeline_offset, False, "deterministic_model_center",
                None, False, None, False, None, None, None, None, f"{type(error).__name__}: {detail}",
            )
            for attack in attack_values
        )
    records: list[CenterPhaseTrial] = []
    for attack in attack_values:
        try:
            seed = 7100 + trial_index
            attacked_audio = attack.transform(embedding.audio, seed)
            reconstruction, coarse_offset, coarse_accepted, center_phase = decoder.reconstruct(
                attacked_audio,
                embedding.carrier_plan,
            )
            measurement = _extraction_record(encoder, embedding, _measured(reconstruction, token))
            unwatermarked, _, _, _ = decoder.reconstruct(attack.transform(source, seed), embedding.carrier_plan)
            wrong_secret, _, _, _ = wrong_decoder.reconstruct(attack.transform(embedding.audio, seed), wrong_plan)
        except Exception as error:
            detail = str(error) or "no message"
            records.append(
                CenterPhaseTrial(
                    attack.name, trial_index, cover_seed, timeline_offset, False, "deterministic_model_center",
                    None, False, None, False, embedding.signal_to_noise_db, None, None, None,
                    f"{type(error).__name__}: {detail}",
                )
            )
            continue
        records.append(
            CenterPhaseTrial(
                attack.name,
                trial_index,
                cover_seed,
                timeline_offset,
                False,
                "deterministic_model_center",
                coarse_offset,
                coarse_accepted,
                center_phase,
                center_phase is not None,
                embedding.signal_to_noise_db,
                measurement,
                _control_token_match(unwatermarked, token),
                _control_token_match(wrong_secret, token),
                None,
            )
        )
    return tuple(records)


def _summary(attack: AttackDefinition, trials: tuple[CenterPhaseTrial, ...]) -> dict[str, object]:
    """Aggregate held-out coarse acceptance, center feasibility, exact recovery, byte damage, and controls by crop."""

    measurements = tuple(trial.measurement for trial in trials if trial.measurement is not None)
    feasible = tuple(trial for trial in trials if trial.center_phase_feasible)
    recoveries = sum(bool(measurement["token_matches_input"]) for measurement in measurements)
    conditional_recoveries = sum(
        bool(trial.measurement and trial.measurement["token_matches_input"])
        for trial in feasible
    )
    return {
        "attack_name": attack.name,
        "trial_count": len(trials),
        "execution_failures": sum(trial.error is not None for trial in trials),
        "coarse_scan_acceptances": sum(trial.coarse_scan_accepted for trial in trials),
        "deterministic_center_feasible": len(feasible),
        "exact_recoveries": recoveries,
        "conditional_center_phase_recoveries": conditional_recoveries,
        "median_rs_cost": median(int(measurement["rs_error_cost"]) for measurement in measurements) if measurements else None,
        "maximum_rs_cost": max(int(measurement["rs_error_cost"]) for measurement in measurements) if measurements else None,
        "median_carrier_erasures": median(int(measurement["carrier_erasures"]) for measurement in measurements) if measurements else None,
        "median_embedding_snr_db": median(
            trial.embedding_snr_db for trial in trials if trial.embedding_snr_db is not None
        ) if measurements else None,
        "unwatermarked_control_false_accepts": sum(bool(trial.unwatermarked_control_handle_match) for trial in trials),
        "wrong_secret_control_false_accepts": sum(bool(trial.wrong_secret_control_handle_match) for trial in trials),
    }


def run() -> dict[str, object]:
    """Run held-out deterministic center-phase validation on fresh covers without telemetry-derived decisions."""

    attacks = _crop_attacks()
    trials = tuple(record for trial_index in range(10) for record in evaluate_variant(trial_index, attacks))
    allocation = _selected_allocation()
    return {
        "fixture": "ten fresh seeded 30-second synthetic music-like covers and unchanged 250 ms crop attacks",
        "mapping_mode": "blind_non_oracle_coarse_scan_deterministic_center_phase",
        "decoder_received_oracle_map": False,
        "residual_phase_selection": "deterministic_model_center",
        "allocation": asdict(allocation),
        "protected_codeword_bytes": allocation.payload_bytes + allocation.parity_symbols,
        "carrier_bit_count": 184,
        "physical_carrier_count": 736,
        "profile": asdict(_profile()),
        "payload_thresholds": asdict(_threshold_policy()),
        "validation_cover_seeds": list(range(6700, 6710)),
        "summaries": [
            _summary(attack, tuple(trial for trial in trials if trial.attack_name == attack.name))
            for attack in attacks
        ],
        "trials": [asdict(trial) for trial in trials],
    }


def main() -> None:
    """Print the complete reproducible held-out center-phase validation as formatted JSON."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
