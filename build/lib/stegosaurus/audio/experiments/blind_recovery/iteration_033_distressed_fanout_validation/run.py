"""Run iteration 033: distressed known-song fanout validation.

Goal: apply realistic light distress to the suspicious excerpt after the
iteration 032 workflow succeeded on a clean crop. The experiment keeps the same
known-song registry assumption: source audio and embedding records are
available, but the submitted excerpt may have been normalized, lightly filtered,
or passed through a recorded-audio proxy.

Toy flow:
    clean leaked crop -> named distress -> shared source-audio prefilter
        -> fine phase search -> verify many export records -> rank the leak

This is a named synthetic distress validation only. It does not claim broad
microphone, platform, codec, or production-processing robustness.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
from time import perf_counter

from ....attacks import add_reverberation, add_white_noise, low_pass_filter, normalize_peak, resample_audio
from ....attribution import BlockAttributionCodec
from ....pilot import PcmAudio, read_pcm16_wav
from ..iteration_031_registry_audio_prefilter.run import _registry_blocks, _trial
from ..iteration_032_prefilter_embedding_fanout.run import (
    BLOCK_SECONDS,
    CROP_SECONDS,
    LEAKED_INDEX,
    TARGET_FILE,
    _crop,
    _crop_start,
    _embed_exports,
    _rank,
    _records,
    _unique_candidates,
    _verify_export,
)


SAMPLES_DIR = Path("samples")
OUTPUT_PATH = Path(__file__).with_name("results.json")


@dataclass(frozen=True, slots=True)
class DistressProfile:
    """Declare one named suspicious-excerpt transformation."""

    name: str
    expectation: str


@dataclass(frozen=True, slots=True)
class DistressOutcome:
    """Summarize one known-song fanout run under a distress profile."""

    distress: str
    expected: str
    correct_record_rank: int | None
    correct_record_recovered: bool
    correct_record_rs_cost: int
    false_acceptances: int
    prefilter_elapsed_ms: float
    verification_elapsed_ms: float
    workflow_passed: bool


def _profiles() -> tuple[DistressProfile, ...]:
    """Return the named distress profiles for this validation pass."""

    return (
        DistressProfile("clean", "must_pass"),
        DistressProfile("peak_normalized", "must_pass"),
        DistressProfile("light_recorded_proxy", "stretch_goal"),
        DistressProfile("moderate_recorded_proxy", "exploratory"),
    )


def _apply_distress(audio: PcmAudio, name: str) -> PcmAudio:
    """Apply one named synthetic real-world distress profile."""

    if name == "clean":
        return audio
    if name == "peak_normalized":
        return normalize_peak(audio, 0.85)
    if name == "light_recorded_proxy":
        transformed = resample_audio(resample_audio(audio, 12000), audio.sample_rate)
        transformed = low_pass_filter(transformed, 3800.0)
        transformed = add_reverberation(transformed, 0.080, 0.10, seed=20261010)
        transformed = add_white_noise(transformed, 35.0, seed=20261010)
        return normalize_peak(transformed, 0.85)
    if name == "moderate_recorded_proxy":
        transformed = resample_audio(resample_audio(audio, 10000), audio.sample_rate)
        transformed = low_pass_filter(transformed, 3400.0)
        transformed = add_reverberation(transformed, 0.120, 0.16, seed=20261010)
        transformed = add_white_noise(transformed, 30.0, seed=20261010)
        return normalize_peak(transformed, 0.82)
    raise ValueError(f"unknown distress profile: {name}")


def _prefilter(source: PcmAudio, suspicious_crop: PcmAudio) -> tuple[object, tuple[object, ...], float]:
    """Run source-audio crop localization on an already-cropped suspicious excerpt."""

    registry_fingerprints = _registry_blocks(source, BLOCK_SECONDS)
    started = perf_counter()
    trial, candidates = _trial(Path(TARGET_FILE), suspicious_crop, registry_fingerprints, CROP_SECONDS, 0.0)
    return trial, _unique_candidates(candidates), (perf_counter() - started) * 1000.0


def _outcome(
    codec: BlockAttributionCodec,
    source: PcmAudio,
    embeddings: tuple[object, ...],
    clean_crop: PcmAudio,
    profile: DistressProfile,
) -> tuple[DistressOutcome, dict[str, object]]:
    """Run one distressed fanout workflow and return diagnostics."""

    suspicious = _apply_distress(clean_crop, profile.name)
    prefilter_trial, candidates, prefilter_elapsed_ms = _prefilter(source, suspicious)
    registry_records = _records()
    started = perf_counter()
    raw = tuple(
        _verify_export(
            codec,
            suspicious,
            embedding,
            candidates,
            registry_records[index].is_leaked_copy,
            registry_records[index].label,
        )[0]
        for index, embedding in enumerate(embeddings)
    )
    ranked = _rank(raw)
    verification_elapsed_ms = (perf_counter() - started) * 1000.0
    correct = next(item for item in ranked if item.expected_match)
    false_acceptances = sum(item.recovered and not item.expected_match for item in ranked)
    outcome = DistressOutcome(
        profile.name,
        profile.expectation,
        correct.rank,
        correct.recovered,
        correct.pooled_rs_cost,
        false_acceptances,
        prefilter_elapsed_ms,
        verification_elapsed_ms,
        correct.recovered and false_acceptances == 0,
    )
    details = {
        "prefilter_trial": asdict(prefilter_trial),
        "prefilter_candidates": [asdict(candidate) for candidate in candidates],
        "ranked_verifications": [asdict(item) for item in ranked],
    }
    return outcome, details


def run(samples_dir: Path = SAMPLES_DIR) -> dict[str, object]:
    """Run the distressed fanout validation suite."""

    source = read_pcm16_wav(samples_dir / TARGET_FILE)
    codec = BlockAttributionCodec(b"prefilter-embedding-fanout")
    embeddings = _embed_exports(codec, source)
    crop_start = _crop_start(embeddings[LEAKED_INDEX].audio)
    clean_crop = _crop(embeddings[LEAKED_INDEX].audio, crop_start, CROP_SECONDS)
    results = tuple(_outcome(codec, source, embeddings, clean_crop, profile) for profile in _profiles())
    manifest = {
        "goal": "validate known-song fanout under named suspicious-excerpt distress",
        "source_file": TARGET_FILE,
        "crop_seconds": CROP_SECONDS,
        "crop_start_seconds": crop_start,
        "outcomes": [asdict(outcome) for outcome, _ in results],
        "details": {outcome.distress: details for outcome, details in results},
    }
    OUTPUT_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def main() -> None:
    """Print the distressed known-song fanout validation."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
