"""Run iteration 030: measure carrier reliability at a failed and recovered trailing crop.

Goal: determine whether the remaining non-oracle trailing abstention is driven
primarily by local candidate-map errors or by low payload evidence after a
correct candidate frame is selected. The diagnostic replays one failed seed
(`7600`) and one recovered seed (`7601`) from iteration 028's fresh fixture.

For each logical carrier, record post-hoc map correctness, usable replica
count, combined score magnitude, erasure status, and expected-bit agreement.
The retained encoder map and known bits are used only for measurement. The
decoder itself remains the iteration 021 duration-feasible coarse bank.

Pipeline state: 4-byte handle, 16 parity bytes, 20 protected bytes, 184
logical carriers, four replicas, fixed local pilot thresholds, and the named
250 ms trailing crop are unchanged. This is a telemetry experiment, not a
carrier-strength or robustness result.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import asdict, dataclass
import json
import math
from statistics import median

from ....pilot import SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioWatermarkConfig
from ...transport_optimization.iteration_006_duration_stability_bounds.run import _cover_variant, _trial_offset_seconds
from ..iteration_005_contrastive_pilot_calibration.run import ContrastivePilotCalibratedExperiment
from ..iteration_019_registry_handle_parity_tradeoff.run import _crop_attacks, _profile
from ..iteration_021_coarse_hypothesis_bank.run import CoarseHypothesisBankDecoder, _allocation


@dataclass(frozen=True, slots=True)
class CarrierTelemetry:
    """Capture post-hoc selection and payload evidence for one logical carrier across four replicas."""

    carrier_index: int
    selected_replica_count: int
    map_correct_replica_count: int
    combined_score: float | None
    observed_bit: int | None
    expected_bit: int
    bit_correct: bool | None


@dataclass(frozen=True, slots=True)
class CaseTelemetry:
    """Record one replayed cover, its leading blind hypothesis, aggregate groups, and every carrier row."""

    cover_seed: int
    recovered_payload: bool
    carrier_count: int
    map_correct_rate: float | None
    groups: dict[str, dict[str, float | int | None]]
    carriers: tuple[CarrierTelemetry, ...]


def _case(cover_seed: int) -> CaseTelemetry:
    """Replay one named trailing crop and produce post-hoc carrier reliability telemetry from its best blind hypothesis."""

    allocation = _allocation()
    handle = allocation.handle()
    source = _cover_variant(30, cover_seed, _trial_offset_seconds(1500 + cover_seed - 7600))
    configuration = SpectralPilotConfig(minimum_frequency_hz=500.0, maximum_frequency_hz=3800.0, relative_difference=0.95)
    watermark = AudioWatermarkConfig(attribution_token_bytes=4, parity_symbols=16)
    pilot = SpectralAudioPilot(b"audio-pilot-test-key", configuration, watermark)
    encoder = ContrastivePilotCalibratedExperiment(pilot, 0.01, _profile())
    embedding = encoder.embed(source, handle)
    attack = next(item for item in _crop_attacks() if item.name == "trailing_crop_025s")
    decision = CoarseHypothesisBankDecoder(encoder).reconstruct(
        attack.transform(embedding.audio, 8000 + cover_seed - 7600),
        embedding.carrier_plan,
    )
    if not decision.hypotheses:
        raise RuntimeError("telemetry case produced no duration-feasible blind hypothesis")
    hypothesis = decision.selected or decision.hypotheses[0]
    extraction = hypothesis.reconstruction.extraction
    expected_bits = embedding.carrier_plan.carrier_bits
    rows: list[CarrierTelemetry] = []
    for carrier_index, expected_bit in enumerate(expected_bits):
        selected = tuple(replica[carrier_index] for replica in hypothesis.reconstruction.selected_frame_indices)
        expected = tuple(replica[carrier_index] for replica in embedding.replica_frame_indices)
        observed = extraction.observed_carrier_bits[carrier_index]
        rows.append(CarrierTelemetry(
            carrier_index,
            sum(frame is not None for frame in selected),
            sum(frame == expected_frame for frame, expected_frame in zip(selected, expected) if frame is not None),
            extraction.combined_scores[carrier_index],
            observed,
            expected_bit,
            None if observed is None else observed == expected_bit,
        ))
    map_total = sum(row.selected_replica_count for row in rows)
    map_correct = sum(row.map_correct_replica_count for row in rows)
    return CaseTelemetry(
        cover_seed,
        extraction.recovery.token == handle,
        len(rows),
        map_correct / map_total if map_total else None,
        _groups(tuple(rows)),
        tuple(rows),
    )


def _groups(rows: tuple[CarrierTelemetry, ...]) -> dict[str, dict[str, float | int | None]]:
    """Aggregate carrier outcomes by whether every selected replica agrees with the retained map post-hoc."""

    grouped: dict[str, list[CarrierTelemetry]] = defaultdict(list)
    for row in rows:
        label = "fully_map_correct" if row.selected_replica_count and row.selected_replica_count == row.map_correct_replica_count else "map_disputed"
        grouped[label].append(row)
    return {label: _aggregate(values) for label, values in grouped.items()}


def _aggregate(rows: list[CarrierTelemetry]) -> dict[str, float | int | None]:
    """Summarize selection coverage, score strength, erasures, and observed-bit error rate for one carrier group."""

    scores = tuple(abs(row.combined_score) for row in rows if row.combined_score is not None and math.isfinite(row.combined_score))
    observed = tuple(row for row in rows if row.observed_bit is not None)
    return {
        "carrier_count": len(rows),
        "median_selected_replicas": median(row.selected_replica_count for row in rows) if rows else None,
        "median_map_correct_replicas": median(row.map_correct_replica_count for row in rows) if rows else None,
        "median_absolute_combined_score": median(scores) if scores else None,
        "carrier_erasures": sum(row.observed_bit is None for row in rows),
        "observed_bit_errors": sum(row.bit_correct is False for row in observed),
        "observed_bit_count": len(observed),
    }


def run() -> dict[str, object]:
    """Compare the selected failed and recovered trailing cases and return machine-readable carrier telemetry."""

    cases = (_case(7600), _case(7601))
    return {
        "goal": "separate blind local-map reliability from payload-score reliability before changing carrier strength or redundancy",
        "decoder_received_oracle_map": False,
        "cases": [asdict(case) for case in cases],
    }


def main() -> None:
    """Print the preliminary carrier telemetry for archival redirection to ``RESULTS.json``."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
