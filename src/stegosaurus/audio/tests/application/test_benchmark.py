"""Test audio attack validation, reproducible transcoding, and benchmark failure records.

The colocated tests use a deterministic mono waveform to exercise attack contracts and
reporting without making corpus-level robustness or perceptual-quality claims.
They verify that a failed caller-supplied attack is visible while subsequent
attacks still run, allowing benchmark summaries to distinguish failure from an
absent or inconclusive watermark result.
"""

from datetime import date

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("scipy")

from stegosaurus.audio.attacks import (
    EntropicAttackConfig,
    EntropicAttackProfile,
    add_white_noise,
    low_pass_filter,
    mp3_round_trip,
    resample_audio,
    time_scale_audio,
    trim_audio,
)
from stegosaurus.audio.benchmark import AudioPilotBenchmark
from stegosaurus.audio.pilot import PcmAudio, SpectralAudioPilot


def _fixture_audio(seconds: int = 6) -> PcmAudio:
    """Create deterministic, non-silent mono audio suitable for pilot smoke tests."""

    sample_rate = 16000
    positions = np.arange(sample_rate * seconds) / sample_rate
    samples = (
        0.28 * np.sin(2 * np.pi * 190 * positions)
        + 0.18 * np.sin(2 * np.pi * 420 * positions)
        + 0.02 * np.random.default_rng(13).normal(size=len(positions))
    )
    return PcmAudio(samples.astype(np.float64), sample_rate)


def _failing_attack(_: PcmAudio) -> PcmAudio:
    """Raise a predictable error to verify per-attack benchmark failure capture."""

    raise ValueError("intentional attack failure")


def test_attack_parameter_validation_and_short_filtering_are_explicit() -> None:
    """Reject invalid attack values while allowing a short waveform through the filter."""

    audio = _fixture_audio()
    short_audio = PcmAudio(np.array([0.1, -0.1, 0.05], dtype=np.float64), 16000)

    with pytest.raises(TypeError, match="bitrate_kbps"):
        mp3_round_trip(audio, 96.5)
    with pytest.raises(ValueError, match="noise_snr_db must be finite"):
        add_white_noise(audio, float("nan"))
    with pytest.raises(TypeError, match="destination_sample_rate"):
        resample_audio(audio, 16000.0)
    with pytest.raises(ValueError, match="at least one sample"):
        trim_audio(PcmAudio(np.array([0.1], dtype=np.float64), 1), 0.1, 0.2)
    with pytest.raises(ValueError, match="speed_factor"):
        time_scale_audio(audio, float("inf"))

    filtered = low_pass_filter(short_audio, 3000)

    assert filtered.sample_rate == short_audio.sample_rate
    assert len(filtered.samples) == len(short_audio.samples)
    assert np.isfinite(filtered.samples).all()


def test_benchmark_captures_one_attack_failure_and_runs_later_attacks() -> None:
    """Preserve an error record for one bad attack while evaluating subsequent attacks."""

    source = _fixture_audio()
    benchmark = AudioPilotBenchmark(SpectralAudioPilot(b"benchmark-test-key"))

    result = benchmark.evaluate(
        source,
        date(2026, 10, 7),
        {
            "broken": _failing_attack,
            "resample": lambda audio: resample_audio(audio, 12000),
        },
    )

    failed, succeeded = result.attacks

    assert failed.name == "broken"
    assert failed.duration_seconds is None
    assert failed.extraction is None
    assert failed.error == "ValueError: intentional attack failure"
    assert not failed.succeeded
    assert succeeded.name == "resample"
    assert succeeded.succeeded
    assert succeeded.extraction is not None
    assert result.failures == (failed,)


def test_entropic_attack_recipe_replays_exactly_with_recorded_parameters() -> None:
    """Sample one realistic multi-effect recipe and reproduce its transformed waveform exactly."""

    source = _fixture_audio()
    profile = EntropicAttackProfile(
        EntropicAttackConfig(
            resample_probability=1.0,
            resample_rates=(12000,),
            low_pass_probability=1.0,
            low_pass_cutoff_hz_range=(3500.0, 3500.0),
            reverb_probability=1.0,
            reverb_mix_range=(0.12, 0.12),
            reverb_decay_seconds_range=(0.08, 0.08),
            time_scale_probability=1.0,
            speed_factor_range=(1.0, 1.0),
            leading_trim_probability=1.0,
            leading_trim_seconds_range=(0.0, 0.0),
            mp3_probability=0.0,
            noise_snr_db_range=(30.0, 30.0),
            target_peak_range=(0.85, 0.85),
        )
    )

    recipe = profile.sample(source.sample_rate, 12345)
    repeated_recipe = profile.sample(source.sample_rate, 12345)
    first = profile.apply(source, recipe)
    second = profile.apply(source, repeated_recipe)

    assert recipe == repeated_recipe
    assert recipe.name == "entropy-0000000000003039"
    assert first.sample_rate == source.sample_rate
    assert np.array_equal(first.samples, second.samples)
    assert not np.array_equal(first.samples, source.samples)


def test_benchmark_retains_sampled_recipes_for_entropic_trials() -> None:
    """Record every replay recipe when evaluating a deterministic batch of stochastic attacks."""

    source = _fixture_audio()
    profile = EntropicAttackProfile(
        EntropicAttackConfig(
            resample_probability=0.0,
            low_pass_probability=0.0,
            reverb_probability=0.0,
            time_scale_probability=0.0,
            leading_trim_probability=0.0,
            mp3_probability=0.0,
            noise_snr_db_range=(30.0, 30.0),
            target_peak_range=(0.85, 0.85),
        )
    )
    benchmark = AudioPilotBenchmark(SpectralAudioPilot(b"entropy-benchmark-test-key"))

    result = benchmark.evaluate_entropic(
        source,
        date(2026, 10, 8),
        profile,
        trial_count=3,
        seed=99,
    )

    assert len(result.attacks) == 3
    assert all(evaluation.succeeded for evaluation in result.attacks)
    assert all(evaluation.recipe is not None for evaluation in result.attacks)
    assert tuple(evaluation.name for evaluation in result.attacks) == tuple(
        evaluation.recipe.name for evaluation in result.attacks if evaluation.recipe is not None
    )


def test_mp3_round_trip_is_repeatable_for_sample_rate_and_mono_samples() -> None:
    """Verify repeated FFmpeg MP3 round trips retain the requested PCM output geometry."""

    pytest.importorskip("imageio_ffmpeg")
    source = _fixture_audio()

    first = mp3_round_trip(source, 96)
    second = mp3_round_trip(source, 96)

    assert first.sample_rate == source.sample_rate
    assert first.samples.ndim == 1
    assert np.array_equal(first.samples, second.samples)
