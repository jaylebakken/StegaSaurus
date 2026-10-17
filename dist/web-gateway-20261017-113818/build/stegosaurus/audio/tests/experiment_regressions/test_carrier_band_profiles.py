"""Test fixed carrier-band profiles and transformation-study declarations.

The tests verify that every profile is distinct and that the low-pass-safe
profile remains below the named 4 kHz attack cutoff. They avoid running codec
and calibration workloads during ordinary regression testing.
"""

from stegosaurus.audio.experiments.transport_optimization.iteration_013_carrier_band_profiles.run import (
    _attacks,
    _profiles,
)


def test_profiles_are_unique_and_include_a_low_pass_safe_band() -> None:
    """Keep profile names distinct and preserve the guarded band below the 4 kHz cutoff."""

    profiles = _profiles()
    names = tuple(profile.name for profile in profiles)
    low_pass_safe = next(profile for profile in profiles if profile.name == "lowpass_safe_500_3200hz")

    assert len(names) == len(set(names))
    assert low_pass_safe.maximum_frequency_hz < 4000.0


def test_attack_set_includes_low_pass_and_sync_scanned_leading_crop() -> None:
    """Retain the named low-pass target and offset-scanned leading-crop control condition."""

    attacks = _attacks()
    leading_crop = next(attack for attack in attacks if attack.name == "leading_crop_025s")

    assert any(attack.name == "low_pass_4khz" for attack in attacks)
    assert leading_crop.offset_scan is True
