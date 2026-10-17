"""Test fixed attack-study definitions and alignment-label behavior.

The tests verify that the pre-registered attack list is stable and that the
leading-crop result remains explicitly labeled as alignment limited. They avoid
expensive codec execution during ordinary regression testing.
"""

from stegosaurus.audio.experiments.transport_optimization.iteration_010_calibrated_attack_study.run import (
    _attack_definitions,
)


def test_attack_definitions_have_unique_names_and_an_explicit_alignment_limited_crop() -> None:
    """Keep conditions distinct and preserve the leading-crop caveat in output data."""

    attacks = _attack_definitions()
    names = tuple(attack.name for attack in attacks)
    leading_crop = next(attack for attack in attacks if attack.name == "leading_crop_025s")

    assert len(names) == len(set(names))
    assert leading_crop.mapping_mode == "unrealigned_original_map_alignment_limited"
    assert {"mp3_64k", "mp3_96k", "mp3_128k", "low_pass_4khz"}.issubset(names)
