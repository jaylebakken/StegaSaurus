"""Record human approval before discovery leaves the review bench.

Public discovery deliberately stops at song candidates. This module adds a
small approval record for the next step: client alerts, attribution workflow
handoff, or an external notice draft. It does not notify anyone, generate a
notice, or decide recipient attribution. The flow is:

candidate accepted by review -> evidence class checked -> reviewer and counsel
approval recorded -> neutral language screened -> action marked allowed or
blocked with explicit reasons.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .models import CandidateEvidenceClass, CandidateEvidenceDecision, CandidateRecord, ReviewState


class ExternalActionKind(str, Enum):
    """Name the controlled action that may follow discovery review."""

    CLIENT_ALERT = "client alert"
    ATTRIBUTION_HANDOFF = "attribution handoff"
    EXTERNAL_NOTICE = "external notice"


@dataclass(frozen=True, slots=True)
class ExternalActionApproval:
    """Record whether a reviewed candidate may leave the discovery queue."""

    candidate_id: str
    action_kind: ExternalActionKind
    evidence_class: CandidateEvidenceClass
    reviewer_id: str
    counsel_reviewer_id: str
    client_policy_reference: str
    language_summary: str
    approved_utc: datetime
    allowed: bool
    reasons: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate approval identity, timestamps, and recorded reasons."""

        for value, name in (
            (self.candidate_id, "candidate_id"),
            (self.reviewer_id, "reviewer_id"),
            (self.counsel_reviewer_id, "counsel_reviewer_id"),
            (self.client_policy_reference, "client_policy_reference"),
            (self.language_summary, "language_summary"),
        ):
            _require_text(value, name)
        _require_aware(self.approved_utc, "approved_utc")
        if self.allowed and self.reasons:
            raise ValueError("allowed approvals must not carry blocking reasons")
        if not self.allowed and not self.reasons:
            raise ValueError("blocked approvals must explain at least one reason")


def review_external_action(
    candidate: CandidateRecord,
    evidence_decision: CandidateEvidenceDecision,
    action_kind: ExternalActionKind,
    reviewer_id: str,
    counsel_reviewer_id: str,
    client_policy_reference: str,
    language_summary: str,
    approved_utc: datetime,
) -> ExternalActionApproval:
    """Return an approval record for one proposed discovery follow-up action."""

    _require_text(reviewer_id, "reviewer_id")
    _require_text(counsel_reviewer_id, "counsel_reviewer_id")
    _require_text(client_policy_reference, "client_policy_reference")
    _require_text(language_summary, "language_summary")
    _require_aware(approved_utc, "approved_utc")
    if candidate.candidate_id != evidence_decision.candidate_id:
        raise ValueError("candidate and evidence decision identifiers must match")

    reasons: list[str] = []
    if candidate.state is not ReviewState.ACCEPTED:
        reasons.append("candidate must be accepted by human review before follow-up")
    if _contains_accusation(language_summary):
        reasons.append("language summary must stay neutral and avoid accusations")
    if action_kind in (ExternalActionKind.ATTRIBUTION_HANDOFF, ExternalActionKind.EXTERNAL_NOTICE):
        if evidence_decision.evidence_class is not CandidateEvidenceClass.ATTRIBUTION_ELIGIBLE:
            reasons.append("song-match-only evidence cannot support attribution or external notice")

    return ExternalActionApproval(
        candidate.candidate_id,
        action_kind,
        evidence_decision.evidence_class,
        reviewer_id,
        counsel_reviewer_id,
        client_policy_reference,
        language_summary,
        approved_utc,
        not reasons,
        tuple(reasons),
    )


def _require_text(value: str, name: str) -> None:
    """Require one visible text value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _require_aware(value: datetime, name: str) -> None:
    """Require one timezone-aware timestamp."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _contains_accusation(statement: str) -> bool:
    """Return whether text turns discovery evidence into blame."""

    lowered = statement.lower()
    unsafe_fragments = ("leak", "leaked", "stole", "pirated", "guilty", "fault", "accuse", "caused")
    return any(fragment in lowered for fragment in unsafe_fragments)
