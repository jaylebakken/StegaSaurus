"""Test the isolated two-frame soft-combining experiment's transport diagnostics.

The regression tests verify only structural experiment invariants: each logical
carrier receives two disjoint time-separated frame mappings, combined evidence
is emitted in carrier-plan order, and missing evidence remains an erasure. They
do not assert token recovery because that is the measured outcome of the
experiment rather than a completed capability.
"""

import pytest

from stegosaurus.audio.experiments.transport_optimization.iteration_003_two_frame_soft_combine.run import (
    TwoFrameSoftCombineExperiment,
    _music_like_fixture,
)
from stegosaurus.audio.pilot import SpectralAudioPilot, SpectralPilotConfig


def test_two_frame_experiment_maps_two_disjoint_time_separated_copies_per_carrier() -> None:
    """Assign every planned bit to one primary and one replica frame in separate signal halves."""

    source = _music_like_fixture(10)
    experiment = TwoFrameSoftCombineExperiment(
        SpectralAudioPilot(
            b"two-frame-test-key",
            SpectralPilotConfig(relative_difference=0.72),
        )
    )

    embedding = experiment.embed(source, bytes.fromhex("0123456789abcdef"))
    extraction = experiment.extract(embedding.audio, embedding)

    assert len(embedding.carrier_plan.carrier_bits) == 144
    assert len(embedding.primary_frame_indices) == 144
    assert len(embedding.replica_frame_indices) == 144
    assert set(embedding.primary_frame_indices).isdisjoint(embedding.replica_frame_indices)
    assert max(embedding.primary_frame_indices) < min(embedding.replica_frame_indices)
    assert len(extraction.combined_scores) == 144
    assert len(extraction.observed_carrier_bits) == 144


def test_two_frame_soft_combiner_preserves_missing_evidence_and_weights_stronger_scores() -> None:
    """Emit an erasure only when both copies are missing and weight nonzero signed evidence by magnitude."""

    combine_scores = TwoFrameSoftCombineExperiment._combine_scores

    assert combine_scores(None, None) is None
    assert combine_scores(0.2, None) == pytest.approx(0.2)
    assert combine_scores(0.2, -0.1) == pytest.approx(0.1)
