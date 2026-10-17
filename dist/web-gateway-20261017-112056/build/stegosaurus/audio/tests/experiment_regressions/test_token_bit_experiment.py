"""Test diagnostics and failure handling for the isolated token-bit experiment.

The tests confirm that the experiment maps every planned carrier to an oracle
frame index, reports raw bit damage before Reed--Solomon recovery, and preserves
per-attack failures without making the current statistical pilot appear to be a
working attribution transport. They deliberately do not assert token recovery:
that result is an experimental measurement expected to improve over time.
"""

import numpy as np
import pytest

from stegosaurus.audio.experiments.transport_optimization.iteration_002_oracle_token_bits.run import (
    TokenBitCapacityError,
    TokenBitExperiment,
)
from stegosaurus.audio.pilot import PcmAudio, SpectralAudioPilot


def _speech_like_fixture() -> PcmAudio:
    """Create deterministic non-silent synthetic audio with broad usable spectral energy."""

    sample_rate = 16000
    positions = np.arange(sample_rate * 6) / sample_rate
    modulated_frequency = 900 + 90 * np.sin(2 * np.pi * 2 * positions)
    samples = (
        0.28 * np.sin(2 * np.pi * 190 * positions)
        + 0.18 * np.sin(2 * np.pi * 420 * positions)
        + 0.10 * np.sin(2 * np.pi * modulated_frequency * positions)
        + 0.02 * np.random.default_rng(7).normal(size=len(positions))
    )
    return PcmAudio(samples.astype(np.float64), sample_rate)


def _invalid_attack(_: PcmAudio) -> PcmAudio:
    """Return an invalid attack result to verify isolated experiment error reporting."""

    return None  # type: ignore[return-value]


def test_token_bit_experiment_reports_ordered_clean_transport_diagnostics() -> None:
    """Expose the complete carrier plan and its actual raw recovery evidence without false success."""

    experiment = TokenBitExperiment(SpectralAudioPilot(b"audio-pilot-test-key"))
    token = bytes.fromhex("0123456789abcdef")

    embedding = experiment.embed(_speech_like_fixture(), token)
    extraction = experiment.extract(embedding.audio, embedding)

    assert len(embedding.carrier_plan.carrier_bits) == 144
    assert len(embedding.carrier_frame_indices) == 144
    assert len(extraction.observed_carrier_bits) == 144
    assert extraction.known_bit_errors + extraction.carrier_erasures <= 144
    assert extraction.recovery.channel_recovery.error is None or not extraction.recovered


def test_token_bit_experiment_fails_closed_when_audio_has_insufficient_eligible_frames() -> None:
    """Reject a quiet waveform instead of silently truncating the required token-bit plan."""

    silent_audio = PcmAudio(np.zeros(16000, dtype=np.float64), 16000)
    experiment = TokenBitExperiment(SpectralAudioPilot(b"audio-pilot-test-key"))

    with pytest.raises(TokenBitCapacityError, match="enough eligible frames"):
        experiment.embed(silent_audio, bytes.fromhex("0123456789abcdef"))


def test_token_bit_experiment_captures_one_bad_attack_without_skipping_later_results() -> None:
    """Keep a named failure record while extracting a later identity transformation normally."""

    experiment = TokenBitExperiment(SpectralAudioPilot(b"audio-pilot-test-key"))

    result = experiment.evaluate(
        _speech_like_fixture(),
        bytes.fromhex("0123456789abcdef"),
        {
            "invalid": _invalid_attack,
            "identity": lambda audio: audio,
        },
    )

    invalid, identity = result.attacks
    assert invalid.error == "TypeError: audio attacks must return PcmAudio"
    assert not invalid.succeeded
    assert identity.succeeded
    assert identity.extraction is not None
