"""Test the v2 repeated-block attribution prototype.

The v2 codec embeds the same handle into complete 30-second blocks and pools
carrier evidence across block verifications. The test keeps the fixture
synthetic and clean; it does not claim blind localization, crop recovery,
compression robustness, or perceptual transparency.
"""

from __future__ import annotations

import numpy as np

from stegosaurus.audio.attribution import AttributionStatus, BlockAttributionCodec
from stegosaurus.audio.pilot import PcmAudio


def _music_like_fixture(duration_seconds: int = 150) -> PcmAudio:
    """Create a deterministic multi-block synthetic cover for v2 attribution tests."""

    sample_rate = 16000
    positions = np.arange(sample_rate * duration_seconds, dtype=np.float64) / sample_rate
    modulation = 0.5 + 0.5 * np.sin(2 * np.pi * 0.07 * positions)
    samples = (
        0.18 * np.sin(2 * np.pi * 110 * positions)
        + 0.12 * np.sin(2 * np.pi * 220 * positions + 0.25 * modulation)
        + 0.10 * np.sin(2 * np.pi * 330 * positions)
        + 0.08 * np.sin(2 * np.pi * (700 + 80 * modulation) * positions)
        + 0.06 * np.sin(2 * np.pi * (1400 + 140 * modulation) * positions)
        + 0.025 * np.random.default_rng(43).normal(size=len(positions))
    )
    return PcmAudio(np.asarray(samples, dtype=np.float64), sample_rate)


def test_block_attribution_pools_repeated_clean_block_evidence() -> None:
    """Recover a repeated v2 handle through pooled block evidence."""

    codec = BlockAttributionCodec(b"block-attribution-test-secret")
    handle = bytes.fromhex("01020304")

    embedding = codec.embed(_music_like_fixture(), handle)
    verification = codec.verify(embedding.audio, embedding.record)

    assert len(embedding.record.block_records) == 5
    assert verification.status is AttributionStatus.RECOVERED
    assert verification.recovered_handle == handle
    assert verification.pooled_verification.claim_rs_cost <= 16
    assert verification.recovered_block_count >= 1


def test_block_attribution_reports_sample_rate_mismatch() -> None:
    """Reject mismatched PCM geometry before attempting pooled attribution."""

    codec = BlockAttributionCodec(b"block-attribution-test-secret")
    embedding = codec.embed(_music_like_fixture(30), bytes.fromhex("01020304"))
    mismatched = PcmAudio(embedding.audio.samples[::2], embedding.audio.sample_rate // 2)

    verification = codec.verify(mismatched, embedding.record)

    assert verification.status is AttributionStatus.UNRECOVERABLE
    assert verification.pooled_verification.error == "received sample rate does not match the retained block record"

