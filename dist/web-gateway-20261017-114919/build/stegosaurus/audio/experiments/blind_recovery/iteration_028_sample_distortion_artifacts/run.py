"""Run iteration 028: write strongest recoverable distorted sample artifacts.

Goal: create listening examples for every WAV in ``samples``. Each source is
embedded with the product repeated-block codec, using raw audio when possible
and a single whole-song peak normalization only when raw capacity fails. The
script then applies the recorded-proxy severity ladder and saves the strongest
distorted version that still verifies.

Toy flow:
    sample WAV -> raw/normalized preflight -> block attribution embed
        -> distortion ladder -> verify retained block record -> save best WAV

The output files are artifacts for listening and validation. They are not a
claim of general recorded-audio robustness beyond the named synthetic ladder.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path
import re

from ....attacks import normalize_peak
from ....attribution import BlockAttributionCodec
from ....attribution_core.repetition import AttributionCapacityError
from ....pilot import PcmAudio, read_pcm16_wav, write_pcm16_wav
from ..iteration_024_recorded_proxy_upper_bound.run import DistortionLevel, _apply_level, _levels


SAMPLES_DIR = Path("samples")
OUTPUT_DIR = SAMPLES_DIR / "max_distortion_recoverable"
BLOCK_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class ArtifactResult:
    """Record the artifact generated for one source sample."""

    source_file: str
    preflight: str
    block_count: int
    highest_level: str | None
    pooled_rs_cost: int | None
    block_votes: int | None
    output_path: str | None
    status: str


def _slug(name: str) -> str:
    """Return a filesystem-friendly artifact stem."""

    return re.sub(r"[^A-Za-z0-9]+", "_", Path(name).stem).strip("_").lower()


def _embed_source(codec: BlockAttributionCodec, audio: PcmAudio, handle: bytes) -> tuple[str, object]:
    """Embed raw audio when possible, otherwise retry one whole-song normalization."""

    try:
        return "raw", codec.embed(audio, handle, block_seconds=BLOCK_SECONDS)
    except AttributionCapacityError:
        normalized = normalize_peak(audio, 0.90)
        return "whole_song_peak_normalized", codec.embed(normalized, handle, block_seconds=BLOCK_SECONDS)


def _best_distortion(codec: BlockAttributionCodec, embedding: object) -> tuple[DistortionLevel | None, PcmAudio | None, object | None]:
    """Return the strongest recorded-proxy level that verifies."""

    best_level = None
    best_audio = None
    best_verification = None
    for level in _artifact_levels():
        distorted = _apply_artifact_level(embedding.audio, level)
        verification = codec.verify(distorted, embedding.record)
        if verification.recovered:
            best_level = level
            best_audio = distorted
            best_verification = verification
    return best_level, best_audio, best_verification


def _artifact_levels() -> tuple[DistortionLevel, ...]:
    """Return gentle artifact levels plus the established recorded-proxy ladder."""

    return (
        DistortionLevel("level_0_gain_only", 44100, 6000.0, 0.001, 0.0, 300.0, 0.90),
        DistortionLevel("level_0_subtle", 22050, 5000.0, 0.025, 0.03, 45.0, 0.90),
        DistortionLevel("level_0_very_light", 16000, 4200.0, 0.050, 0.06, 40.0, 0.88),
        *_levels(),
    )


def _apply_artifact_level(audio: PcmAudio, level: DistortionLevel) -> PcmAudio:
    """Apply the special gain-only floor or a recorded-proxy level."""

    if level.name == "level_0_gain_only":
        return normalize_peak(audio, level.target_peak)
    return _apply_level(audio, level)


def _process_file(path: Path, codec: BlockAttributionCodec, handle: bytes, output_dir: Path) -> ArtifactResult:
    """Generate one maximally distorted recoverable artifact if possible."""

    audio = read_pcm16_wav(path)
    preflight, embedding = _embed_source(codec, audio, handle)
    level, distorted, verification = _best_distortion(codec, embedding)
    if level is None or distorted is None or verification is None:
        clean_verification = codec.verify(embedding.audio, embedding.record)
        if not clean_verification.recovered:
            return ArtifactResult(
                path.name,
                preflight,
                len(embedding.record.block_records),
                None,
                clean_verification.pooled_verification.claim_rs_cost,
                clean_verification.recovered_block_count,
                None,
                "no_recoverable_artifact",
            )
        output_path = output_dir / f"{_slug(path.name)}__clean_no_extra_distortion.wav"
        write_pcm16_wav(output_path, embedding.audio)
        return ArtifactResult(
            path.name,
            preflight,
            len(embedding.record.block_records),
            "clean_no_extra_distortion",
            clean_verification.pooled_verification.claim_rs_cost,
            clean_verification.recovered_block_count,
            str(output_path),
            "written_clean_ceiling",
        )
    output_path = output_dir / f"{_slug(path.name)}__{level.name}.wav"
    write_pcm16_wav(output_path, distorted)
    return ArtifactResult(
        path.name,
        preflight,
        len(embedding.record.block_records),
        level.name,
        verification.pooled_verification.claim_rs_cost,
        verification.recovered_block_count,
        str(output_path),
        "written",
    )


def run(samples_dir: Path = SAMPLES_DIR, output_dir: Path = OUTPUT_DIR) -> dict[str, object]:
    """Generate strongest recoverable distorted WAVs and a JSON manifest."""

    output_dir.mkdir(parents=True, exist_ok=True)
    codec = BlockAttributionCodec(b"sample-distortion-artifact-secret")
    handle = bytes.fromhex("A1B2C3D4")
    paths = tuple(sorted(path for path in samples_dir.glob("*.wav") if path.parent == samples_dir))
    results = tuple(_process_file(path, codec, handle, output_dir) for path in paths)
    manifest = {
        "goal": "save strongest recorded-proxy distorted WAVs that still verify",
        "output_dir": str(output_dir),
        "results": [asdict(result) for result in results],
    }
    (output_dir / "manifest.json").write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def main() -> None:
    """Print the artifact generation manifest."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
