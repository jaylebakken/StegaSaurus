"""Record legal and policy review scope for production readiness.

Saurus separates technical evidence from conclusions, and discovery is not
allowed to become an automatic accusation workflow. Before production, counsel
and a policy owner must review the language and operating rules around evidence,
discovery sources, client notices, opt-out handling, and retention/deletion.

This module records that review in a small gate object:

1. Name the reviewed legal/policy areas.
2. Require counsel, policy owner, client-policy reference, and timestamp.
3. Block production readiness if required areas are missing or counsel has not
   approved the packet.

The record does not provide legal advice or approve deletion tooling by itself.
It preserves whether the production legal/policy gate has sufficient review
evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

__all__ = [
    "LegalPolicyReviewArea",
    "LegalPolicyReviewRecord",
    "REQUIRED_LEGAL_POLICY_REVIEW_AREAS",
    "record_legal_policy_review",
]


class LegalPolicyReviewArea(str, Enum):
    """Name one required legal or policy review area."""

    EVIDENCE_LANGUAGE = "evidence_language"
    DISCOVERY_SOURCE_POLICY = "discovery_source_policy"
    CLIENT_ALERTS_AND_NOTICES = "client_alerts_and_notices"
    OPT_OUT_AND_CORRECTIONS = "opt_out_and_corrections"
    RETENTION_AND_DELETION = "retention_and_deletion"


REQUIRED_LEGAL_POLICY_REVIEW_AREAS: tuple[LegalPolicyReviewArea, ...] = tuple(LegalPolicyReviewArea)


@dataclass(frozen=True, slots=True)
class LegalPolicyReviewRecord:
    """Summarize legal and policy review evidence for production gates."""

    counsel_reviewer_id: str
    policy_owner_id: str
    client_policy_reference: str
    reviewed_utc: datetime
    areas: tuple[LegalPolicyReviewArea, ...]
    counsel_approved: bool
    summary: str
    production_ready: bool
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate legal/policy review provenance."""

        for value, name in (
            (self.counsel_reviewer_id, "counsel_reviewer_id"),
            (self.policy_owner_id, "policy_owner_id"),
            (self.client_policy_reference, "client_policy_reference"),
            (self.summary, "summary"),
        ):
            _require_text(value, name)
        _require_aware(self.reviewed_utc, "reviewed_utc")
        for area in self.areas:
            if not isinstance(area, LegalPolicyReviewArea):
                raise TypeError("areas must contain LegalPolicyReviewArea values")
        if self.production_ready and self.blockers:
            raise ValueError("production_ready cannot be true while blockers exist")


def record_legal_policy_review(
    counsel_reviewer_id: str,
    policy_owner_id: str,
    client_policy_reference: str,
    reviewed_utc: datetime,
    areas: tuple[LegalPolicyReviewArea, ...],
    counsel_approved: bool,
    summary: str,
) -> LegalPolicyReviewRecord:
    """Create a legal/policy review record and compute production blockers."""

    for area in areas:
        if not isinstance(area, LegalPolicyReviewArea):
            raise TypeError("areas must contain LegalPolicyReviewArea values")
    unique_areas = tuple(dict.fromkeys(areas))
    missing = tuple(area for area in REQUIRED_LEGAL_POLICY_REVIEW_AREAS if area not in unique_areas)
    blockers = _blockers(missing, counsel_approved)
    return LegalPolicyReviewRecord(
        counsel_reviewer_id,
        policy_owner_id,
        client_policy_reference,
        reviewed_utc,
        unique_areas,
        counsel_approved,
        summary,
        not blockers,
        blockers,
    )


def _blockers(missing: tuple[LegalPolicyReviewArea, ...], counsel_approved: bool) -> tuple[str, ...]:
    """List legal/policy review blockers."""

    blockers: list[str] = []
    if missing:
        blockers.append("missing legal/policy review areas: " + ", ".join(area.value for area in missing))
    if not counsel_approved:
        blockers.append("counsel approval is missing")
    return tuple(blockers)


def _require_text(value: str, name: str) -> None:
    """Require one visible text value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _require_aware(value: datetime, name: str) -> None:
    """Require one timezone-aware timestamp."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
