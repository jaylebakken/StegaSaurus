"""Test structural helpers for the stratified carrier-selection experiment.

The tests verify deterministic non-overlapping time strata and policy dispatch.
They do not assert recovery because that remains a measured experiment result.
"""

import pytest

from stegosaurus.audio.experiments.transport_optimization.iteration_008_stratified_carrier_selection.run import (
    StratifiedEnergyExperiment,
    _experiment_for_policy,
)
from stegosaurus.audio.pilot import SpectralAudioPilot


def test_strata_cover_one_replica_range_without_overlap() -> None:
    """Divide a replica span into chronological non-overlapping carrier-selection groups."""

    strata = StratifiedEnergyExperiment._strata(range(0, 12), 3)

    assert strata == (range(0, 4), range(4, 8), range(8, 12))


def test_policy_factory_selects_supported_policy_and_rejects_unknown_names() -> None:
    """Construct known experiment policies while rejecting accidental selection-policy typos."""

    pilot = SpectralAudioPilot(b"selection-test-key")

    assert type(_experiment_for_policy("sequential", pilot)).__name__ == "FourFrameSoftCombineExperiment"
    assert isinstance(_experiment_for_policy("stratified_pair_energy", pilot), StratifiedEnergyExperiment)
    with pytest.raises(ValueError, match="not recognized"):
        _experiment_for_policy("unknown", pilot)
