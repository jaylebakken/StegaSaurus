"""Manage human review decisions for discovery candidates.

The queue records song-level candidate decisions with reviewer identity and
reason text. It keeps discovery evidence separate from recipient attribution:
accepted means "song candidate accepted for follow-up," not "recipient caused a
leak." Persistence can replace this in-memory adapter later behind the same
review operations.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime

from .models import CandidateRecord, ReviewState


@dataclass(frozen=True, slots=True)
class ReviewAction:
    """Record one human or system review transition."""

    candidate_id: str
    reviewer_id: str
    state: ReviewState
    reason: str
    occurred_utc: datetime

    def __post_init__(self) -> None:
        """Validate review provenance."""

        for value, name in ((self.candidate_id, "candidate_id"), (self.reviewer_id, "reviewer_id"), (self.reason, "reason")):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        if self.occurred_utc.tzinfo is None or self.occurred_utc.utcoffset() is None:
            raise ValueError("occurred_utc must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ReviewSnapshot:
    """Return one candidate with its review history."""

    candidate: CandidateRecord
    actions: tuple[ReviewAction, ...]


class ReviewQueue:
    """Keep reviewable candidates and auditable review transitions."""

    def __init__(self) -> None:
        """Initialize an empty in-memory review queue."""

        self._candidates: dict[str, CandidateRecord] = {}
        self._actions: list[ReviewAction] = []

    def add(self, candidate: CandidateRecord) -> CandidateRecord:
        """Add one pending candidate to the queue."""

        if candidate.candidate_id in self._candidates:
            raise ValueError("candidate_id is already queued")
        if candidate.state is not ReviewState.PENDING:
            raise ValueError("new candidates must start pending")
        self._candidates[candidate.candidate_id] = candidate
        return candidate

    def pending(self, now: datetime) -> tuple[CandidateRecord, ...]:
        """Return pending, unexpired candidates ordered by discovery time."""

        self.expire(now)
        return tuple(
            sorted(
                (candidate for candidate in self._candidates.values() if candidate.state is ReviewState.PENDING),
                key=lambda item: (item.discovered_utc, item.candidate_id),
            )
        )

    def decide(
        self,
        candidate_id: str,
        state: ReviewState,
        reviewer_id: str,
        reason: str,
        now: datetime,
    ) -> CandidateRecord:
        """Apply one accepted, rejected, or suppressed review decision."""

        if state not in {ReviewState.ACCEPTED, ReviewState.REJECTED, ReviewState.SUPPRESSED}:
            raise ValueError("review decision state is not allowed")
        current = self._require_pending(candidate_id)
        updated = replace(current, state=state)
        self._candidates[candidate_id] = updated
        self._actions.append(ReviewAction(candidate_id, reviewer_id, state, reason, now))
        return updated

    def expire(self, now: datetime) -> tuple[CandidateRecord, ...]:
        """Expire stale pending candidates and record system review actions."""

        expired: list[CandidateRecord] = []
        for candidate in tuple(self._candidates.values()):
            if candidate.state is ReviewState.PENDING and candidate.expires_utc <= now:
                updated = replace(candidate, state=ReviewState.EXPIRED)
                self._candidates[candidate.candidate_id] = updated
                self._actions.append(ReviewAction(candidate.candidate_id, "system", ReviewState.EXPIRED, "candidate expired", now))
                expired.append(updated)
        return tuple(expired)

    def delete(self, candidate_id: str, reviewer_id: str, reason: str, now: datetime) -> CandidateRecord:
        """Tombstone one candidate and redact retained public URL evidence."""

        candidate = self._candidates.get(candidate_id)
        if candidate is None:
            raise ValueError("candidate_id is not queued")
        if candidate.state is ReviewState.DELETED:
            raise ValueError("candidate is already deleted")
        redacted = replace(candidate, state=ReviewState.DELETED, canonical_url="deleted://candidate")
        self._candidates[candidate_id] = redacted
        self._actions.append(ReviewAction(candidate_id, reviewer_id, ReviewState.DELETED, reason, now))
        return redacted

    def snapshot(self, candidate_id: str) -> ReviewSnapshot:
        """Return one candidate and all recorded review actions."""

        candidate = self._candidates.get(candidate_id)
        if candidate is None:
            raise ValueError("candidate_id is not queued")
        actions = tuple(action for action in self._actions if action.candidate_id == candidate_id)
        return ReviewSnapshot(candidate, actions)

    def snapshots(self) -> tuple[ReviewSnapshot, ...]:
        """Return all candidates with their recorded review actions."""

        return tuple(self.snapshot(candidate_id) for candidate_id in sorted(self._candidates))

    def _require_pending(self, candidate_id: str) -> CandidateRecord:
        """Return one pending candidate or reject terminal reviews."""

        candidate = self._candidates.get(candidate_id)
        if candidate is None:
            raise ValueError("candidate_id is not queued")
        if candidate.state is not ReviewState.PENDING:
            raise ValueError("candidate is no longer pending")
        return candidate
