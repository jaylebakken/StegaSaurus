"""Apply public-source opt-out requests to discovery review candidates.

Opt-out handling is part of the discovery pilot rehearsal. This module records
the request and suppresses matching pending candidates without notifying clients
or making attribution claims. Full legal retention, regional deletion policy,
and production persistence remain separate launch work.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .models import ReviewState
from .review import ReviewQueue


@dataclass(frozen=True, slots=True)
class OptOutRequest:
    """Record one public source opt-out request."""

    request_id: str
    source_id: str
    canonical_url: str
    requester: str
    reason: str
    received_utc: datetime

    def __post_init__(self) -> None:
        """Validate visible opt-out request fields."""

        for value, name in (
            (self.request_id, "request_id"),
            (self.source_id, "source_id"),
            (self.canonical_url, "canonical_url"),
            (self.requester, "requester"),
            (self.reason, "reason"),
        ):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        if self.received_utc.tzinfo is None or self.received_utc.utcoffset() is None:
            raise ValueError("received_utc must be timezone-aware")


@dataclass(frozen=True, slots=True)
class OptOutResult:
    """Summarize one applied opt-out request."""

    request_id: str
    suppressed_candidate_ids: tuple[str, ...]
    completed_utc: datetime
    completion_hours: float


def apply_opt_out(queue: ReviewQueue, request: OptOutRequest, completed_utc: datetime) -> OptOutResult:
    """Suppress pending candidates that match one opt-out source URL."""

    if completed_utc.tzinfo is None or completed_utc.utcoffset() is None:
        raise ValueError("completed_utc must be timezone-aware")
    if completed_utc < request.received_utc:
        raise ValueError("completed_utc must not be before received_utc")
    suppressed = []
    for candidate in queue.pending(completed_utc):
        if candidate.source_id == request.source_id and candidate.canonical_url == request.canonical_url:
            queue.decide(candidate.candidate_id, ReviewState.SUPPRESSED, request.requester, f"opt-out: {request.reason}", completed_utc)
            suppressed.append(candidate.candidate_id)
    hours = (completed_utc - request.received_utc).total_seconds() / 3600.0
    return OptOutResult(request.request_id, tuple(suppressed), completed_utc, hours)
