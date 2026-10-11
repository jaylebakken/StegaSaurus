"""Run iteration 035: chain-ledger workflow and attack-surface stress test.

Goal: design a custody-chain ledger and test whether independent child updates
can be encoded without decreasing watermark robustness. The ledger is useful if
it can record parent-child lifecycle events, but the audio layer must not turn
chain updates into a misattribution or denial-of-attribution weakness.

Toy flow:
    source song -> chain event 0 -> optional child update 1 -> optional child 2
        -> named transform -> verify every event record -> classify chain state

This experiment deliberately keeps user labels separate from system facts. A
recovered event proves only that a registry handle matched, not that a typed
recipient label is absolute truth.
"""

from __future__ import annotations

from dataclasses import asdict
import json
from pathlib import Path

from ....attacks import add_reverberation, add_white_noise, low_pass_filter, normalize_peak, resample_audio, trim_audio
from ....attribution import BlockAttributionCodec
from ....pilot import PcmAudio, read_pcm16_wav
from .models import ChainLedgerEvent, EventEvidence, ScenarioOutcome


SAMPLES_DIR = Path("samples")
OUTPUT_PATH = Path(__file__).with_name("results.json")
TARGET_FILE = "10. Lovers Rock.wav"
BLOCK_SECONDS = 30.0
MAXIMUM_RS_COST = 16


def _handle(index: int) -> bytes:
    """Return a deterministic chain-event handle."""

    return (0xD1000000 + index).to_bytes(4, "big")


def _event(index: int) -> ChainLedgerEvent:
    """Create one append-only ledger event with separated label and fact fields."""

    return ChainLedgerEvent(
        f"event_{index:02d}",
        None if index == 0 else f"event_{index - 1:02d}",
        _handle(index).hex().upper(),
        "system_created",
        f"user supplied recipient/update label {index}",
        f"local registry embedded handle for chain event {index}",
    )


def _encode_chain(codec: BlockAttributionCodec, source: PcmAudio, length: int) -> tuple[PcmAudio, tuple[object, ...], tuple[ChainLedgerEvent, ...]]:
    """Encode independent child events as sequential watermark updates."""

    current = source
    records = []
    events = []
    for index in range(length):
        embedding = codec.embed(current, _handle(index), block_seconds=BLOCK_SECONDS)
        current = embedding.audio
        records.append(embedding.record)
        events.append(_event(index))
    return current, tuple(records), tuple(events)


def _apply_transform(audio: PcmAudio, name: str) -> PcmAudio:
    """Apply one named stress transform to the chain audio."""

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
    if name == "leading_crop_30s":
        return trim_audio(audio, 30.0, audio.duration_seconds)
    raise ValueError(f"unknown transform: {name}")


def _evidence(codec: BlockAttributionCodec, audio: PcmAudio, records: tuple[object, ...], events: tuple[ChainLedgerEvent, ...]) -> tuple[EventEvidence, ...]:
    """Verify every retained event record against one received signal."""

    raw = []
    for event, record in zip(events, records):
        verification = codec.verify(audio, record)
        raw.append(
            EventEvidence(
                event.event_id,
                event.handle_hex,
                verification.recovered and verification.pooled_verification.claim_rs_cost <= MAXIMUM_RS_COST,
                verification.pooled_verification.claim_rs_cost,
                verification.recovered_block_count,
                0,
            )
        )
    ranked = sorted(raw, key=lambda item: (not item.recovered, item.pooled_rs_cost, item.event_id))
    return tuple(
        EventEvidence(item.event_id, item.handle_hex, item.recovered, item.pooled_rs_cost, item.block_votes, rank)
        for rank, item in enumerate(ranked, start=1)
    )


def _scenario(codec: BlockAttributionCodec, source: PcmAudio, length: int, transform: str) -> tuple[ScenarioOutcome, tuple[ChainLedgerEvent, ...], tuple[EventEvidence, ...]]:
    """Run one chain length and transform scenario."""

    encoded, records, events = _encode_chain(codec, source, length)
    received = _apply_transform(encoded, transform)
    evidence = _evidence(codec, received, records, events)
    recovered = tuple(item for item in evidence if item.recovered)
    latest = events[-1].event_id
    latest_recovered = any(item.event_id == latest and item.recovered for item in evidence)
    unexpected = tuple(item for item in recovered if item.event_id != latest)
    best = evidence[0] if evidence else None
    outcome = ScenarioOutcome(
        f"chain_{length}_{transform}",
        length,
        transform,
        len(recovered),
        latest_recovered,
        len(unexpected),
        None if best is None else best.event_id,
        None if best is None else best.pooled_rs_cost,
        _status(length, transform, recovered, latest_recovered, unexpected),
    )
    return outcome, events, evidence


def _status(
    length: int,
    transform: str,
    recovered: tuple[EventEvidence, ...],
    latest_recovered: bool,
    unexpected: tuple[EventEvidence, ...],
) -> str:
    """Classify the chain evidence without overclaiming user labels."""

    if unexpected:
        return "ambiguous_chain_evidence"
    if latest_recovered:
        return "latest_event_recovered"
    if recovered:
        return "older_event_only"
    if length > 1 and transform == "clean":
        return "independent_update_destroyed_chain_evidence"
    return "no_recoverable_chain_event"


def run(samples_dir: Path = SAMPLES_DIR) -> dict[str, object]:
    """Run the chain-ledger attack surface suite."""

    source = read_pcm16_wav(samples_dir / TARGET_FILE)
    codec = BlockAttributionCodec(b"chain-ledger-attack-surface")
    plans = (
        (1, "clean"),
        (1, "peak_normalized"),
        (1, "light_recorded_proxy"),
        (1, "leading_crop_30s"),
        (2, "clean"),
        (2, "peak_normalized"),
        (2, "light_recorded_proxy"),
        (3, "clean"),
    )
    results = tuple(_scenario(codec, source, length, transform) for length, transform in plans)
    manifest = {
        "goal": "design a chain ledger and stress independent update robustness",
        "source_file": TARGET_FILE,
        "ledger_design": _ledger_design(),
        "outcomes": [asdict(outcome) for outcome, _, _ in results],
        "events": {outcome.scenario: [asdict(event) for event in events] for outcome, events, _ in results},
        "evidence": {outcome.scenario: [asdict(item) for item in evidence] for outcome, _, evidence in results},
        "recommendation": _recommendation(tuple(outcome for outcome, _, _ in results)),
    }
    OUTPUT_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def _ledger_design() -> dict[str, object]:
    """Return the registry design principles captured by this experiment."""

    return {
        "system_fact_fields": ("event_id", "parent_event_id", "handle_hex", "trust_level", "system_fact"),
        "user_supplied_fields": ("user_label",),
        "trust_levels": ("system_created", "system_verified", "imported_signed", "imported_untrusted", "user_label_only"),
        "policy": "verification may identify a registry event; user labels remain context, not absolute fault claims",
    }


def _recommendation(outcomes: tuple[ScenarioOutcome, ...]) -> str:
    """Return the next product/research recommendation."""

    destructive = any(outcome.status == "independent_update_destroyed_chain_evidence" for outcome in outcomes)
    if destructive:
        return "do not ship independent child re-watermarking as V4.x robustness; implement ledger first, then test same-handle or partitioned updates"
    return "chain updates survived this first stress pass; expand to branch and open-world controls"


def main() -> None:
    """Print the chain-ledger attack-surface manifest."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
