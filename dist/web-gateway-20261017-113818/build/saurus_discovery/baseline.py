"""Record no-notification discovery baseline runs.

Before any client alerts, the discovery pilot needs a baseline period where
operators measure source filtering and candidate review outcomes. This module
binds those local measurements into one run record and rejects any nonzero
client notification count. It does not crawl, send alerts, or make attribution
claims.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .adjudication import CandidateAdjudicationSnapshot
from .source_metrics import FeedSourceMetricsSnapshot


@dataclass(frozen=True, slots=True)
class DiscoveryBaselineRun:
    """Summarize one no-notification discovery baseline run."""

    run_id: str
    reviewer_id: str
    started_utc: datetime
    completed_utc: datetime
    source_metrics: tuple[FeedSourceMetricsSnapshot, ...]
    adjudication: CandidateAdjudicationSnapshot
    client_notification_count: int = 0

    def __post_init__(self) -> None:
        """Validate baseline identity, timing, and no-notification boundary."""

        _require_text(self.run_id, "run_id")
        _require_text(self.reviewer_id, "reviewer_id")
        _require_aware(self.started_utc, "started_utc")
        _require_aware(self.completed_utc, "completed_utc")
        if self.completed_utc < self.started_utc:
            raise ValueError("completed_utc must not be before started_utc")
        if not self.source_metrics:
            raise ValueError("source_metrics must not be empty")
        if self.client_notification_count != 0:
            raise ValueError("baseline runs must not send client notifications")

    @property
    def policy_denial_count(self) -> int:
        """Return total URL policy denials observed during the baseline."""

        return sum(metric.policy_denial_count for metric in self.source_metrics)

    @property
    def duplicate_count(self) -> int:
        """Return total duplicate URLs plus duplicate adjudication labels."""

        return sum(metric.duplicate_count for metric in self.source_metrics) + self.adjudication.duplicate_count

    @property
    def emitted_candidate_count(self) -> int:
        """Return total source-emitted candidate count."""

        return sum(metric.emitted_candidate_count for metric in self.source_metrics)


def _require_text(value: str, name: str) -> None:
    """Require one visible text value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _require_aware(value: datetime, name: str) -> None:
    """Require one timezone-aware timestamp."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
