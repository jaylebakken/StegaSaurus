"""Test the detector-only WAV spectral pilot and reproducible MP3 benchmark path.

The colocated tests generate deterministic speech-like mono audio, prove PCM WAV I/O,
verify that unmarked audio remains absent, and check clean plus MP3 pilot
detection. They are smoke tests on synthetic content, not resilience claims for
speech corpora, human perception, arbitrary codecs, or adversarial edits.
"""

from datetime import date

import pytest

np = pytest.importorskip("numpy")
pytest.importorskip("scipy")
pytest.importorskip("imageio_ffmpeg")

from stegosaurus.audio.attacks import mp3_round_trip, normalize_peak
from stegosaurus.audio.benchmark import AudioPilotBenchmark
from stegosaurus.audio.detector import SpectralAudioDetector
from stegosaurus.audio.encoder import SpectralAudioEncoder
from stegosaurus.audio.pilot import (
    PcmAudio,
    SpectralAudioPilot,
    read_pcm16_wav,
    write_pcm16_wav,
)
from stegosaurus.audio.schema import AudioDetectionStatus


def _speech_like_fixture() -> PcmAudio:
    """Create a deterministic six-second voiced and noisy mono waveform for smoke tests."""

    sample_rate = 16000
    sample_positions = np.arange(sample_rate * 6) / sample_rate
    modulated_frequency = 900 + 90 * np.sin(2 * np.pi * 2 * sample_positions)
    samples = (
        0.28 * np.sin(2 * np.pi * 190 * sample_positions)
        + 0.18 * np.sin(2 * np.pi * 420 * sample_positions)
        + 0.10 * np.sin(2 * np.pi * modulated_frequency * sample_positions)
        + 0.02 * np.random.default_rng(7).normal(size=len(sample_positions))
    )
    return PcmAudio(samples.astype(np.float64), sample_rate)


def test_pcm16_wav_round_trip_preserves_mono_audio_with_quantization_tolerance(tmp_path) -> None:
    """Write and read PCM16 WAV data while allowing only expected integer quantization error."""

    source = _speech_like_fixture()
    output_path = tmp_path / "fixture.wav"

    write_pcm16_wav(output_path, source)
    recovered = read_pcm16_wav(output_path)

    assert recovered.sample_rate == source.sample_rate
    assert len(recovered.samples) == len(source.samples)
    assert np.max(np.abs(recovered.samples - source.samples)) <= 1 / 32767


def test_spectral_pilot_verifies_clean_and_mp3_audio_while_unmarked_audio_is_absent() -> None:
    """Verify the deterministic pilot after clean, 128, 96, and 64 kbps MP3 round trips."""

    epoch = date(2026, 10, 7)
    source = _speech_like_fixture()
    pilot = SpectralAudioPilot(b"audio-pilot-test-key")

    unmarked = pilot.extract(source, epoch)
    embedding = pilot.embed(source, epoch)
    clean = pilot.extract(embedding.audio, epoch)
    mp3_results = tuple(
        pilot.extract(mp3_round_trip(embedding.audio, bitrate), epoch)
        for bitrate in (128, 96, 64)
    )

    assert unmarked.detection.status is AudioDetectionStatus.ABSENT
    assert embedding.embedded_frame_count > 100
    assert embedding.signal_to_noise_db > 35
    assert clean.detection.status is AudioDetectionStatus.VERIFIED
    assert all(result.detection.status is AudioDetectionStatus.VERIFIED for result in mp3_results)


def test_directional_audio_api_keeps_encoding_and_detection_roles_separate() -> None:
    """Expose separate public encoder and detector workflows with compatible keyed state."""

    epoch = date(2026, 10, 7)
    source = _speech_like_fixture()
    encoder = SpectralAudioEncoder(b"audio-pilot-test-key")
    detector = SpectralAudioDetector(b"audio-pilot-test-key")

    embedding = encoder.encode(source, epoch)
    extraction = detector.detect(embedding.audio, epoch)

    assert encoder.schema.detection_bits(20, epoch) == detector.schema.detection_bits(20, epoch)
    assert extraction.detection.status is AudioDetectionStatus.VERIFIED


def test_spectral_pilot_rederives_keyed_carriers_for_hop_aligned_leading_trim() -> None:
    """Recover an embedded pilot after a leading trim aligned to STFT hop boundaries."""

    epoch = date(2026, 10, 7)
    pilot = SpectralAudioPilot(b"audio-pilot-test-key")
    embedding = pilot.embed(_speech_like_fixture(), epoch)
    leading_hops = 16
    trimmed = PcmAudio(
        embedding.audio.samples[leading_hops * 256 :],
        embedding.audio.sample_rate,
    )

    extraction = pilot.extract(trimmed, epoch)

    assert extraction.frame_offset == leading_hops
    assert extraction.detection.status is AudioDetectionStatus.VERIFIED


def test_spectral_pilot_preserves_selected_pair_magnitude_energy() -> None:
    """Keep each modified coefficient pair's combined magnitude unchanged during embedding."""

    pilot = SpectralAudioPilot(b"audio-pilot-test-key")
    frequencies = np.fft.rfftfreq(1024, 1 / 16000)
    lower_bin, upper_bin = pilot._frequency_bin_range(frequencies)
    frame = np.linspace(0.1, 1.0, len(frequencies)).astype(np.complex128)
    original_frame = frame.copy()

    embedded = pilot._embed_frame(frame, 1, lower_bin, upper_bin, 0)

    assert embedded
    for first_bin, second_bin in pilot._pair_bins(lower_bin, upper_bin, 0):
        original_energy = abs(original_frame[first_bin]) + abs(original_frame[second_bin])
        embedded_energy = abs(frame[first_bin]) + abs(frame[second_bin])
        assert embedded_energy == pytest.approx(original_energy)


def test_benchmark_records_named_attack_results_without_hiding_detector_evidence() -> None:
    """Report a clean baseline and named attack extraction for independent review."""

    epoch = date(2026, 10, 7)
    source = _speech_like_fixture()
    pilot = SpectralAudioPilot(b"audio-pilot-test-key")
    benchmark = AudioPilotBenchmark(pilot)

    result = benchmark.evaluate(
        source,
        epoch,
        {
            "normalize": lambda audio: normalize_peak(audio, 0.85),
            "mp3_96": lambda audio: mp3_round_trip(audio, 96),
        },
    )

    assert result.clean_extraction.detection.status is AudioDetectionStatus.VERIFIED
    assert tuple(evaluation.name for evaluation in result.attacks) == ("normalize", "mp3_96")
    assert all(evaluation.extraction.detection.observed_frames > 0 for evaluation in result.attacks)
