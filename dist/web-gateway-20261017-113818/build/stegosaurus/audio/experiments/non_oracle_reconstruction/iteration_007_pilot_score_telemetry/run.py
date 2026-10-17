"""Run iteration 007: offline contrastive local-pilot score telemetry.

Experiment goal: collect the score distributions needed to design a future
error-versus-erasure policy without guessing wider decoder thresholds. The
contrastive encoder and leading 4-pilot / 12-payload profile remain fixed. For
each physical carrier replica, the decoder selects its higher expected-pilot
candidate without a threshold and records both signed pilot scores, their gap,
selected payload score, and the blind decision. Only after reconstruction does
the experiment join those rows with the retained oracle map and known carrier
bit. It then records the four-copy logical-bit outcome and its deinterleaved
Reed--Solomon byte status.

Pipeline state: iteration 006's declared low threshold grid did not reduce
Reed--Solomon cost below 24.5. This iteration is instrumentation, not a new
encoding mode and not a threshold validation. The generated tables are offline
experimental artifacts; no table, oracle label, or score trace is embedded in
the WAV or required by a production decoder.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from statistics import median

from ....pilot import PcmAudio, SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioWatermarkConfig
from ....transport import BitFramer, CarrierPlan
from ...transport_optimization.iteration_004_four_frame_soft_combine.run import FourFrameEmbedding
from ...transport_optimization.iteration_006_duration_stability_bounds.run import (
    _cover_variant,
    _trial_offset_seconds,
)
from ..iteration_002_local_selection_pilot.run import LocalPilotProfile, _profiles
from ..iteration_005_contrastive_pilot_calibration.run import ContrastivePilotCalibratedExperiment


@dataclass(frozen=True, slots=True)
class TelemetryTrial:
    """Record the three offline telemetry tables and aggregate channel diagnostics for one cover."""

    trial_index: int
    embedding_snr_db: float | None
    physical_carriers: tuple[dict[str, object], ...]
    logical_carriers: tuple[dict[str, object], ...]
    codeword_bytes: tuple[dict[str, object], ...]
    aggregate: dict[str, object] | None
    error: str | None


def _profile() -> LocalPilotProfile:
    """Return the leading contrastive 4-pilot / 12-payload allocation fixed for telemetry collection."""

    return next(profile for profile in _profiles() if profile.name == "small_pilot_4_payload_12")


def _carrier_data_positions(carrier_plan: CarrierPlan) -> tuple[int | None, ...]:
    """Map framed carrier positions to transmitted data-bit positions while marking sync positions absent."""

    framer = BitFramer()
    positions: list[int | None] = []
    remaining_data_bits = carrier_plan.codeword_length * 8
    transmitted_data_index = 0
    while remaining_data_bits:
        positions.extend([None] * len(framer.sync_pattern))
        frame_data_count = min(framer.data_bits_per_frame, remaining_data_bits)
        positions.extend(range(transmitted_data_index, transmitted_data_index + frame_data_count))
        transmitted_data_index += frame_data_count
        remaining_data_bits -= frame_data_count
    if len(positions) != len(carrier_plan.carrier_bits):
        raise ValueError("carrier-plan framing does not match the expected data and sync positions")
    return tuple(positions)


def _physical_rows(
    encoder: ContrastivePilotCalibratedExperiment,
    embedding: FourFrameEmbedding,
    trial_index: int,
) -> tuple[
    tuple[dict[str, object], ...],
    tuple[tuple[float | None, ...], ...],
    tuple[tuple[int | None, ...], ...],
]:
    """Blindly select raw pilot winners and return physical telemetry plus payload evidence by replica."""

    frequencies, spectrum = encoder._pilot._stft(embedding.audio)
    lower_bin, upper_bin = encoder._pilot._frequency_bin_range(frequencies)
    carrier_plan = embedding.carrier_plan
    candidate_maps = tuple(
        encoder._ranked_frame_maps(
            spectrum,
            frame_range,
            carrier_plan.carrier_bits,
            lower_bin,
            upper_bin,
        )
        for frame_range in encoder._replica_ranges(spectrum.shape[1])
    )
    channel = encoder._pilot.schema._channel
    transmitted_to_codeword = channel._interleaver._permutation(carrier_plan.codeword_length * 8)
    carrier_data_positions = _carrier_data_positions(carrier_plan)
    rows: list[dict[str, object]] = []
    replica_payload_scores: list[tuple[float | None, ...]] = []
    replica_selected_frames: list[tuple[int | None, ...]] = []
    for replica_index, replica_rank_maps in enumerate(candidate_maps):
        current_payload_scores: list[float | None] = []
        current_selected_frames: list[int | None] = []
        oracle_map = embedding.replica_frame_indices[replica_index]
        for carrier_index, expected_carrier_bit in enumerate(carrier_plan.carrier_bits):
            candidate_frames = tuple(
                replica_rank_maps[rank][carrier_index]
                for rank in range(encoder._candidate_rank_count)
            )
            expected_pilot_sign = 1.0 if encoder.selection_pilot_bit(replica_index, carrier_index) else -1.0
            signed_pilot_scores = tuple(
                None
                if (score := encoder.pilot_score_at_frame(spectrum, lower_bin, upper_bin, frame_index)) is None
                else expected_pilot_sign * score
                for frame_index in candidate_frames
            )
            score_order = tuple(
                float("-inf") if score is None else score
                for score in signed_pilot_scores
            )
            selected_rank = max(range(encoder._candidate_rank_count), key=lambda rank: (score_order[rank], -rank))
            rival_rank = 1 - selected_rank
            selected_frame = candidate_frames[selected_rank]
            payload_score = encoder._score_at_frame(spectrum, lower_bin, upper_bin, selected_frame)
            payload_sign = 1.0 if expected_carrier_bit else -1.0
            payload_margin = None if payload_score is None else payload_sign * payload_score
            selected_pilot_margin = signed_pilot_scores[selected_rank]
            rival_pilot_margin = signed_pilot_scores[rival_rank]
            pilot_gap = (
                None
                if selected_pilot_margin is None or rival_pilot_margin is None
                else selected_pilot_margin - rival_pilot_margin
            )
            transmitted_data_index = carrier_data_positions[carrier_index]
            codeword_bit_index = (
                None
                if transmitted_data_index is None
                else transmitted_to_codeword[transmitted_data_index]
            )
            oracle_frame = oracle_map[carrier_index]
            row = {
                "trial_index": trial_index,
                "replica_index": replica_index,
                "carrier_index": carrier_index,
                "candidate_rank_0_frame": candidate_frames[0],
                "candidate_rank_1_frame": candidate_frames[1],
                "oracle_frame": oracle_frame,
                "oracle_candidate_covered": oracle_frame in candidate_frames,
                "selected_rank": selected_rank,
                "selected_frame": selected_frame,
                "oracle_map_correct": selected_frame == oracle_frame,
                "expected_pilot_bit": int(expected_pilot_sign > 0),
                "selected_pilot_margin": selected_pilot_margin,
                "rival_pilot_margin": rival_pilot_margin,
                "pilot_gap": pilot_gap,
                "expected_payload_bit": expected_carrier_bit,
                "selected_payload_score": payload_score,
                "selected_payload_margin": payload_margin,
                "physical_payload_correct": None if payload_score is None else int(payload_score >= 0) == expected_carrier_bit,
                "transmitted_data_index": transmitted_data_index,
                "codeword_bit_index": codeword_bit_index,
                "codeword_byte_index": None if codeword_bit_index is None else codeword_bit_index // 8,
            }
            rows.append(row)
            current_payload_scores.append(payload_score)
            current_selected_frames.append(selected_frame)
        replica_payload_scores.append(tuple(current_payload_scores))
        replica_selected_frames.append(tuple(current_selected_frames))
    return tuple(rows), tuple(replica_payload_scores), tuple(replica_selected_frames)


def _logical_rows(
    encoder: ContrastivePilotCalibratedExperiment,
    embedding: FourFrameEmbedding,
    replica_payload_scores: tuple[tuple[float | None, ...], ...],
) -> tuple[tuple[dict[str, object], ...], tuple[int | None, ...]]:
    """Soft-combine raw selected payload scores into threshold-free logical carrier observations."""

    carrier_plan = embedding.carrier_plan
    channel = encoder._pilot.schema._channel
    carrier_data_positions = _carrier_data_positions(carrier_plan)
    transmitted_to_codeword = channel._interleaver._permutation(carrier_plan.codeword_length * 8)
    rows: list[dict[str, object]] = []
    observed_bits: list[int | None] = []
    for carrier_index, expected_carrier_bit in enumerate(carrier_plan.carrier_bits):
        combined_score = encoder._combine_scores(
            replica_payload_scores[replica_index][carrier_index]
            for replica_index in range(encoder._replica_count)
        )
        observed_bit = None if combined_score is None else int(combined_score >= 0)
        transmitted_data_index = carrier_data_positions[carrier_index]
        codeword_bit_index = (
            None
            if transmitted_data_index is None
            else transmitted_to_codeword[transmitted_data_index]
        )
        rows.append(
            {
                "carrier_index": carrier_index,
                "expected_payload_bit": expected_carrier_bit,
                "combined_payload_score": combined_score,
                "observed_bit": observed_bit,
                "logical_payload_correct": None if observed_bit is None else observed_bit == expected_carrier_bit,
                "logical_carrier_erasure": observed_bit is None,
                "accepted_replica_count": sum(
                    replica_payload_scores[replica_index][carrier_index] is not None
                    for replica_index in range(encoder._replica_count)
                ),
                "transmitted_data_index": transmitted_data_index,
                "codeword_bit_index": codeword_bit_index,
                "codeword_byte_index": None if codeword_bit_index is None else codeword_bit_index // 8,
            }
        )
        observed_bits.append(observed_bit)
    return tuple(rows), tuple(observed_bits)


def _byte_rows(
    encoder: ContrastivePilotCalibratedExperiment,
    token: bytes,
    observed_bits: tuple[int | None, ...],
) -> tuple[tuple[dict[str, object], ...], dict[str, object]]:
    """Map logical carrier observations into deinterleaved codeword bytes and RS-cost contributions."""

    channel = encoder._pilot.schema._channel
    expected_codeword = channel._codec.encode(token)
    observation = channel.inspect_carrier_bits(observed_bits, len(token))
    erasure_positions = set(observation.erasure_positions)
    rows: list[dict[str, object]] = []
    unknown_byte_errors = 0
    byte_erasures = 0
    for byte_index, (expected_byte, observed_byte) in enumerate(zip(expected_codeword, observation.codeword)):
        byte_erasure = byte_index in erasure_positions
        unknown_error = not byte_erasure and observed_byte != expected_byte
        rs_cost_contribution = 1 if byte_erasure else 2 if unknown_error else 0
        unknown_byte_errors += int(unknown_error)
        byte_erasures += int(byte_erasure)
        rows.append(
            {
                "codeword_byte_index": byte_index,
                "expected_byte": expected_byte,
                "observed_byte": observed_byte,
                "byte_erasure": byte_erasure,
                "unknown_byte_error": unknown_error,
                "rs_cost_contribution": rs_cost_contribution,
            }
        )
    aggregate = {
        "unknown_byte_errors": unknown_byte_errors,
        "byte_erasures": byte_erasures,
        "rs_cost": 2 * unknown_byte_errors + byte_erasures,
        "rs_parity_budget": channel.parity_symbols,
        "within_rs_budget": 2 * unknown_byte_errors + byte_erasures <= channel.parity_symbols,
        "synchronization_mismatches": observation.synchronization_mismatches,
        "extra_carrier_bits": observation.extra_carrier_bits,
    }
    return tuple(rows), aggregate


def evaluate_trial(trial_index: int) -> TelemetryTrial:
    """Collect blind score telemetry and post-hoc oracle labels for one clean contrastively calibrated cover."""

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
    encoder = ContrastivePilotCalibratedExperiment(pilot, 0.01, _profile())
    try:
        embedding = encoder.embed(source, token)
        physical_rows, replica_payload_scores, _ = _physical_rows(encoder, embedding, trial_index)
        logical_rows, observed_bits = _logical_rows(encoder, embedding, replica_payload_scores)
        byte_rows, aggregate = _byte_rows(encoder, token, observed_bits)
    except Exception as error:
        detail = str(error) or "no message"
        return TelemetryTrial(trial_index, None, (), (), (), None, f"{type(error).__name__}: {detail}")
    return TelemetryTrial(
        trial_index,
        embedding.signal_to_noise_db,
        physical_rows,
        logical_rows,
        byte_rows,
        aggregate,
        None,
    )


def _summary(trials: tuple[TelemetryTrial, ...]) -> dict[str, object]:
    """Summarize threshold-free score telemetry, oracle map outcomes, and codeword RS damage."""

    successful = tuple(trial for trial in trials if trial.aggregate is not None)
    physical_rows = tuple(row for trial in successful for row in trial.physical_carriers)
    logical_rows = tuple(row for trial in successful for row in trial.logical_carriers)
    byte_rows = tuple(row for trial in successful for row in trial.codeword_bytes)
    map_correct_rows = tuple(row for row in physical_rows if bool(row["oracle_map_correct"]))
    map_wrong_rows = tuple(row for row in physical_rows if not bool(row["oracle_map_correct"]))
    return {
        "trial_count": len(trials),
        "execution_failures": sum(trial.error is not None for trial in trials),
        "physical_row_count": len(physical_rows),
        "logical_row_count": len(logical_rows),
        "codeword_byte_row_count": len(byte_rows),
        "median_embedding_snr_db": median(
            trial.embedding_snr_db for trial in successful if trial.embedding_snr_db is not None
        ) if successful else None,
        "oracle_map_accuracy": sum(bool(row["oracle_map_correct"]) for row in physical_rows) / len(physical_rows) if physical_rows else None,
        "median_selected_pilot_margin_correct_map": median(
            float(row["selected_pilot_margin"])
            for row in map_correct_rows
            if row["selected_pilot_margin"] is not None
        ) if map_correct_rows else None,
        "median_selected_pilot_margin_wrong_map": median(
            float(row["selected_pilot_margin"])
            for row in map_wrong_rows
            if row["selected_pilot_margin"] is not None
        ) if map_wrong_rows else None,
        "median_pilot_gap_correct_map": median(
            float(row["pilot_gap"])
            for row in map_correct_rows
            if row["pilot_gap"] is not None
        ) if map_correct_rows else None,
        "median_pilot_gap_wrong_map": median(
            float(row["pilot_gap"])
            for row in map_wrong_rows
            if row["pilot_gap"] is not None
        ) if map_wrong_rows else None,
        "logical_bit_errors": sum(row["logical_payload_correct"] is False for row in logical_rows),
        "logical_bit_erasures": sum(bool(row["logical_carrier_erasure"]) for row in logical_rows),
        "unknown_byte_errors": sum(bool(row["unknown_byte_error"]) for row in byte_rows),
        "byte_erasures": sum(bool(row["byte_erasure"]) for row in byte_rows),
        "median_rs_cost": median(int(trial.aggregate["rs_cost"]) for trial in successful) if successful else None,
        "trials_within_rs_budget": sum(bool(trial.aggregate["within_rs_budget"]) for trial in successful),
    }


def run() -> dict[str, object]:
    """Collect three-layer offline telemetry from ten clean contrastively calibrated cover variants."""

    trials = tuple(evaluate_trial(trial_index) for trial_index in range(10))
    return {
        "fixture": "ten seeded 30-second music-like cover variants and virtual timeline offsets",
        "mapping_mode": "offline_non_oracle_pilot_score_telemetry",
        "decoder_received_oracle_map": False,
        "oracle_labels_used_after_reconstruction_only": True,
        "profile": asdict(_profile()),
        "carrier_band_hz": [500.0, 3800.0],
        "relative_difference": 0.95,
        "parity_symbols": 12,
        "repetition": 4,
        "summary": _summary(trials),
        "trials": [asdict(trial) for trial in trials],
    }


def main() -> None:
    """Print the complete reproducible offline pilot-score telemetry archive as formatted JSON."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
