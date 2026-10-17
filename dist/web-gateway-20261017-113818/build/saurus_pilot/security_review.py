"""Record external security review scope and production blocking status.

Saurus can rehearse many security expectations locally, but production launch
still needs an independent review of the hosted API, tenant isolation, key
custody, desktop credential path, infrastructure, and discovery crawler
boundary. This module is intentionally a signoff record, not a scanner. A toy
flow is:

1. Give the reviewer the scope packet and alpha evidence.
2. Record which required areas were reviewed.
3. Block production if any required area is missing or critical/high findings
   remain open.

The record does not claim security readiness by itself. It only preserves the
review result in a form that release gates can evaluate.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

__all__ = [
    "REQUIRED_SECURITY_REVIEW_AREAS",
    "SecurityReviewArea",
    "SecurityReviewSignoff",
    "record_security_review_signoff",
]


class SecurityReviewArea(str, Enum):
    """Name one production security review area."""

    API_AUTHORIZATION = "api_authorization"
    TENANT_ISOLATION = "tenant_isolation"
    KEY_MANAGEMENT = "key_management"
    DESKTOP_CREDENTIALS = "desktop_credentials"
    INFRASTRUCTURE = "infrastructure"
    DISCOVERY_CRAWLER = "discovery_crawler"
    PRIVACY_RETENTION = "privacy_retention"


REQUIRED_SECURITY_REVIEW_AREAS: tuple[SecurityReviewArea, ...] = (
    SecurityReviewArea.API_AUTHORIZATION,
    SecurityReviewArea.TENANT_ISOLATION,
    SecurityReviewArea.KEY_MANAGEMENT,
    SecurityReviewArea.DESKTOP_CREDENTIALS,
    SecurityReviewArea.INFRASTRUCTURE,
    SecurityReviewArea.DISCOVERY_CRAWLER,
    SecurityReviewArea.PRIVACY_RETENTION,
)


@dataclass(frozen=True, slots=True)
class SecurityReviewSignoff:
    """Summarize an external review result for production release gates."""

    reviewer_id: str
    report_reference: str
    reviewed_utc: datetime
    areas: tuple[SecurityReviewArea, ...]
    critical_open_count: int
    high_open_count: int
    medium_open_count: int
    summary: str
    production_ready: bool
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate review provenance and finding counts."""

        _require_text(self.reviewer_id, "reviewer_id")
        _require_text(self.report_reference, "report_reference")
        _require_text(self.summary, "summary")
        _require_aware(self.reviewed_utc, "reviewed_utc")
        for value, name in (
            (self.critical_open_count, "critical_open_count"),
            (self.high_open_count, "high_open_count"),
            (self.medium_open_count, "medium_open_count"),
        ):
            if value < 0:
                raise ValueError(f"{name} must be non-negative")
        if self.production_ready and self.blockers:
            raise ValueError("production_ready cannot be true while blockers exist")


def record_security_review_signoff(
    reviewer_id: str,
    report_reference: str,
    reviewed_utc: datetime,
    areas: tuple[SecurityReviewArea, ...],
    critical_open_count: int,
    high_open_count: int,
    medium_open_count: int,
    summary: str,
) -> SecurityReviewSignoff:
    """Create a production gate record from external security review evidence."""

    for area in areas:
        if not isinstance(area, SecurityReviewArea):
            raise TypeError("areas must contain SecurityReviewArea values")
    unique_areas = tuple(dict.fromkeys(areas))
    missing = tuple(area for area in REQUIRED_SECURITY_REVIEW_AREAS if area not in unique_areas)
    blockers = _blockers(missing, critical_open_count, high_open_count)
    return SecurityReviewSignoff(
        reviewer_id,
        report_reference,
        reviewed_utc,
        unique_areas,
        critical_open_count,
        high_open_count,
        medium_open_count,
        summary,
        not blockers,
        blockers,
    )


def _blockers(
    missing: tuple[SecurityReviewArea, ...],
    critical_open_count: int,
    high_open_count: int,
) -> tuple[str, ...]:
    """List production blockers from review scope and finding severity."""

    blockers: list[str] = []
    if missing:
        blockers.append("missing review areas: " + ", ".join(area.value for area in missing))
    if critical_open_count:
        blockers.append(f"{critical_open_count} critical finding(s) remain open")
    if high_open_count:
        blockers.append(f"{high_open_count} high finding(s) remain open")
    return tuple(blockers)


def _require_text(value: str, name: str) -> None:
    """Require one visible text value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _require_aware(value: datetime, name: str) -> None:
    """Require one timezone-aware timestamp."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
