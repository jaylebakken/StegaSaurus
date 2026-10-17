"""Run iteration 016: deterministic center-neighborhood payload soft combining.

Experiment goal: compare the held-out single deterministic center phase with a
predeclared five-phase robust median combiner around that same center. The
alignment path is unchanged: a secret-pilot coarse frame scan accepts or
rejects a bounded source offset, then the one-edge duration model supplies the
center analysis origin. The neighborhood strategy uses exactly center minus
eight, minus four, zero, plus four, and plus eight samples; it neither ranks
phase pilots nor searches by payload outcome.

Pipeline state: the 6-byte opaque handle, 14 Reed--Solomon parity symbols,
contrastive local-pilot encoder, four-replica channel, band, thresholds, crop
attacks, and negative controls remain unchanged. Fresh seeds `6800-6809` are
used to distinguish combination effects from the iteration 015 validation.
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
from ..iteration_002_local_selection_pilot.run import LocalPilotProfile, _control_token_match, _profiles
from ..iteration_005_contrastive_pilot_calibration.run import ContrastivePilotCalibratedExperiment
from ..iteration_010_constant_codeword_allocation.run import CodewordAllocation, _allocations
from ..iteration_011_blind_attack_validation.run import AttackDefinition, _attack_definitions
from ..iteration_013_sample_phase_crop_realignment.run import SamplePhaseLocalPilotDecoder
from ..iteration_014_residual_phase_telemetry.run import _threshold_policy


@dataclass(frozen=True, slots=True)
class CombinationStrategy:
    """Declare one fixed set of sample-phase offsets and its payload-score aggregation rule."""

    name: str
    phase_offsets_samples: tuple[int, ...]
    aggregation: str


@dataclass(frozen=True, slots=True)
class StrategyDecode:
    """Record coarse synchronization, deterministic center feasibility, and one strategy's combined extraction."""

    coarse_offset_frames: int | None
    coarse_scan_accepted: bool
    deterministic_center_phase_samples: int | None
    center_phase_feasible: bool
    extraction: FourFrameExtraction


@dataclass(frozen=True, slots=True)
class SoftCombineTrial:
    """Record one fresh crop, strategy result, RS measurement, and exact-handle controls."""

    attack_name: str
    strategy_name: str
    phase_offsets_samples: tuple[int, ...]
    aggregation: str
    trial_index: int
    cover_seed: int
    virtual_timeline_offset_seconds: float
    decoder_received_oracle_map: bool
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
    """Return the fixed six-byte opaque handle and fourteen-parity allocation under test."""

    return next(allocation for allocation in _allocations() if allocation.name == "registry_handle_6_parity_14")


def _profile() -> LocalPilotProfile:
    """Return the frozen contrastive four-pilot / twelve-payload allocation."""

    return next(profile for profile in _profiles() if profile.name == "small_pilot_4_payload_12")


def _crop_attacks() -> tuple[AttackDefinition, ...]:
    """Return the unchanged bounded leading and trailing crop transformations."""

    crop_names = {"leading_crop_025s", "trailing_crop_025s"}
    return tuple(attack for attack in _attack_definitions() if attack.name in crop_names)


def _strategies() -> tuple[CombinationStrategy, ...]:
    """Return the predeclared single-center baseline and fixed five-phase robust median combiner."""

    return (
        CombinationStrategy("center_only", (0,), "identity"),
        CombinationStrategy("median_neighborhood_5", (-8, -4, 0, 4, 8), "median"),
    )


class CenterNeighborhoodDecoder:
    """Decode fixed center-neighborhood payload evidence after unchanged blind coarse synchronization."""

    def __init__(self, encoder: ContrastivePilotCalibratedExperiment) -> None:
        """Initialize the existing phase helper without exposing phase evidence or label selection to decoding."""

        self._encoder = encoder
        self._pilot = encoder._pilot
        self._phase_helper = SamplePhaseLocalPilotDecoder(encoder)

    def decode(self, audio: PcmAudio, carrier_plan: CarrierPlan, strategy: CombinationStrategy) -> StrategyDecode:
        """Run coarse synchronization, derive the fixed center, and extract identity or median-combined payload evidence."""

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
            return StrategyDecode(
                None,
                False,
                None,
                False,
                self._phase_helper._coarse_decoder._erasure_reconstruction(carrier_plan).extraction,
            )
        center_phase = self._phase_helper._edge_crop_phase_center(audio, coarse.selected_offset_frames)
        if center_phase is None:
            return StrategyDecode(
                coarse.selected_offset_frames,
                True,
                None,
                False,
                self._phase_helper._coarse_decoder._erasure_reconstruction(carrier_plan).extraction,
            )
        phase_extractions = tuple(
            self._phase_extraction(
                audio,
                carrier_plan,
                lower_bin,
                upper_bin,
                nominal_frame_count,
                coarse.selected_offset_frames,
                center_phase + phase_offset,
            )
            for phase_offset in strategy.phase_offsets_samples
        )
        extraction = (
            phase_extractions[0]
            if strategy.aggregation == "identity"
            else self._median_combined_extraction(phase_extractions, carrier_plan)
        )
        return StrategyDecode(coarse.selected_offset_frames, True, center_phase, True, extraction)

    def _phase_extraction(
        self,
        audio: PcmAudio,
        carrier_plan: CarrierPlan,
        lower_bin: int,
        upper_bin: int,
        nominal_frame_count: int,
        coarse_offset_frames: int,
        phase_samples: int,
    ) -> FourFrameExtraction:
        """Reframe one deterministic neighborhood phase and return its ordinary blind four-replica extraction."""

        reframed_audio = self._phase_helper._reframe_audio(audio, phase_samples)
        frequencies, spectrum = self._pilot._stft(reframed_audio)
        lower_bin, upper_bin = self._pilot._frequency_bin_range(frequencies)
        reconstruction = self._phase_helper._coarse_decoder._reconstruct_at_offset(
            spectrum,
            carrier_plan,
            lower_bin,
            upper_bin,
            nominal_frame_count,
            coarse_offset_frames,
        )
        return reconstruction.extraction

    def _median_combined_extraction(
        self,
        phase_extractions: tuple[FourFrameExtraction, ...],
        carrier_plan: CarrierPlan,
    ) -> FourFrameExtraction:
        """Take the median available payload score per replica/carrier before unchanged four-replica extraction."""

        replica_count = len(phase_extractions[0].replica_scores)
        carrier_count = len(carrier_plan.carrier_bits)
        combined_scores = tuple(
            tuple(
                median(scores)
                if (scores := tuple(
                    extraction.replica_scores[replica_index][carrier_index]
                    for extraction in phase_extractions
                    if extraction.replica_scores[replica_index][carrier_index] is not None
                ))
                else None
                for carrier_index in range(carrier_count)
            )
            for replica_index in range(replica_count)
        )
        return self._phase_helper._coarse_decoder._extract(combined_scores, carrier_plan)


def _known_measurement(extraction: FourFrameExtraction, token: bytes) -> FourFrameExtraction:
    """Attach exact known-token equality to a strategy extraction for shared byte-level measurement recording."""

    return FourFrameExtraction(
        extraction.replica_scores,
        extraction.combined_scores,
        extraction.observed_carrier_bits,
        extraction.known_bit_errors,
        extraction.carrier_erasures,
        extraction.recovery,
        extraction.recovery.token == token,
    )


def evaluate_variant(trial_index: int, attacks: Iterable[AttackDefinition]) -> tuple[SoftCombineTrial, ...]:
    """Embed one fresh cover and compare all fixed combination strategies for each crop and paired controls."""

    allocation = _selected_allocation()
    token = allocation.token()
    cover_seed = 6800 + trial_index
    timeline_offset = _trial_offset_seconds(600 + trial_index)
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
    strategies = _strategies()
    pilot = SpectralAudioPilot(b"audio-pilot-test-key", pilot_config, watermark_config)
    encoder = ContrastivePilotCalibratedExperiment(pilot, 0.01, _profile())
    decoder = CenterNeighborhoodDecoder(encoder)
    try:
        embedding = encoder.embed(source, token)
        wrong_pilot = SpectralAudioPilot(b"wrong-audio-pilot-test-key", pilot_config, watermark_config)
        wrong_encoder = ContrastivePilotCalibratedExperiment(wrong_pilot, 0.01, _profile())
        wrong_decoder = CenterNeighborhoodDecoder(wrong_encoder)
        wrong_plan = wrong_pilot.schema.plan_attribution(token)
    except Exception as error:
        detail = str(error) or "no message"
        return tuple(
            SoftCombineTrial(
                attack.name, strategy.name, strategy.phase_offsets_samples, strategy.aggregation, trial_index,
                cover_seed, timeline_offset, False, None, False, None, False, None, None, None, None,
                f"{type(error).__name__}: {detail}",
            )
            for attack in attack_values
            for strategy in strategies
        )
    records: list[SoftCombineTrial] = []
    for attack in attack_values:
        for strategy in strategies:
            try:
                seed = 7200 + trial_index
                attacked_audio = attack.transform(embedding.audio, seed)
                decoded = decoder.decode(attacked_audio, embedding.carrier_plan, strategy)
                measurement = _extraction_record(encoder, embedding, _known_measurement(decoded.extraction, token))
                unwatermarked = decoder.decode(attack.transform(source, seed), embedding.carrier_plan, strategy)
                wrong_secret = wrong_decoder.decode(attack.transform(embedding.audio, seed), wrong_plan, strategy)
            except Exception as error:
                detail = str(error) or "no message"
                records.append(
                    SoftCombineTrial(
                        attack.name, strategy.name, strategy.phase_offsets_samples, strategy.aggregation, trial_index,
                        cover_seed, timeline_offset, False, None, False, None, False, embedding.signal_to_noise_db,
                        None, None, None, f"{type(error).__name__}: {detail}",
                    )
                )
                continue
            records.append(
                SoftCombineTrial(
                    attack.name,
                    strategy.name,
                    strategy.phase_offsets_samples,
                    strategy.aggregation,
                    trial_index,
                    cover_seed,
                    timeline_offset,
                    False,
                    decoded.coarse_offset_frames,
                    decoded.coarse_scan_accepted,
                    decoded.deterministic_center_phase_samples,
                    decoded.center_phase_feasible,
                    embedding.signal_to_noise_db,
                    measurement,
                    unwatermarked.extraction.recovery.token == token,
                    wrong_secret.extraction.recovery.token == token,
                    None,
                )
            )
    return tuple(records)


def _summary(
    attack: AttackDefinition,
    strategy: CombinationStrategy,
    trials: tuple[SoftCombineTrial, ...],
) -> dict[str, object]:
    """Aggregate A/B recovery, center feasibility, RS damage, and controls for one crop and fixed strategy."""

    measurements = tuple(trial.measurement for trial in trials if trial.measurement is not None)
    feasible = tuple(trial for trial in trials if trial.center_phase_feasible)
    return {
        "attack_name": attack.name,
        "strategy_name": strategy.name,
        "phase_offsets_samples": list(strategy.phase_offsets_samples),
        "aggregation": strategy.aggregation,
        "trial_count": len(trials),
        "execution_failures": sum(trial.error is not None for trial in trials),
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
    """Run the fresh-cover center-only versus fixed-neighborhood median-combination study."""

    attacks = _crop_attacks()
    strategies = _strategies()
    trials = tuple(record for trial_index in range(10) for record in evaluate_variant(trial_index, attacks))
    allocation = _selected_allocation()
    return {
        "fixture": "ten fresh seeded 30-second synthetic music-like covers and unchanged 250 ms crop attacks",
        "mapping_mode": "blind_non_oracle_deterministic_center_neighborhood_combination",
        "decoder_received_oracle_map": False,
        "phase_selection": "deterministic_model_center_with_fixed_offsets",
        "allocation": asdict(allocation),
        "protected_codeword_bytes": allocation.payload_bytes + allocation.parity_symbols,
        "carrier_bit_count": 184,
        "physical_carrier_count": 736,
        "profile": asdict(_profile()),
        "payload_thresholds": asdict(_threshold_policy()),
        "validation_cover_seeds": list(range(6800, 6810)),
        "strategies": [asdict(strategy) for strategy in strategies],
        "summaries": [
            _summary(
                attack,
                strategy,
                tuple(
                    trial
                    for trial in trials
                    if trial.attack_name == attack.name and trial.strategy_name == strategy.name
                ),
            )
            for attack in attacks
            for strategy in strategies
        ],
        "trials": [asdict(trial) for trial in trials],
    }


def main() -> None:
    """Print the complete reproducible fresh-cover center-neighborhood combination study as formatted JSON."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
