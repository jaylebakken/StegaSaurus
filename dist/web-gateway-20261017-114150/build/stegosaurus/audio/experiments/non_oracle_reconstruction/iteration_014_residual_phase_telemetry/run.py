"""Run iteration 014: per-phase residual sample-alignment telemetry.

Experiment goal: collect calibration data after iteration 013 found that an
inherited winner-gap threshold rejected all nearby sample-phase candidates.
This runner retains the unchanged secret-pilot coarse frame scan and bounded
one-edge-crop phase geometry, but does not accept or reject a residual phase.
Instead it reconstructs every feasible phase candidate and records pilot
evidence, phase rank, post-hoc watermarked-label distance, exact payload
recovery, byte-level Reed--Solomon damage, and independently scanned controls.

Pipeline state: transport remains a 6-byte opaque registry handle protected by
14 Reed--Solomon parity symbols. The 30-second synthetic crop fixture, frozen
contrastive encoder, four-pilot / twelve-payload allocation, and crop attacks
are held fixed solely to obtain direct calibration telemetry. No resulting
threshold is installed here; any future policy must validate on fresh covers.
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import asdict, dataclass
import json
from statistics import median

from ....pilot import SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioWatermarkConfig, CarrierPlan
from ...transport_optimization.iteration_004_four_frame_soft_combine.run import _extraction_record
from ...transport_optimization.iteration_006_duration_stability_bounds.run import (
    _cover_variant,
    _trial_offset_seconds,
)
from ..iteration_002_local_selection_pilot.run import LocalPilotProfile, _profiles
from ..iteration_005_contrastive_pilot_calibration.run import ContrastivePilotCalibratedExperiment
from ..iteration_010_constant_codeword_allocation.run import CodewordAllocation, _allocations
from ..iteration_011_blind_attack_validation.run import AttackDefinition, _attack_definitions
from ..iteration_013_sample_phase_crop_realignment.run import (
    SamplePhaseLocalPilotDecoder,
    _measured_extraction,
    _oracle_crop_labels,
    _threshold_policy,
)


@dataclass(frozen=True, slots=True)
class ResidualTelemetryTrial:
    """Record one watermarked crop's blind coarse result and whether residual candidates were available."""

    attack_name: str
    trial_index: int
    cover_seed: int
    virtual_timeline_offset_seconds: float
    decoder_received_oracle_map: bool
    oracle_crop_offset_frames: int
    oracle_analysis_phase_samples: int
    coarse_offset_frames: int | None
    coarse_scan_accepted: bool
    residual_phase_candidate_count: int
    embedding_snr_db: float | None
    error: str | None


@dataclass(frozen=True, slots=True)
class ResidualTelemetryRow:
    """Record one raw phase candidate's pilot evidence and payload/control outcome without policy acceptance."""

    attack_name: str
    trial_index: int
    stream: str
    coarse_offset_frames: int | None
    coarse_scan_accepted: bool
    phase_candidate_count: int
    phase_samples: int
    phase_evidence_rank: int
    mean_pilot_evidence: float | None
    posthoc_absolute_phase_error_samples: int | None
    measurement: dict[str, object] | None
    exact_known_handle_match: bool | None
    error: str | None


def _selected_allocation() -> CodewordAllocation:
    """Return the fixed six-byte registry handle and fourteen-parity allocation under calibration."""

    return next(allocation for allocation in _allocations() if allocation.name == "registry_handle_6_parity_14")


def _profile() -> LocalPilotProfile:
    """Return the frozen four-pilot / twelve-payload contrastive allocation."""

    return next(profile for profile in _profiles() if profile.name == "small_pilot_4_payload_12")


def _crop_attacks() -> tuple[AttackDefinition, ...]:
    """Return exactly the fixed leading and trailing 250 ms crop attacks from prior direct comparisons."""

    crop_names = {"leading_crop_025s", "trailing_crop_025s"}
    return tuple(attack for attack in _attack_definitions() if attack.name in crop_names)


def _phase_ranks(phase_scores) -> dict[int, int]:
    """Assign stable one-based evidence ranks to each residual phase without using post-hoc payload labels."""

    ranked = sorted(
        phase_scores,
        key=lambda score: (
            float("-inf") if score.mean_pilot_evidence is None else float(score.mean_pilot_evidence),
            -abs(score.phase_samples),
            -score.phase_samples,
        ),
        reverse=True,
    )
    return {score.phase_samples: rank for rank, score in enumerate(ranked, start=1)}


def _phase_rows(
    decoder: SamplePhaseLocalPilotDecoder,
    audio,
    carrier_plan: CarrierPlan,
    attack_name: str,
    trial_index: int,
    stream: str,
    known_token: bytes,
    embedding,
    posthoc_phase: int | None,
) -> tuple[int | None, bool, tuple[ResidualTelemetryRow, ...]]:
    """Collect all residual candidates after blind coarse synchronization for one watermarked or control stream."""

    frequencies, spectrum = decoder._pilot._stft(audio)
    lower_bin, upper_bin = decoder._pilot._frequency_bin_range(frequencies)
    nominal_frame_count = decoder._coarse_decoder._nominal_frame_count(audio.sample_rate)
    coarse = decoder._coarse_decoder._select_offset(
        spectrum,
        carrier_plan,
        lower_bin,
        upper_bin,
        nominal_frame_count,
    )
    if coarse.selected_offset_frames is None:
        return None, False, ()
    residual, spectra = decoder._select_phase(
        audio,
        carrier_plan,
        lower_bin,
        upper_bin,
        nominal_frame_count,
        coarse.selected_offset_frames,
    )
    phase_ranks = _phase_ranks(residual.searched_scores)
    rows: list[ResidualTelemetryRow] = []
    for phase_score in residual.searched_scores:
        try:
            reconstruction = decoder._coarse_decoder._reconstruct_at_offset(
                spectra[phase_score.phase_samples],
                carrier_plan,
                lower_bin,
                upper_bin,
                nominal_frame_count,
                coarse.selected_offset_frames,
            )
            exact_match = reconstruction.extraction.recovery.token == known_token
            measurement = (
                _extraction_record(
                    decoder._encoder,
                    embedding,
                    _measured_extraction(reconstruction, known_token),
                )
                if stream == "watermarked"
                else None
            )
            error = None
        except Exception as exception:
            detail = str(exception) or "no message"
            exact_match = None
            measurement = None
            error = f"{type(exception).__name__}: {detail}"
        rows.append(
            ResidualTelemetryRow(
                attack_name,
                trial_index,
                stream,
                coarse.selected_offset_frames,
                coarse.accepted,
                len(residual.searched_scores),
                phase_score.phase_samples,
                phase_ranks[phase_score.phase_samples],
                phase_score.mean_pilot_evidence,
                abs(phase_score.phase_samples - posthoc_phase) if posthoc_phase is not None else None,
                measurement,
                exact_match,
                error,
            )
        )
    return coarse.selected_offset_frames, coarse.accepted, tuple(rows)


def evaluate_variant(
    trial_index: int,
    attacks: Iterable[AttackDefinition],
) -> tuple[tuple[ResidualTelemetryTrial, ...], tuple[ResidualTelemetryRow, ...]]:
    """Embed one direct-comparison cover and collect all watermarked/control phase telemetry for each crop."""

    allocation = _selected_allocation()
    token = allocation.token()
    cover_seed = 6600 + trial_index
    timeline_offset = _trial_offset_seconds(400 + trial_index)
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
    decoder = SamplePhaseLocalPilotDecoder(encoder)
    try:
        embedding = encoder.embed(source, token)
        wrong_pilot = SpectralAudioPilot(b"wrong-audio-pilot-test-key", pilot_config, watermark_config)
        wrong_encoder = ContrastivePilotCalibratedExperiment(wrong_pilot, 0.01, _profile())
        wrong_decoder = SamplePhaseLocalPilotDecoder(wrong_encoder)
        wrong_plan = wrong_pilot.schema.plan_attribution(token)
    except Exception as exception:
        detail = str(exception) or "no message"
        trials = tuple(
            ResidualTelemetryTrial(
                attack.name, trial_index, cover_seed, timeline_offset, False, *_oracle_crop_labels(attack),
                None, False, 0, None, f"{type(exception).__name__}: {detail}",
            )
            for attack in attack_values
        )
        return trials, ()
    trials: list[ResidualTelemetryTrial] = []
    rows: list[ResidualTelemetryRow] = []
    for attack in attack_values:
        try:
            seed = 7000 + trial_index
            watermarked_audio = attack.transform(embedding.audio, seed)
            unwatermarked_audio = attack.transform(source, seed)
            wrong_secret_audio = attack.transform(embedding.audio, seed)
            coarse_offset, coarse_accepted, watermarked_rows = _phase_rows(
                decoder,
                watermarked_audio,
                embedding.carrier_plan,
                attack.name,
                trial_index,
                "watermarked",
                token,
                embedding,
                _oracle_crop_labels(attack)[1],
            )
            _, _, unwatermarked_rows = _phase_rows(
                decoder,
                unwatermarked_audio,
                embedding.carrier_plan,
                attack.name,
                trial_index,
                "unwatermarked",
                token,
                embedding,
                None,
            )
            _, _, wrong_secret_rows = _phase_rows(
                wrong_decoder,
                wrong_secret_audio,
                wrong_plan,
                attack.name,
                trial_index,
                "wrong_secret",
                token,
                embedding,
                None,
            )
        except Exception as exception:
            detail = str(exception) or "no message"
            oracle_offset, oracle_phase = _oracle_crop_labels(attack)
            trials.append(
                ResidualTelemetryTrial(
                    attack.name, trial_index, cover_seed, timeline_offset, False, oracle_offset, oracle_phase,
                    None, False, 0, embedding.signal_to_noise_db, f"{type(exception).__name__}: {detail}",
                )
            )
            continue
        oracle_offset, oracle_phase = _oracle_crop_labels(attack)
        trials.append(
            ResidualTelemetryTrial(
                attack.name,
                trial_index,
                cover_seed,
                timeline_offset,
                False,
                oracle_offset,
                oracle_phase,
                coarse_offset,
                coarse_accepted,
                len(watermarked_rows),
                embedding.signal_to_noise_db,
                None,
            )
        )
        rows.extend(watermarked_rows)
        rows.extend(unwatermarked_rows)
        rows.extend(wrong_secret_rows)
    return tuple(trials), tuple(rows)


def _summary(
    attack: AttackDefinition,
    trials: tuple[ResidualTelemetryTrial, ...],
    telemetry: tuple[ResidualTelemetryRow, ...],
) -> dict[str, object]:
    """Aggregate phase-rank, post-hoc recovery, RS-damage, and exact-control telemetry for one crop attack."""

    watermarked = tuple(row for row in telemetry if row.stream == "watermarked")
    controls = tuple(row for row in telemetry if row.stream != "watermarked")
    watermarked_by_trial: dict[int, list[ResidualTelemetryRow]] = defaultdict(list)
    for row in watermarked:
        watermarked_by_trial[row.trial_index].append(row)
    best_rows = tuple(
        next(row for row in rows if row.phase_evidence_rank == 1)
        for rows in watermarked_by_trial.values()
        if any(row.phase_evidence_rank == 1 for row in rows)
    )
    oracle_rows = tuple(
        row
        for trial in trials
        for row in watermarked_by_trial.get(trial.trial_index, ())
        if row.phase_samples == trial.oracle_analysis_phase_samples
    )
    payload_rows = tuple(row for row in watermarked if row.measurement is not None)
    return {
        "attack_name": attack.name,
        "trial_count": len(trials),
        "execution_failures": sum(trial.error is not None for trial in trials),
        "watermarked_coarse_acceptances": sum(trial.coarse_scan_accepted for trial in trials),
        "watermarked_phase_rows": len(watermarked),
        "median_phase_evidence": median(
            float(row.mean_pilot_evidence) for row in watermarked if row.mean_pilot_evidence is not None
        ) if watermarked else None,
        "best_evidence_phase_exact_label_matches": sum(
            row.posthoc_absolute_phase_error_samples == 0 for row in best_rows
        ),
        "best_evidence_phase_exact_recoveries": sum(bool(row.exact_known_handle_match) for row in best_rows),
        "oracle_label_phase_exact_recoveries": sum(bool(row.exact_known_handle_match) for row in oracle_rows),
        "oracle_label_phase_median_rs_cost": median(
            int(row.measurement["rs_error_cost"])
            for row in oracle_rows
            if row.measurement is not None
        ) if any(row.measurement is not None for row in oracle_rows) else None,
        "minimum_phase_rs_cost_median": median(
            min(int(row.measurement["rs_error_cost"]) for row in rows if row.measurement is not None)
            for rows in watermarked_by_trial.values()
            if any(row.measurement is not None for row in rows)
        ) if payload_rows else None,
        "control_phase_rows": len(controls),
        "control_exact_known_handle_matches": sum(bool(row.exact_known_handle_match) for row in controls),
    }


def run() -> dict[str, object]:
    """Run complete residual-phase telemetry over the direct-comparison crop fixture without choosing a new policy."""

    attacks = _crop_attacks()
    evaluated = tuple(evaluate_variant(trial_index, attacks) for trial_index in range(10))
    trials = tuple(trial for variant_trials, _ in evaluated for trial in variant_trials)
    telemetry = tuple(row for _, variant_rows in evaluated for row in variant_rows)
    allocation = _selected_allocation()
    return {
        "fixture": "iteration 013's direct-comparison synthetic crop fixture, retained for telemetry only",
        "mapping_mode": "blind_non_oracle_residual_phase_telemetry",
        "decoder_received_oracle_map": False,
        "posthoc_labels": "Residual phase and crop offset labels are evaluation fields, not decoder inputs.",
        "allocation": asdict(allocation),
        "protected_codeword_bytes": allocation.payload_bytes + allocation.parity_symbols,
        "carrier_bit_count": 184,
        "physical_carrier_count": 736,
        "profile": asdict(_profile()),
        "payload_thresholds": asdict(_threshold_policy()),
        "validation_cover_seeds": list(range(6600, 6610)),
        "summaries": [
            _summary(
                attack,
                tuple(trial for trial in trials if trial.attack_name == attack.name),
                tuple(row for row in telemetry if row.attack_name == attack.name),
            )
            for attack in attacks
        ],
        "trials": [asdict(trial) for trial in trials],
        "phase_telemetry": [asdict(row) for row in telemetry],
    }


def main() -> None:
    """Print the complete reproducible residual-phase telemetry archive as formatted JSON."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
