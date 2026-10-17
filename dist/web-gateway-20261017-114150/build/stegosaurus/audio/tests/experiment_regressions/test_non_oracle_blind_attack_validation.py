"""Regression checks for iteration 011's blind compact-handle attack validation.

The test runs a clean condition, a named lossy-codec condition, and a leading
crop condition on one disjoint cover. It verifies that every result comes from
the blind decoder, records an exact-handle negative control, and explicitly
labels crop diagnostics as timeline-unaligned rather than oracle mapped.
"""

from stegosaurus.audio.experiments.non_oracle_reconstruction.iteration_011_blind_attack_validation.run import (
    _attack_definitions,
    evaluate_variant,
)


def test_blind_attack_validation_records_codec_and_crop_conditions() -> None:
    """Evaluate one disjoint cover under clean PCM, MP3, and a bounded leading crop."""

    selected_names = {"clean_pcm", "mp3_64k", "leading_crop_025s"}
    attacks = tuple(attack for attack in _attack_definitions() if attack.name in selected_names)
    records = evaluate_variant(0, attacks)

    assert len(records) == 3
    assert all(record.error is None for record in records)
    assert all(record.measurement is not None for record in records)
    assert all(record.decoder_received_oracle_map is False for record in records)
    assert all(record.unwatermarked_control_handle_match is False for record in records)
    crop = next(record for record in records if record.attack_name == "leading_crop_025s")
    assert crop.map_diagnostic_mode == "timeline_unaligned_not_scored"
