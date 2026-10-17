"""Run iteration 009: sweep block watermark schemas across song lengths.

Goal: compare one full-song codeword with repeated independently recoverable
blocks for 30-second, 2.5-minute, and 5-minute covers. This is an analytical
planning iteration grounded in measured per-block recovery behavior, not a new
audio robustness claim.

Toy flow:
    song duration -> block cadence -> independent recovery opportunities
        -> any-block and k-of-n voting estimates

The model assumes the current 30-second block profile and decision policy from
the blind-recovery experiments. It does not simulate codecs, perceptual quality,
or interactions from overlapping real audio embeddings.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
import json


@dataclass(frozen=True, slots=True)
class SongLength:
    """Describe one song duration to evaluate."""

    name: str
    duration_seconds: int


@dataclass(frozen=True, slots=True)
class BlockSchema:
    """Describe one repeated-block watermark layout."""

    name: str
    block_seconds: int
    stride_seconds: int
    voting_threshold: int


@dataclass(frozen=True, slots=True)
class SchemaResult:
    """Record block opportunities and simple independent-recovery estimates."""

    song_name: str
    schema_name: str
    block_count: int
    minimum_clip_seconds: int
    any_block_recovery_probability: float
    threshold_recovery_probability: float
    estimated_full_file_attempts: int


def _songs() -> tuple[SongLength, ...]:
    """Return the cover lengths requested for early planning."""

    return (
        SongLength("thirty_seconds", 30),
        SongLength("two_and_half_minutes", 150),
        SongLength("five_minutes", 300),
    )


def _schemas() -> tuple[BlockSchema, ...]:
    """Return candidate block layouts for song-scale watermarking."""

    return (
        BlockSchema("single_full_song_codeword", 30, 30, 1),
        BlockSchema("thirty_second_any_block", 30, 30, 1),
        BlockSchema("thirty_second_two_vote", 30, 30, 2),
        BlockSchema("overlap_30s_every_15s_any_block", 30, 15, 1),
        BlockSchema("overlap_30s_every_15s_two_vote", 30, 15, 2),
    )


def _block_count(song: SongLength, schema: BlockSchema) -> int:
    """Return complete block starts for a song and schema."""

    if schema.name == "single_full_song_codeword":
        return 1
    if song.duration_seconds < schema.block_seconds:
        return 0
    return 1 + (song.duration_seconds - schema.block_seconds) // schema.stride_seconds


def _binomial_tail(blocks: int, threshold: int, per_block_probability: float) -> float:
    """Return probability that at least threshold independent blocks recover."""

    if blocks < threshold:
        return 0.0
    total = 0.0
    for successes in range(threshold, blocks + 1):
        combinations = _combinations(blocks, successes)
        total += combinations * per_block_probability**successes * (1.0 - per_block_probability) ** (blocks - successes)
    return total


def _combinations(total: int, selected: int) -> int:
    """Return n choose k for small integer planning values."""

    if selected < 0 or selected > total:
        return 0
    selected = min(selected, total - selected)
    value = 1
    for index in range(1, selected + 1):
        value = value * (total - selected + index) // index
    return value


def _result(song: SongLength, schema: BlockSchema, per_block_probability: float) -> SchemaResult:
    """Evaluate one schema under a simple independent block model."""

    blocks = _block_count(song, schema)
    threshold = schema.voting_threshold
    full_file_attempts = blocks if schema.name != "single_full_song_codeword" else 1
    probability = _binomial_tail(blocks, threshold, per_block_probability)
    return SchemaResult(
        song.name,
        schema.name,
        blocks,
        schema.block_seconds,
        _binomial_tail(blocks, 1, per_block_probability),
        probability,
        full_file_attempts,
    )


def run(per_block_probability: float = 0.8) -> dict[str, object]:
    """Run the block schema length sweep."""

    songs = _songs()
    schemas = _schemas()
    results = tuple(_result(song, schema, per_block_probability) for song in songs for schema in schemas)
    return {
        "goal": "compare repeated block watermark schemas across song lengths",
        "per_block_probability_assumption": per_block_probability,
        "songs": [asdict(song) for song in songs],
        "schemas": [asdict(schema) for schema in schemas],
        "recommendation": "prefer repeated 30-second blocks with 15-30 second stride over one full-song codeword",
        "results": [asdict(result) for result in results],
    }


def main() -> None:
    """Print the block schema planning sweep."""

    print(json.dumps(run(), indent=2, sort_keys=True))


if __name__ == "__main__":
    main()
