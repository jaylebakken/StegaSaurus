"""Run iteration 001: reproduce the detector-only pilot benchmark.

Experiment goal: measure the detector's statistical presence decision on a
deterministic speech-like fixture under a named transformation matrix and a
seeded stochastic attack profile with matched unmarked controls.

Pipeline state: this is a detector-only WAV pilot. It embeds a daily keyed
statistical pattern, scans bounded frame offsets, and reports presence. It does
not embed an opaque token or perform byte-level Reed--Solomon attribution
recovery; that follow-on question belongs to iteration 002.
"""

from __future__ import annotations

from collections import Counter, defaultdict
from datetime import date
import json

import numpy as np

from ....attacks import (
    EntropicAttackProfile,
    add_white_noise,
    concatenate_audio,
    low_pass_filter,
    mp3_round_trip,
    normalize_peak,
    resample_audio,
    time_scale_audio,
    trim_audio,
)
from ....benchmark import AudioPilotBenchmark
from ....pilot import PcmAudio, SpectralAudioPilot


def _fixture_audio() -> PcmAudio:
    """Create the deterministic six-second speech-like mono waveform used by iteration 001."""

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


def _detection_record(extraction: object) -> dict[str, object]:
    """Serialize one pilot extraction into stable primitive values for the experiment summary."""

    detection = extraction.detection
    return {
        "status": detection.status.value,
        "tail_probability": detection.tail_probability,
        "uncorrected_tail_probability": detection.uncorrected_tail_probability,
        "observed_frames": detection.observed_frames,
        "matching_frames": detection.matching_frames,
        "matching_rate": detection.matching_rate,
        "frame_offset": extraction.frame_offset,
    }


def _named_attacks() -> dict[str, object]:
    """Return the fixed individual transformation matrix recorded by iteration 001."""

    return {
        "mp3_128": lambda audio: mp3_round_trip(audio, 128),
        "mp3_96": lambda audio: mp3_round_trip(audio, 96),
        "mp3_64": lambda audio: mp3_round_trip(audio, 64),
        "resample_8k_round_trip": lambda audio: resample_audio(resample_audio(audio, 8000), 16000),
        "resample_44k1_round_trip": lambda audio: resample_audio(
            resample_audio(audio, 44100),
            16000,
        ),
        "normalize_peak_085": lambda audio: normalize_peak(audio, 0.85),
        "low_pass_4khz": lambda audio: low_pass_filter(audio, 4000),
        "noise_30db": lambda audio: add_white_noise(audio, 30.0, seed=13),
        "leading_crop_025s": lambda audio: trim_audio(audio, 0.25, audio.duration_seconds),
        "self_concatenation": lambda audio: concatenate_audio((audio, audio)),
        "time_scale_105x": lambda audio: time_scale_audio(audio, 1.05),
    }


def _effect_labels(recipe: object) -> tuple[str, ...]:
    """Return names of all stochastic effects enabled in one retained entropy recipe."""

    labels = ["noise", "peak_normalization"]
    if recipe.resample_rate is not None:
        labels.append("resample")
    if recipe.low_pass_cutoff_hz is not None:
        labels.append("low_pass")
    if recipe.reverb_mix is not None:
        labels.append("reverb")
    if recipe.speed_factor != 1.0:
        labels.append("time_scale")
    if recipe.leading_trim_seconds:
        labels.append("leading_trim")
    if recipe.mp3_bitrate_kbps is not None:
        labels.append("mp3")
    return tuple(labels)


def run() -> dict[str, object]:
    """Execute the detector benchmark and return a JSON-serializable record of all outcomes."""

    source = _fixture_audio()
    epoch = date(2026, 10, 7)
    pilot = SpectralAudioPilot(b"audio-pilot-test-key")
    benchmark = AudioPilotBenchmark(pilot)
    named_attacks = _named_attacks()
    named_result = benchmark.evaluate(source, epoch, named_attacks)
    named_records = {
        evaluation.name: {
            "marked": _detection_record(evaluation.extraction),
            "unmarked_control": _detection_record(pilot.extract(named_attacks[evaluation.name](source), epoch)),
        }
        for evaluation in named_result.attacks
        if evaluation.extraction is not None
    }
    profile = EntropicAttackProfile()
    root_seed = 20261008
    recipes = profile.sample_many(source.sample_rate, 20, root_seed)
    entropy_result = benchmark.evaluate_entropic(source, epoch, profile, len(recipes), root_seed)
    marked_status_counts: Counter[str] = Counter()
    unmarked_status_counts: Counter[str] = Counter()
    effect_trial_counts: Counter[str] = Counter()
    effect_status_counts: defaultdict[str, Counter[str]] = defaultdict(Counter)
    for recipe, evaluation in zip(recipes, entropy_result.attacks):
        if evaluation.extraction is None:
            continue
        marked_status = evaluation.extraction.detection.status.value
        control_status = pilot.extract(profile.apply(source, recipe), epoch).detection.status.value
        marked_status_counts[marked_status] += 1
        unmarked_status_counts[control_status] += 1
        for label in _effect_labels(recipe):
            effect_trial_counts[label] += 1
            effect_status_counts[label][marked_status] += 1
    return {
        "fixture": {
            "description": "deterministic six-second 16 kHz speech-like synthetic mono waveform",
            "sample_rate": source.sample_rate,
            "duration_seconds": source.duration_seconds,
            "epoch": epoch.isoformat(),
            "embedding_snr_db": named_result.embedding.signal_to_noise_db,
            "embedded_frames": named_result.embedding.embedded_frame_count,
            "skipped_frames": named_result.embedding.skipped_frame_count,
        },
        "clean_marked": _detection_record(named_result.clean_extraction),
        "clean_unmarked": _detection_record(pilot.extract(source, epoch)),
        "named_attacks": named_records,
        "entropy_profile": {
            "root_seed": root_seed,
            "trial_count": len(recipes),
            "marked_status_counts": dict(sorted(marked_status_counts.items())),
            "unmarked_status_counts": dict(sorted(unmarked_status_counts.items())),
            "effect_trial_counts": dict(sorted(effect_trial_counts.items())),
            "effect_marked_status_counts": {
                name: dict(sorted(counts.items()))
                for name, counts in sorted(effect_status_counts.items())
            },
        },
    }


def main() -> None:
    """Print the complete reproducible iteration record as formatted JSON."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
