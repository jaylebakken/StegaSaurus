"""Run iteration 034: multi-encode watermark interference.

Goal: identify whether encoding the same song multiple times creates a
capacity/pooling bottleneck before combining crop recovery with distress
recovery. A likely V4.x temptation is to add redundant watermarks or repeat
recipient handles to survive crops. This experiment asks whether stacking
independent handles on the same waveform destroys the intended claim, causes
wrong-handle recovery, or merely raises the pooled Reed--Solomon cost.

Toy flow:
    source song -> encode handle 0 -> encode handle 1 on the result -> ...
        -> verify each retained record against the final stacked waveform
        -> rank intended and wrong-handle outcomes by RS cost

This is a clean retained-record interference test. It does not yet include
unknown-crop localization, distress transforms, or recorded-audio proxies.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json
from pathlib import Path

from ....attribution import BlockAttributionCodec
from ....pilot import PcmAudio, read_pcm16_wav


SAMPLES_DIR = Path("samples")
OUTPUT_PATH = Path(__file__).with_name("results.json")
TARGET_FILE = "10. Lovers Rock.wav"
STACK_COUNTS = (1, 2, 3, 4, 6, 8)
BLOCK_SECONDS = 30.0
MAXIMUM_RS_COST = 16


@dataclass(frozen=True, slots=True)
class HandleOutcome:
    """Record one retained handle's verification against the final stacked audio."""

    handle_index: int
    handle_hex: str
    recovered: bool
    pooled_rs_cost: int
    block_votes: int
    rank: int


@dataclass(frozen=True, slots=True)
class StackOutcome:
    """Summarize one stacked multi-encode run."""

    stack_count: int
    recovered_handles: int
    best_handle_index: int
    best_handle_recovered: bool
    wrong_recovered_handles: int
    maximum_recovered_index: int | None
    minimum_rs_cost: int
    median_rs_cost: float
    notes: str


def _handle(index: int) -> bytes:
    """Return one deterministic four-byte registry handle."""

    return (0xC1000000 + index).to_bytes(4, "big")


def _stack(codec: BlockAttributionCodec, source: PcmAudio, count: int) -> tuple[PcmAudio, tuple[object, ...]]:
    """Encode the source repeatedly and retain every block record."""

    current = source
    records = []
    for index in range(count):
        embedding = codec.embed(current, _handle(index), block_seconds=BLOCK_SECONDS)
        current = embedding.audio
        records.append(embedding.record)
    return current, tuple(records)


def _outcomes(codec: BlockAttributionCodec, audio: PcmAudio, records: tuple[object, ...]) -> tuple[HandleOutcome, ...]:
    """Verify every retained record against the final stacked waveform."""

    raw = []
    for index, record in enumerate(records):
        verification = codec.verify(audio, record)
        raw.append(
            HandleOutcome(
                index,
                record.handle.hex().upper(),
                verification.recovered and verification.pooled_verification.claim_rs_cost <= MAXIMUM_RS_COST,
                verification.pooled_verification.claim_rs_cost,
                verification.recovered_block_count,
                0,
            )
        )
    ranked = sorted(raw, key=lambda item: (not item.recovered, item.pooled_rs_cost, item.handle_index))
    return tuple(
        HandleOutcome(item.handle_index, item.handle_hex, item.recovered, item.pooled_rs_cost, item.block_votes, rank)
        for rank, item in enumerate(ranked, start=1)
    )


def _summary(stack_count: int, outcomes: tuple[HandleOutcome, ...]) -> StackOutcome:
    """Convert ranked handle outcomes into stack-level bottleneck diagnostics."""

    recovered = tuple(item for item in outcomes if item.recovered)
    best = outcomes[0]
    rs_costs = tuple(sorted(item.pooled_rs_cost for item in outcomes))
    wrong_recovered = tuple(item for item in recovered if item.handle_index != stack_count - 1)
    return StackOutcome(
        stack_count,
        len(recovered),
        best.handle_index,
        best.recovered,
        len(wrong_recovered),
        max((item.handle_index for item in recovered), default=None),
        min(rs_costs),
        _median(rs_costs),
        _note(stack_count, recovered, wrong_recovered, best),
    )


def _median(values: tuple[int, ...]) -> float:
    """Return the median of a non-empty sorted integer tuple."""

    middle = len(values) // 2
    if len(values) % 2:
        return float(values[middle])
    return (values[middle - 1] + values[middle]) / 2.0


def _note(stack_count: int, recovered: tuple[HandleOutcome, ...], wrong_recovered: tuple[HandleOutcome, ...], best: HandleOutcome) -> str:
    """Name the practical interpretation of a stacked encode result."""

    if not recovered:
        return "all stacked handles lost under clean retained-record verification"
    if wrong_recovered and best.handle_index != stack_count - 1:
        return "older watermark evidence can outrank the most recent encode"
    if len(recovered) > 1:
        return "multiple stacked handles remain recoverable; attribution is ambiguous without candidate selection"
    return "only one stacked handle recovered"


def run(samples_dir: Path = SAMPLES_DIR) -> dict[str, object]:
    """Run the multi-encode interference suite."""

    source = read_pcm16_wav(samples_dir / TARGET_FILE)
    codec = BlockAttributionCodec(b"multi-encode-interference")
    results = []
    details = {}
    for count in STACK_COUNTS:
        audio, records = _stack(codec, source, count)
        outcomes = _outcomes(codec, audio, records)
        summary = _summary(count, outcomes)
        results.append(summary)
        details[str(count)] = [asdict(outcome) for outcome in outcomes]
    manifest = {
        "goal": "measure whether stacked watermarks interfere with pooling and attribution identity",
        "source_file": TARGET_FILE,
        "block_seconds": BLOCK_SECONDS,
        "maximum_rs_cost": MAXIMUM_RS_COST,
        "summaries": [asdict(result) for result in results],
        "handle_outcomes": details,
        "recommendation": _recommendation(tuple(results)),
    }
    OUTPUT_PATH.write_text(json.dumps(manifest, indent=2, sort_keys=True), encoding="utf-8")
    return manifest


def _recommendation(results: tuple[StackOutcome, ...]) -> str:
    """Return the next-step recommendation for crop-plus-distress optimization."""

    ambiguous = tuple(result for result in results if result.wrong_recovered_handles)
    if ambiguous:
        return "avoid stacking independent export handles; measure repeated same-handle redundancy instead"
    failing = tuple(result for result in results if not result.best_handle_recovered)
    if failing:
        return "stacking lowers capacity before ambiguity appears; optimize shorter/same-handle blocks instead"
    return "stacking did not fail in this clean test; continue with cropped and distressed stacked controls"


def main() -> None:
    """Print the multi-encode interference manifest."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
