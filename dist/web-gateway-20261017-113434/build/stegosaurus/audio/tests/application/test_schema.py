"""Test carrier-agnostic audio watermark detection and attribution schema behavior.

The colocated tests use already synchronized binary frame observations rather than audio
files. They verify keyed detector decisions, missing-frame handling, and exact
opaque-token recovery through the shared Reed--Solomon transport.
"""

from datetime import date

import pytest

from stegosaurus.audio import (
    AudioDetectionStatus,
    AudioWatermarkConfig,
    AudioWatermarkSchema,
)


def test_audio_schema_verifies_keyed_frame_agreement_and_rejects_inverse_bits() -> None:
    """Verify an exact detector pattern and classify its inverse as absent evidence."""

    schema = AudioWatermarkSchema(
        b"audio-schema-test-key",
        AudioWatermarkConfig(
            minimum_detection_frames=20,
            verification_p_value=1e-4,
        ),
    )
    epoch = date(2026, 10, 7)
    expected_bits = schema.detection_bits(20, epoch)

    verified = schema.detect(expected_bits, epoch)
    absent = schema.detect(tuple(1 - bit for bit in expected_bits), epoch)

    assert verified.status is AudioDetectionStatus.VERIFIED
    assert verified.matching_frames == 20
    assert verified.tail_probability < 1e-4
    assert absent.status is AudioDetectionStatus.ABSENT
    assert absent.matching_frames == 0


def test_audio_schema_marks_short_or_missing_frame_observations_inconclusive() -> None:
    """Treat unavailable frame observations as erasures and require enough evidence."""

    schema = AudioWatermarkSchema(
        b"audio-schema-test-key",
        AudioWatermarkConfig(minimum_detection_frames=20),
    )
    epoch = date(2026, 10, 7)
    expected_bits = schema.detection_bits(20, epoch)
    observed_bits = tuple(expected_bits[:10]) + (None,) * 10

    result = schema.detect(observed_bits, epoch)

    assert result.status is AudioDetectionStatus.INCONCLUSIVE
    assert result.observed_frames == 10
    assert result.matching_frames == 10


def test_audio_schema_applies_multiple_offset_correction_before_verification() -> None:
    """Increase the detection tail probability when a synchronization search tests offsets."""

    schema = AudioWatermarkSchema(
        b"audio-schema-test-key",
        AudioWatermarkConfig(minimum_detection_frames=20, verification_p_value=1e-6),
    )
    epoch = date(2026, 10, 7)
    expected_bits = schema.detection_bits(20, epoch)

    uncorrected = schema.detect(expected_bits, epoch)
    corrected = schema.detect(expected_bits, epoch, p_value_multiplier=32)

    assert corrected.tail_probability == uncorrected.tail_probability * 32
    assert corrected.uncorrected_tail_probability == uncorrected.tail_probability
    assert corrected.p_value_multiplier == 32
    assert corrected.status is AudioDetectionStatus.INCONCLUSIVE


def test_audio_schema_keeps_large_inverse_observations_absent() -> None:
    """Avoid numerical underflow that could falsely verify a long inverse pattern."""

    schema = AudioWatermarkSchema(
        b"audio-schema-test-key",
        AudioWatermarkConfig(minimum_detection_frames=2_048),
    )
    epoch = date(2026, 10, 7)
    expected_bits = schema.detection_bits(2_048, epoch)

    result = schema.detect(tuple(1 - bit for bit in expected_bits), epoch)

    assert result.tail_probability == 1.0
    assert result.status is AudioDetectionStatus.ABSENT


def test_audio_schema_rejects_ambiguous_binary_and_search_inputs() -> None:
    """Require literal binary frame values and an integer predeclared search count."""

    schema = AudioWatermarkSchema(b"audio-schema-test-key")
    epoch = date(2026, 10, 7)

    with pytest.raises(ValueError, match="0, 1, or None"):
        schema.detect((True,), epoch)
    with pytest.raises(ValueError, match="0, 1, or None"):
        schema.detect((1.0,), epoch)
    with pytest.raises(TypeError, match="integer"):
        schema.detect((0,), epoch, p_value_multiplier=True)


def test_audio_schema_rejects_ambiguous_configuration_types() -> None:
    """Fail early when boolean or fractional values reach count-based configuration."""

    with pytest.raises(TypeError, match="count settings"):
        AudioWatermarkConfig(parity_symbols=True)
    with pytest.raises(TypeError, match="count settings"):
        AudioWatermarkConfig(minimum_detection_frames=32.0)
    with pytest.raises(TypeError, match="finite numbers"):
        AudioWatermarkConfig(verification_p_value=float("nan"))


def test_audio_schema_exposes_carrier_budget_and_recovers_declared_erasures() -> None:
    """Expose the fixed transport budget and use Reed--Solomon erasure recovery."""

    schema = AudioWatermarkSchema(b"audio-schema-test-key")
    token = bytes.fromhex("0123456789abcdef")
    plan = schema.plan_attribution(token)
    observed_bits: list[int | None] = list(plan.carrier_bits)
    observed_bits[8:16] = [None] * 8

    result = schema.recover_attribution(observed_bits)

    assert schema.attribution_carrier_bits == len(plan.carrier_bits)
    assert result.recovered
    assert result.token == token
    assert result.channel_recovery.erasure_positions


def test_audio_schema_rejects_accidental_secret_and_token_coercions() -> None:
    """Require bytes-like opaque material instead of accepting integers or text."""

    with pytest.raises(TypeError, match="master_secret"):
        AudioWatermarkSchema(8)  # type: ignore[arg-type]

    schema = AudioWatermarkSchema(b"audio-schema-test-key")
    with pytest.raises(TypeError, match="token"):
        schema.plan_attribution("01234567")  # type: ignore[arg-type]


def test_audio_schema_recovers_fixed_length_opaque_attribution_token() -> None:
    """Round-trip an eight-byte opaque ledger token through the audio carrier plan."""

    schema = AudioWatermarkSchema(b"audio-schema-test-key")
    token = bytes.fromhex("0123456789abcdef")
    plan = schema.plan_attribution(token)

    result = schema.recover_attribution(plan.carrier_bits)

    assert result.recovered
    assert result.token == token
    assert result.channel_recovery.error is None
