"""Run iteration 036: identify overwrite/tamper-like watermark evidence.

Goal: distinguish "no watermark" from "watermark-like evidence exists but no
claim recovers." Iterations 034 and 035 showed that independent re-watermarking
can destroy both parent and child claims. This experiment asks whether retained
claim diagnostics can classify that state as tamper/overwrite instead of a
plain absence.

Toy flow:
    build clean source, valid watermark, overwritten watermark, crop, distress
        -> verify parent/child/wrong records
        -> classify by accepted claims and RS-cost shape

This is a first-pass diagnostic policy, not a production tamper detector.
"""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from ....attacks import add_reverberation, add_white_noise, low_pass_filter, normalize_peak, resample_audio, trim_audio
from ....attribution import BlockAttributionCodec
from ....pilot import PcmAudio, read_pcm16_wav
from .models import ClaimDiagnostic, IdentificationOutcome


SAMPLES_DIR = Path("samples")
OUTPUT_PATH = Path(__file__).with_name("results.json")
TARGET_FILE = "10. Lovers Rock.wav"
BLOCK_SECONDS = 30.0
ACCEPT_RS_COST = 16
TAMPER_BAND_RS_COST = 24


def _handle(index: int) -> bytes:
    """Return one deterministic diagnostic handle."""

    return (0xE1000000 + index).to_bytes(4, "big")


def _light_proxy(audio: PcmAudio) -> PcmAudio:
    """Apply the light recorded-proxy transform."""

    transformed = resample_audio(resample_audio(audio, 12000), audio.sample_rate)
    transformed = low_pass_filter(transformed, 3800.0)
    transformed = add_reverberation(transformed, 0.080, 0.10, seed=20261010)
    transformed = add_white_noise(transformed, 35.0, seed=20261010)
    return normalize_peak(transformed, 0.85)


def _fixtures(codec: BlockAttributionCodec, source: PcmAudio) -> tuple[dict[str, tuple[str, PcmAudio]], dict[str, object]]:
    """Build scenario audio and retained records."""

    parent = codec.embed(source, _handle(0), block_seconds=BLOCK_SECONDS)
    child = codec.embed(parent.audio, _handle(1), block_seconds=BLOCK_SECONDS)
    wrong = codec.embed(source, _handle(2), block_seconds=BLOCK_SECONDS)
    scenarios = {
        "clean_source": ("absent", source),
        "valid_parent": ("accepted", parent.audio),
        "overwritten_parent_child": ("tamper_suspected", child.audio),
        "distressed_parent": ("accepted", _light_proxy(parent.audio)),
        "cropped_parent": ("geometry_failure", trim_audio(parent.audio, 30.0, parent.audio.duration_seconds)),
    }
    records = {
        "parent": parent.record,
        "child": child.record,
        "wrong": wrong.record,
    }
    return scenarios, records


def _diagnostics(codec: BlockAttributionCodec, audio: PcmAudio, records: dict[str, object]) -> tuple[ClaimDiagnostic, ...]:
    """Verify every retained claim and return ordered diagnostics."""

    diagnostics = []
    for name, record in records.items():
        verification = codec.verify(audio, record)
        pooled = verification.pooled_verification
        diagnostics.append(
            ClaimDiagnostic(
                name,
                verification.recovered and pooled.claim_rs_cost <= ACCEPT_RS_COST,
                pooled.claim_rs_cost,
                pooled.carrier_erasures,
                pooled.known_bit_errors,
                verification.recovered_block_count,
            )
        )
    return tuple(sorted(diagnostics, key=lambda item: (not item.recovered, item.pooled_rs_cost, item.claim_name)))


def _classify(diagnostics: tuple[ClaimDiagnostic, ...], audio: PcmAudio, reference: PcmAudio) -> str:
    """Classify one scenario from claim diagnostics and geometry."""

    accepted = tuple(item for item in diagnostics if item.recovered)
    if accepted:
        return "accepted"
    if audio.sample_rate != reference.sample_rate or len(audio.samples) < len(reference.samples):
        return "geometry_failure"
    best = diagnostics[0]
    second = diagnostics[1] if len(diagnostics) > 1 else None
    if best.pooled_rs_cost <= TAMPER_BAND_RS_COST and second is not None and second.pooled_rs_cost <= TAMPER_BAND_RS_COST + 8:
        return "tamper_suspected"
    return "absent"


def _outcome(name: str, expected: str, predicted: str, diagnostics: tuple[ClaimDiagnostic, ...]) -> IdentificationOutcome:
    """Build one scenario outcome from ordered diagnostics."""

    accepted = sum(item.recovered for item in diagnostics)
    best = diagnostics[0].pooled_rs_cost
    second = diagnostics[1].pooled_rs_cost if len(diagnostics) > 1 else None
    gap = None if second is None else second - best
    return IdentificationOutcome(name, expected, predicted, accepted, best, second, gap, expected == predicted)


def run(samples_dir: Path = SAMPLES_DIR) -> dict[str, object]:
    """Run the tamper-identification diagnostic suite."""

    source = read_pcm16_wav(samples_dir / TARGET_FILE)
    codec = BlockAttributionCodec(b"tamper-identification")
    scenarios, records = _fixtures(codec, source)
    results = []
    details = {}
    for name, (expected, audio) in scenarios.items():
        diagnostics = _diagnostics(codec, audio, records)
        predicted = _classify(diagnostics, audio, source)
        results.append(_outcome(name, expected, predicted, diagnostics))
        details[name] = [asdict(item) for item in diagnostics]
    manifest = {
        "goal": "separate overwrite/tamper-like evidence from absence and ordinary failures",
        "source_file": TARGET_FILE,
        "accept_rs_cost": ACCEPT_RS_COST,
        "tamper_band_rs_cost": TAMPER_BAND_RS_COST,
        "outcomes": [asdict(result) for result in results],
        "diagnostics": details,
        "recommendation": _recommendation(tuple(results)),
    }
    OUTPUT_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def _recommendation(results: tuple[IdentificationOutcome, ...]) -> str:
    """Return the next-step recommendation for tamper identification."""

    if all(result.matched_expected for result in results):
        return "promote tamper_suspected as an experimental result state and expand controls"
    return "diagnostic policy is not yet stable; add more features before product integration"


def main() -> None:
    """Print the tamper-identification manifest."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
