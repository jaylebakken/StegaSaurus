"""Test structural invariants for the archived four-frame soft-combining experiment.

The tests cover frame-map separation, ordered extraction output, and evidence
combination semantics. They deliberately do not require successful token
recovery because that is a measured experimental result, not a production
capability at this point in the prototype.
"""

import pytest

from stegosaurus.audio.experiments.transport_optimization.iteration_004_four_frame_soft_combine.run import (
    FourFrameSoftCombineExperiment,
    _music_like_fixture,
)
from stegosaurus.audio.pilot import SpectralAudioPilot, SpectralPilotConfig


def test_four_frame_experiment_maps_four_disjoint_time_ordered_copies_per_carrier() -> None:
    """Assign every planned bit to four disjoint, chronologically ordered frame spans."""

    source = _music_like_fixture(10)
    experiment = FourFrameSoftCombineExperiment(
        SpectralAudioPilot(
            b"four-frame-test-key",
            SpectralPilotConfig(relative_difference=0.84),
        ),
        0.05,
    )

    embedding = experiment.embed(source, bytes.fromhex("0123456789abcdef"))
    extraction = experiment.extract(embedding.audio, embedding)

    assert len(embedding.carrier_plan.carrier_bits) == 144
    assert len(embedding.replica_frame_indices) == 4
    assert all(len(frame_map) == 144 for frame_map in embedding.replica_frame_indices)
    for earlier_map, later_map in zip(
        embedding.replica_frame_indices,
        embedding.replica_frame_indices[1:],
    ):
        assert set(earlier_map).isdisjoint(later_map)
        assert max(earlier_map) < min(later_map)
    assert len(extraction.replica_scores) == 4
    assert len(extraction.combined_scores) == 144
    assert len(extraction.observed_carrier_bits) == 144
    assert extraction.recovered == extraction.token_matches_input


def test_four_frame_soft_combiner_preserves_all_missing_evidence_and_weights_stronger_scores() -> None:
    """Emit an erasure for no evidence and use score magnitude when resolving disagreement."""

    combine_scores = FourFrameSoftCombineExperiment._combine_scores

    assert combine_scores((None, None, None, None)) is None
    assert combine_scores((0.2, None, None, None)) == pytest.approx(0.2)
    assert combine_scores((0.2, -0.1, None, None)) == pytest.approx(0.1)
