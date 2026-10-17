"""Record pilot labels for reviewed discovery candidates.

The review queue controls workflow state: pending, accepted, rejected,
suppressed, expired, or deleted. Pilot analysis also needs outcome labels such
as true match, false match, duplicate, and unusable. This module keeps those
labels separate from workflow transitions and recipient attribution claims.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .models import CandidateRecord


class CandidateReviewLabel(str, Enum):
    """Name the pilot outcome label for one reviewed candidate."""

    TRUE_MATCH = "true match"
    FALSE_MATCH = "false match"
    DUPLICATE = "duplicate"
    UNUSABLE = "unusable"


@dataclass(frozen=True, slots=True)
class CandidateAdjudication:
    """Record one pilot outcome label for a discovery candidate."""

    candidate_id: str
    label: CandidateReviewLabel
    reviewer_id: str
    reason: str
    decided_utc: datetime

    def __post_init__(self) -> None:
        """Validate adjudication identity and provenance."""

        for value, name in (
            (self.candidate_id, "candidate_id"),
            (self.reviewer_id, "reviewer_id"),
            (self.reason, "reason"),
        ):
            _require_text(value, name)
        _require_aware(self.decided_utc, "decided_utc")


@dataclass(frozen=True, slots=True)
class CandidateAdjudicationSnapshot:
    """Summarize reviewed candidate labels for pilot metrics."""

    candidate_count: int
    adjudicated_count: int
    true_match_count: int
    false_match_count: int
    duplicate_count: int
    unusable_count: int
    unlabeled_candidate_ids: tuple[str, ...]


def candidate_adjudication_snapshot(
    candidates: tuple[CandidateRecord, ...],
    adjudications: tuple[CandidateAdjudication, ...],
) -> CandidateAdjudicationSnapshot:
    """Return candidate label counts and unlabeled candidate IDs."""

    candidate_ids = {candidate.candidate_id for candidate in candidates}
    labels: dict[str, CandidateAdjudication] = {}
    for adjudication in adjudications:
        if adjudication.candidate_id not in candidate_ids:
            raise ValueError("adjudication candidate_id is not in the candidate set")
        if adjudication.candidate_id in labels:
            raise ValueError("candidate_id is adjudicated more than once")
        labels[adjudication.candidate_id] = adjudication
    values = tuple(adjudication.label for adjudication in labels.values())
    return CandidateAdjudicationSnapshot(
        len(candidates),
        len(labels),
        values.count(CandidateReviewLabel.TRUE_MATCH),
        values.count(CandidateReviewLabel.FALSE_MATCH),
        values.count(CandidateReviewLabel.DUPLICATE),
        values.count(CandidateReviewLabel.UNUSABLE),
        tuple(candidate_id for candidate_id in sorted(candidate_ids) if candidate_id not in labels),
    )


def _require_text(value: str, name: str) -> None:
    """Require one visible text value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _require_aware(value: datetime, name: str) -> None:
    """Require one timezone-aware timestamp."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
