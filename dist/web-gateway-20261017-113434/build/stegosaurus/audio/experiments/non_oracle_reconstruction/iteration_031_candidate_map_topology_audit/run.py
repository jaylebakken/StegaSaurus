"""Run iteration 031: classify blind candidate-map errors before changing selection policy.

Goal: compare the failed trailing seed 7600 and recovered seed 7601 at the
replica/carrier level. For every blind local selection, determine post-hoc
whether the true encoder frame was present in the decoder's two-candidate map,
which rank contained it, which rank was selected, and the selected-to-true
frame displacement.

Interpretation guide:
    true frame absent -> enlarge or improve candidate generation/tracking
    true frame present but wrong rank selected -> improve pilot discrimination
    common displacement -> add timeline-consistent map regularization

The true map is an evaluation label only. The actual decoder remains unchanged;
this diagnostic makes no waveform, candidate, or threshold modification.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass
import json
from statistics import median

from ....pilot import SpectralAudioPilot, SpectralPilotConfig
from ....schema import AudioWatermarkConfig
from ...transport_optimization.iteration_006_duration_stability_bounds.run import _cover_variant, _trial_offset_seconds
from ..iteration_005_contrastive_pilot_calibration.run import ContrastivePilotCalibratedExperiment
from ..iteration_019_registry_handle_parity_tradeoff.run import _crop_attacks, _profile
from ..iteration_021_coarse_hypothesis_bank.run import CoarseHypothesisBankDecoder, _allocation


@dataclass(frozen=True, slots=True)
class SelectionTopology:
    """Record one replica/carrier blind selection relative to retained encoder-map labels."""

    replica_index: int
    carrier_index: int
    true_frame: int
    candidate_frames: tuple[int | None, int | None]
    true_rank: int | None
    selected_rank: int | None
    selected_frame: int | None
    selected_displacement_frames: int | None


@dataclass(frozen=True, slots=True)
class CaseTopology:
    """Return all topology rows and compact aggregate evidence for one replayed trailing-crop source."""

    cover_seed: int
    recovered_payload: bool
    aggregate: dict[str, int | float | None]
    selections: tuple[SelectionTopology, ...]


def _case(cover_seed: int) -> CaseTopology:
    """Replay a known trailing crop and compare its leading blind hypothesis against the retained map post-hoc."""

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
        raise RuntimeError("topology case produced no duration-feasible blind hypothesis")
    reconstruction = (decision.selected or decision.hypotheses[0]).reconstruction
    rows: list[SelectionTopology] = []
    for replica_index, expected_frames in enumerate(embedding.replica_frame_indices):
        rank_zero, rank_one = reconstruction.candidate_frame_indices[replica_index]
        selected_ranks = reconstruction.selected_candidate_ranks[replica_index]
        selected_frames = reconstruction.selected_frame_indices[replica_index]
        for carrier_index, true_frame in enumerate(expected_frames):
            candidates = (rank_zero[carrier_index], rank_one[carrier_index])
            true_rank = next((rank for rank, frame in enumerate(candidates) if frame == true_frame), None)
            selected_frame = selected_frames[carrier_index]
            rows.append(SelectionTopology(
                replica_index,
                carrier_index,
                true_frame,
                candidates,
                true_rank,
                selected_ranks[carrier_index],
                selected_frame,
                None if selected_frame is None else selected_frame - true_frame,
            ))
    return CaseTopology(cover_seed, reconstruction.extraction.recovery.token == handle, _aggregate(tuple(rows)), tuple(rows))


def _aggregate(rows: tuple[SelectionTopology, ...]) -> dict[str, int | float | None]:
    """Summarize candidate coverage, wrong-rank selections, and temporal displacement shape for one replay."""

    covered = tuple(row for row in rows if row.true_rank is not None)
    selected = tuple(row for row in rows if row.selected_rank is not None)
    exact = tuple(row for row in selected if row.selected_frame == row.true_frame)
    wrong_with_truth = tuple(row for row in selected if row.true_rank is not None and row.selected_frame != row.true_frame)
    displacements = tuple(row.selected_displacement_frames for row in selected if row.selected_displacement_frames is not None)
    displacement_mode = Counter(displacements).most_common(1)
    return {
        "replica_carrier_decisions": len(rows),
        "true_frame_candidate_coverage": len(covered),
        "true_frame_candidate_coverage_rate": len(covered) / len(rows) if rows else None,
        "selected_decisions": len(selected),
        "exact_selected_frames": len(exact),
        "exact_selected_rate": len(exact) / len(selected) if selected else None,
        "wrong_rank_when_true_available": len(wrong_with_truth),
        "median_selected_displacement_frames": median(displacements) if displacements else None,
        "modal_selected_displacement_frames": displacement_mode[0][0] if displacement_mode else None,
        "modal_selected_displacement_count": displacement_mode[0][1] if displacement_mode else 0,
    }


def run() -> dict[str, object]:
    """Return topology diagnostics for the failed and recovered iteration-030 trailing cases."""

    cases = (_case(7600), _case(7601))
    return {
        "goal": "classify rare non-oracle candidate-map failures before changing candidate generation or pilot discrimination",
        "decoder_received_oracle_map": False,
        "cases": [asdict(case) for case in cases],
    }


def main() -> None:
    """Print the machine-readable topology audit for archival redirection to ``RESULTS.json``."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
