"""Test structural helpers for the calibrated post-round-trip margin experiment.

These tests verify deterministic ranked-candidate selection behavior without
running the full probe-embedding study across all cover variants.
"""

import pytest

from stegosaurus.audio.experiments.transport_optimization.iteration_009_calibrated_margin_selection.run import (
    CalibratedMarginExperiment,
    _experiment_for_policy,
)
from stegosaurus.audio.pilot import SpectralAudioPilot


def test_best_rank_chooses_the_larger_signed_probe_margin() -> None:
    """Select the probe candidate whose expected-bit signed extraction evidence is stronger."""

    experiment = CalibratedMarginExperiment(SpectralAudioPilot(b"margin-test-key"), 0.01)
    probe_margins = (((0.1,),), ((0.3,),))

    assert experiment._best_rank(probe_margins, 0, 0) == 1


def test_policy_factory_constructs_calibrated_policy_and_rejects_unknown_names() -> None:
    """Return the calibrated selector only for its explicit experiment-policy name."""

    pilot = SpectralAudioPilot(b"margin-test-key")

    assert isinstance(_experiment_for_policy("calibrated_round_trip_margin", pilot), CalibratedMarginExperiment)
    with pytest.raises(ValueError, match="not recognized"):
        _experiment_for_policy("unknown", pilot)
