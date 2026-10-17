"""Measure discovery review burden from queued candidates.

Discovery pilot gates include human review burden and latency. This module
derives those values from the review queue's local snapshots without changing
candidate state and without making attribution claims.
"""

from __future__ import annotations

from dataclasses import dataclass
from statistics import median

from .models import ReviewState
from .review import ReviewQueue, ReviewSnapshot


@dataclass(frozen=True, slots=True)
class ReviewMetricsSnapshot:
    """Summarize review queue burden and timing."""

    candidate_count: int
    pending_count: int
    reviewed_count: int
    accepted_count: int
    rejected_count: int
    suppressed_count: int
    expired_count: int
    deleted_count: int
    median_review_minutes: float
    accepted_median_review_minutes: float


def review_metrics_snapshot(queue: ReviewQueue) -> ReviewMetricsSnapshot:
    """Return review burden and latency metrics for the current queue."""

    snapshots = queue.snapshots()
    review_minutes = tuple(_review_minutes(snapshot) for snapshot in snapshots if snapshot.actions)
    accepted_minutes = tuple(
        _review_minutes(snapshot)
        for snapshot in snapshots
        if snapshot.candidate.state is ReviewState.ACCEPTED and snapshot.actions
    )
    states = tuple(snapshot.candidate.state for snapshot in snapshots)
    return ReviewMetricsSnapshot(
        candidate_count=len(snapshots),
        pending_count=states.count(ReviewState.PENDING),
        reviewed_count=sum(1 for state in states if state is not ReviewState.PENDING),
        accepted_count=states.count(ReviewState.ACCEPTED),
        rejected_count=states.count(ReviewState.REJECTED),
        suppressed_count=states.count(ReviewState.SUPPRESSED),
        expired_count=states.count(ReviewState.EXPIRED),
        deleted_count=states.count(ReviewState.DELETED),
        median_review_minutes=_median_or_zero(review_minutes),
        accepted_median_review_minutes=_median_or_zero(accepted_minutes),
    )


def _review_minutes(snapshot: ReviewSnapshot) -> float:
    """Return minutes from candidate discovery to first recorded review action."""

    first_action = min(snapshot.actions, key=lambda action: action.occurred_utc)
    elapsed = first_action.occurred_utc - snapshot.candidate.discovered_utc
    if elapsed.total_seconds() < 0:
        raise ValueError("review action cannot occur before candidate discovery")
    return elapsed.total_seconds() / 60.0


def _median_or_zero(values: tuple[float, ...]) -> float:
    """Return a zero-safe median for measured durations."""

    return 0.0 if not values else float(median(values))
