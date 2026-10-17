"""Measure discovery media fetch and evidence costs.

The discovery pilot should track how many public bytes are fetched, how much
evidence is retained, and how costly useful candidates are. This module records
those counters from already-approved media worker jobs. It does not fetch media,
store media, or decide whether evidence may be retained in production.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class MediaCostRecord:
    """Record bounded byte counters for one media worker result."""

    source_id: str
    fetched_bytes: int
    retained_evidence_bytes: int
    useful_candidate: bool

    def __post_init__(self) -> None:
        """Validate source identity and non-negative byte counters."""

        if not isinstance(self.source_id, str) or not self.source_id.strip():
            raise ValueError("source_id must not be empty")
        if isinstance(self.fetched_bytes, bool) or self.fetched_bytes < 0:
            raise ValueError("fetched_bytes must not be negative")
        if isinstance(self.retained_evidence_bytes, bool) or self.retained_evidence_bytes < 0:
            raise ValueError("retained_evidence_bytes must not be negative")
        if self.retained_evidence_bytes > self.fetched_bytes:
            raise ValueError("retained_evidence_bytes must not exceed fetched_bytes")


@dataclass(frozen=True, slots=True)
class MediaCostSnapshot:
    """Summarize media cost counters for pilot review."""

    record_count: int
    bytes_fetched: int
    retained_evidence_bytes: int
    useful_candidate_count: int
    fetched_bytes_per_useful_candidate: float
    retained_bytes_per_useful_candidate: float


def media_cost_snapshot(records: tuple[MediaCostRecord, ...]) -> MediaCostSnapshot:
    """Return byte and useful-candidate cost metrics."""

    fetched = sum(record.fetched_bytes for record in records)
    retained = sum(record.retained_evidence_bytes for record in records)
    useful = sum(1 for record in records if record.useful_candidate)
    return MediaCostSnapshot(
        record_count=len(records),
        bytes_fetched=fetched,
        retained_evidence_bytes=retained,
        useful_candidate_count=useful,
        fetched_bytes_per_useful_candidate=_per_useful(fetched, useful),
        retained_bytes_per_useful_candidate=_per_useful(retained, useful),
    )


def _per_useful(value: int, useful_candidate_count: int) -> float:
    """Return a zero-safe cost per useful candidate."""

    return 0.0 if useful_candidate_count == 0 else value / useful_candidate_count
