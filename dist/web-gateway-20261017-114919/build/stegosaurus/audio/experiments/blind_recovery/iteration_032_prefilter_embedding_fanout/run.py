"""Run iteration 032: shared prefilter to embedding-record fanout.

Goal: test the workflow that matters to leak attribution: a user selects the
known leaked song, StegaSaurus localizes the suspicious excerpt once using the
song registry, then checks many recipient/export embedding records against the
small candidate window set.

Toy flow:
    one registered song -> many embedded exports -> crop one leaked export
        -> shared registry-audio prefilter -> top windows
        -> verify every export record only on those windows -> rank matches

This remains a known-song registry experiment. It does not search the user's
entire catalog and does not claim robustness beyond the measured clean crop.
"""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path
from time import perf_counter

import numpy as np

from ....attribution import BlockAttributionCodec
from ....attribution_core import AttributionStatus
from ....pilot import PcmAudio, read_pcm16_wav
from ..iteration_031_registry_audio_prefilter.run import _crop, _registry_blocks, _trial, _window
from .models import FanoutSummary, FanoutVerification, SimulatedEmbeddingRecord


SAMPLES_DIR = Path("samples")
OUTPUT_PATH = Path(__file__).with_name("results.json")
TARGET_FILE = "10. Lovers Rock.wav"
BLOCK_SECONDS = 30.0
EMBEDDING_COUNT = 12
LEAKED_INDEX = 7
CROP_SECONDS = 90.0
CROP_START_FRACTION = 0.37
TOP_PREFILTER_WINDOWS = 5
MAXIMUM_ACCEPTED_RS_COST = 16
PHASE_RADIUS_SECONDS = 0.30
PHASE_STRIDE_SECONDS = 0.025


def _handle(index: int) -> bytes:
    """Return a deterministic four-byte handle for one simulated export."""

    return (0xA1000000 + index).to_bytes(4, "big")


def _records() -> tuple[SimulatedEmbeddingRecord, ...]:
    """Return recipient/export records for one simulated song registry."""

    return tuple(
        SimulatedEmbeddingRecord(f"export_{index:02d}", _handle(index).hex().upper(), index == LEAKED_INDEX)
        for index in range(EMBEDDING_COUNT)
    )


def _embed_exports(codec: BlockAttributionCodec, source: PcmAudio) -> tuple[object, ...]:
    """Create watermarked exports for every simulated embedding record."""

    return tuple(codec.embed(source, _handle(index), block_seconds=BLOCK_SECONDS) for index in range(EMBEDDING_COUNT))


def _crop_start(audio: PcmAudio) -> float:
    """Return the deterministic off-grid crop start for the leaked excerpt."""

    return round(max(0.0, audio.duration_seconds - CROP_SECONDS) * CROP_START_FRACTION, 3)


def _prefilter(source: PcmAudio, leaked_audio: PcmAudio, crop_start: float) -> tuple[object, tuple[object, ...]]:
    """Run the shared registry-audio prefilter once for the selected song."""

    registry_fingerprints = _registry_blocks(source, BLOCK_SECONDS)
    trial, candidates = _trial(Path(TARGET_FILE), leaked_audio, registry_fingerprints, CROP_SECONDS, crop_start)
    return trial, _unique_candidates(candidates)


def _unique_candidates(candidates: tuple[object, ...]) -> tuple[object, ...]:
    """Return top candidates with one entry per registry block."""

    selected = []
    seen: set[int] = set()
    for candidate in candidates:
        if candidate.registry_block_index in seen:
            continue
        selected.append(candidate)
        seen.add(candidate.registry_block_index)
        if len(selected) == TOP_PREFILTER_WINDOWS:
            break
    return tuple(selected)


def _candidate_verifications(
    codec: BlockAttributionCodec,
    crop: PcmAudio,
    embedding: object,
    candidates: tuple[object, ...],
) -> tuple[object, ...]:
    """Verify one embedding record against localized candidate windows."""

    verifications = []
    for candidate in candidates:
        block_index = candidate.registry_block_index
        if block_index >= len(embedding.record.block_records):
            continue
        phases = tuple(
            _verify_phase(codec, crop, embedding, block_index, candidate.crop_window_start_seconds + offset)
            for offset in np.arange(-PHASE_RADIUS_SECONDS, PHASE_RADIUS_SECONDS + 0.0001, PHASE_STRIDE_SECONDS)
        )
        verifications.append(min(phases, key=lambda item: (item.claim_rs_cost, item.carrier_erasures, item.known_bit_errors)))
    return tuple(verifications)


def _verify_phase(codec: BlockAttributionCodec, crop: PcmAudio, embedding: object, block_index: int, start_seconds: float) -> object:
    """Verify one fine phase candidate or return all-erasure evidence when out of range."""

    if start_seconds < 0 or start_seconds + BLOCK_SECONDS > crop.duration_seconds:
        return codec._unrecoverable(embedding.record.handle, "phase candidate outside crop")
    window = _window(crop, start_seconds, BLOCK_SECONDS)
    return codec._codec.verify(window, embedding.record.block_records[block_index])


def _verify_export(
    codec: BlockAttributionCodec,
    crop: PcmAudio,
    embedding: object,
    candidates: tuple[object, ...],
    expected_match: bool,
    label: str,
) -> tuple[FanoutVerification, object]:
    """Pool candidate-window evidence for one recipient/export record."""

    verifications = _candidate_verifications(codec, crop, embedding, candidates)
    pooled = codec._pool(embedding.record.handle, list(verifications))
    recovered = pooled.status is AttributionStatus.RECOVERED and pooled.claim_rs_cost <= MAXIMUM_ACCEPTED_RS_COST
    return (
        FanoutVerification(
            label,
            expected_match,
            recovered,
            pooled.claim_rs_cost,
            sum(verification.recovered for verification in verifications),
            0,
            recovered is expected_match,
        ),
        pooled,
    )


def _rank(verifications: tuple[FanoutVerification, ...]) -> tuple[FanoutVerification, ...]:
    """Rank embedding records by acceptance and pooled RS cost."""

    ordered = sorted(verifications, key=lambda item: (not item.recovered, item.pooled_rs_cost, item.label))
    return tuple(
        FanoutVerification(
            item.label,
            item.expected_match,
            item.recovered,
            item.pooled_rs_cost,
            item.recovered_windows,
            rank,
            item.gate_passed,
        )
        for rank, item in enumerate(ordered, start=1)
    )


def run(samples_dir: Path = SAMPLES_DIR) -> dict[str, object]:
    """Run the prefilter-to-fanout attribution workflow simulation."""

    source = read_pcm16_wav(samples_dir / TARGET_FILE)
    codec = BlockAttributionCodec(b"prefilter-embedding-fanout")
    registry_records = _records()
    embeddings = _embed_exports(codec, source)
    leaked = embeddings[LEAKED_INDEX]
    crop_start = _crop_start(leaked.audio)
    suspicious_crop = _crop(leaked.audio, crop_start, CROP_SECONDS)
    started = perf_counter()
    prefilter_trial, candidates = _prefilter(source, leaked.audio, crop_start)
    prefilter_elapsed_ms = (perf_counter() - started) * 1000.0
    started = perf_counter()
    raw = tuple(
        _verify_export(
            codec,
            suspicious_crop,
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
    summary = FanoutSummary(
        TARGET_FILE,
        EMBEDDING_COUNT,
        CROP_SECONDS,
        crop_start,
        prefilter_elapsed_ms,
        verification_elapsed_ms,
        correct.rank,
        correct.recovered,
        false_acceptances,
        correct.recovered and false_acceptances == 0,
    )
    manifest = {
        "goal": "identify a leaked export using one shared crop prefilter plus embedding fanout",
        "scope": "known song, clean crop, simulated recipient/export records",
        "phase_radius_seconds": PHASE_RADIUS_SECONDS,
        "phase_stride_seconds": PHASE_STRIDE_SECONDS,
        "summary": asdict(summary),
        "registry_records": [asdict(record) for record in registry_records],
        "prefilter_trial": asdict(prefilter_trial),
        "prefilter_candidates": [asdict(candidate) for candidate in candidates],
        "ranked_verifications": [asdict(item) for item in ranked],
    }
    OUTPUT_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def main() -> None:
    """Print the prefilter-to-fanout workflow simulation."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
