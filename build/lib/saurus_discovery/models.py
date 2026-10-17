"""Define public-web discovery records without private registry material.

Discovery stores public source provenance and song-level review candidates. It
does not copy recipient labels, watermark keys, carrier maps, or retained
private attribution records. Candidate records are evidence for human review,
not automatic attribution verdicts.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ReviewState(str, Enum):
    """Name the explicit human review state for one discovery candidate."""

    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    SUPPRESSED = "suppressed"
    EXPIRED = "expired"
    DELETED = "deleted"


class CandidateEvidenceClass(str, Enum):
    """Name the evidence boundary for one public discovery candidate."""

    SONG_MATCH_ONLY = "song match only"
    ATTRIBUTION_ELIGIBLE = "attribution eligible"


@dataclass(frozen=True, slots=True)
class SourceReview:
    """Record policy approval for one public source connector."""

    source_id: str
    owner: str
    approved: bool
    robots_reviewed: bool
    terms_reviewed: bool
    contact: str
    retention_days: int
    reviewed_utc: datetime

    def __post_init__(self) -> None:
        """Validate visible review metadata and bounded retention."""

        for value, name in ((self.source_id, "source_id"), (self.owner, "owner"), (self.contact, "contact")):
            _require_text(value, name)
        if self.retention_days < 0:
            raise ValueError("retention_days must not be negative")
        _require_aware(self.reviewed_utc, "reviewed_utc")


@dataclass(frozen=True, slots=True)
class ConnectorPolicy:
    """Declare source-specific public URL and rate-limit rules."""

    source_id: str
    allowed_domains: tuple[str, ...]
    allowed_schemes: tuple[str, ...] = ("https",)
    max_results_per_job: int = 100
    per_host_concurrency: int = 1

    def __post_init__(self) -> None:
        """Validate connector limits before scheduling."""

        _require_text(self.source_id, "source_id")
        if not self.allowed_domains:
            raise ValueError("allowed_domains must not be empty")
        if self.max_results_per_job < 1 or self.per_host_concurrency < 1:
            raise ValueError("connector budgets must be positive")


@dataclass(frozen=True, slots=True)
class DiscoveryTarget:
    """Represent one client-approved song monitoring target."""

    tenant_id: str
    song_id: str
    title: str
    public_fingerprint_id: str

    def __post_init__(self) -> None:
        """Reject empty target identity values."""

        for value, name in (
            (self.tenant_id, "tenant_id"),
            (self.song_id, "song_id"),
            (self.title, "title"),
            (self.public_fingerprint_id, "public_fingerprint_id"),
        ):
            _require_text(value, name)


@dataclass(frozen=True, slots=True)
class PageCandidate:
    """Describe one public page emitted by a source connector."""

    source_id: str
    url: str
    title: str
    discovered_utc: datetime

    def __post_init__(self) -> None:
        """Validate public page provenance."""

        for value, name in ((self.source_id, "source_id"), (self.url, "url"), (self.title, "title")):
            _require_text(value, name)
        _require_aware(self.discovered_utc, "discovered_utc")


@dataclass(frozen=True, slots=True)
class CandidateRecord:
    """Store a song-level candidate for human review."""

    candidate_id: str
    tenant_id: str
    song_id: str
    source_id: str
    canonical_url: str
    match_score: float
    matched_seconds: float
    state: ReviewState
    discovered_utc: datetime
    expires_utc: datetime

    def __post_init__(self) -> None:
        """Validate candidate identity, score, and review interval."""

        for value, name in (
            (self.candidate_id, "candidate_id"),
            (self.tenant_id, "tenant_id"),
            (self.song_id, "song_id"),
            (self.source_id, "source_id"),
            (self.canonical_url, "canonical_url"),
        ):
            _require_text(value, name)
        if not 0.0 <= self.match_score <= 1.0 or self.matched_seconds < 0:
            raise ValueError("candidate score and matched duration are out of range")
        _require_aware(self.discovered_utc, "discovered_utc")
        _require_aware(self.expires_utc, "expires_utc")
        if self.expires_utc <= self.discovered_utc:
            raise ValueError("expires_utc must be after discovered_utc")


@dataclass(frozen=True, slots=True)
class CandidateEvidenceDecision:
    """Explain whether a discovery candidate can enter attribution follow-up."""

    candidate_id: str
    evidence_class: CandidateEvidenceClass
    reason: str
    matched_seconds: float
    minimum_attribution_seconds: float

    def __post_init__(self) -> None:
        """Validate decision identity and duration threshold."""

        _require_text(self.candidate_id, "candidate_id")
        _require_text(self.reason, "reason")
        if self.matched_seconds < 0 or self.minimum_attribution_seconds < 0:
            raise ValueError("evidence durations must not be negative")


def classify_candidate_evidence(candidate: CandidateRecord, minimum_attribution_seconds: float) -> CandidateEvidenceDecision:
    """Classify a public candidate as song-only or eligible for attribution follow-up."""

    if minimum_attribution_seconds < 0:
        raise ValueError("minimum_attribution_seconds must not be negative")
    if candidate.matched_seconds < minimum_attribution_seconds:
        return CandidateEvidenceDecision(
            candidate.candidate_id,
            CandidateEvidenceClass.SONG_MATCH_ONLY,
            "matched public duration is too short for attribution verification",
            candidate.matched_seconds,
            minimum_attribution_seconds,
        )
    return CandidateEvidenceDecision(
        candidate.candidate_id,
        CandidateEvidenceClass.ATTRIBUTION_ELIGIBLE,
        "matched public duration meets attribution handoff threshold",
        candidate.matched_seconds,
        minimum_attribution_seconds,
    )


def _require_text(value: str, name: str) -> None:
    """Require one visible text value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _require_aware(value: datetime, name: str) -> None:
    """Require one timezone-aware timestamp."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
