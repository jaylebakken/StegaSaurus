"""Test the bounded v1 claimed-handle attribution prototype.

The test uses a deterministic 30-second synthetic cover because the selected
four-replica profile was measured on that duration scale. It verifies clean
claimed-handle recovery through a retained registry record and confirms that a
sample-rate mismatch becomes an explicit unrecoverable result rather than a
guessed attribution.
"""

from __future__ import annotations

import numpy as np

from stegosaurus.audio.attribution import (
    AttributionStatus,
    InMemoryAttributionRegistry,
    SpectralAttributionDecoder,
    SpectralAttributionEncoder,
)
from stegosaurus.audio.pilot import PcmAudio


def _music_like_fixture(duration_seconds: int = 30) -> PcmAudio:
    """Create a deterministic energetic mono cover with enough frames for the v1 four-replica profile."""

    sample_rate = 16000
    positions = np.arange(sample_rate * duration_seconds, dtype=np.float64) / sample_rate
    modulation = 0.5 + 0.5 * np.sin(2 * np.pi * 0.11 * positions)
    samples = (
        0.18 * np.sin(2 * np.pi * 110 * positions)
        + 0.12 * np.sin(2 * np.pi * 220 * positions + 0.25 * modulation)
        + 0.10 * np.sin(2 * np.pi * 330 * positions)
        + 0.08 * np.sin(2 * np.pi * (700 + 80 * modulation) * positions)
        + 0.06 * np.sin(2 * np.pi * (1400 + 140 * modulation) * positions)
        + 0.025 * np.random.default_rng(31).normal(size=len(positions))
    )
    return PcmAudio(np.asarray(samples, dtype=np.float64), sample_rate)


def test_claimed_handle_round_trip_uses_a_retained_registry_record() -> None:
    """Recover an issued handle from clean PCM only after resolving its private retained carrier map."""

    secret = b"attribution-test-secret"
    registry = InMemoryAttributionRegistry(b"registry-test-secret")
    entry, embedding = SpectralAttributionEncoder(secret).issue_and_encode(
        _music_like_fixture(), registry, b"fixture provenance"
    )

    record = registry.record_for(entry.handle)
    assert record is not None
    verification = SpectralAttributionDecoder(secret).verify(embedding.audio, record)

    assert verification.status is AttributionStatus.RECOVERED
    assert verification.recovered_handle == entry.handle
    assert verification.claim_rs_cost <= 16


def test_claimed_handle_decoder_rejects_a_sample_rate_mismatch_without_guessing() -> None:
    """Return an explicit unrecoverable result when a retained frame map cannot align to the PCM sample rate."""

    secret = b"attribution-test-secret"
    registry = InMemoryAttributionRegistry(b"registry-test-secret")
    entry, embedding = SpectralAttributionEncoder(secret).issue_and_encode(
        _music_like_fixture(), registry, b"fixture provenance"
    )
    record = registry.record_for(entry.handle)
    assert record is not None
    mismatched_audio = PcmAudio(embedding.audio.samples[::2], embedding.audio.sample_rate // 2)

    verification = SpectralAttributionDecoder(secret).verify(mismatched_audio, record)

    assert verification.status is AttributionStatus.UNRECOVERABLE
    assert verification.recovered_handle is None
    assert verification.error == "received sample rate does not match the retained attribution record"


def test_claimed_handle_decoder_rejects_a_wrong_carrier_secret() -> None:
    """Reject a retained record when the decoder regenerates different secret-keyed carrier pairs."""

    registry = InMemoryAttributionRegistry(b"registry-test-secret")
    entry, embedding = SpectralAttributionEncoder(b"attribution-test-secret").issue_and_encode(
        _music_like_fixture(), registry, b"fixture provenance"
    )
    record = registry.record_for(entry.handle)
    assert record is not None

    verification = SpectralAttributionDecoder(b"wrong-attribution-test-secret").verify(embedding.audio, record)

    assert verification.status is not AttributionStatus.RECOVERED
    assert verification.recovered_handle != entry.handle
