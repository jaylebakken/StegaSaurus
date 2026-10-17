"""Record production tenant-isolation probe readiness.

Tenant isolation is a cross-system property. Local registry tests can prove
specific repository and API expectations, but production launch also needs
evidence that deployed credentials, backups, KMS grants, discovery projections,
and crawler boundaries do not cross tenant lines. This module records that
evidence as a launch gate:

1. Name each required isolation boundary.
2. Attach a probe or review reference for that boundary.
3. Block production readiness if any required boundary is missing or failing.

The record does not run network probes or replace external security review. It
keeps the tenant-isolation production gate concrete and auditable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

__all__ = [
    "REQUIRED_TENANT_ISOLATION_BOUNDARIES",
    "TenantIsolationBoundary",
    "TenantIsolationProbeEvidence",
    "TenantIsolationReadinessRecord",
    "record_tenant_isolation_readiness",
]


class TenantIsolationBoundary(str, Enum):
    """Name one required tenant-isolation boundary."""

    REGISTRY_API_AUTHORIZATION = "registry_api_authorization"
    REGISTRY_REPOSITORY_SCOPE = "registry_repository_scope"
    KMS_GRANT_SCOPE = "kms_grant_scope"
    BACKUP_AND_EXPORT_SCOPE = "backup_and_export_scope"
    DISCOVERY_PROJECTION = "discovery_projection"
    CRAWLER_NETWORK_SEPARATION = "crawler_network_separation"


REQUIRED_TENANT_ISOLATION_BOUNDARIES: tuple[TenantIsolationBoundary, ...] = tuple(TenantIsolationBoundary)


@dataclass(frozen=True, slots=True)
class TenantIsolationProbeEvidence:
    """Record one tenant-isolation probe or review result."""

    boundary: TenantIsolationBoundary
    evidence_reference: str
    reviewer_id: str
    passed: bool

    def __post_init__(self) -> None:
        """Validate one tenant-isolation evidence item."""

        if not isinstance(self.boundary, TenantIsolationBoundary):
            raise TypeError("boundary must be a TenantIsolationBoundary")
        _require_text(self.evidence_reference, "evidence_reference")
        _require_text(self.reviewer_id, "reviewer_id")


@dataclass(frozen=True, slots=True)
class TenantIsolationReadinessRecord:
    """Summarize tenant-isolation readiness for production launch."""

    evidence: tuple[TenantIsolationProbeEvidence, ...]
    reviewed_utc: datetime
    reviewer_id: str
    summary: str
    production_ready: bool
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate tenant-isolation readiness provenance."""

        _require_aware(self.reviewed_utc, "reviewed_utc")
        _require_text(self.reviewer_id, "reviewer_id")
        _require_text(self.summary, "summary")
        if self.production_ready and self.blockers:
            raise ValueError("production_ready cannot be true while blockers exist")


def record_tenant_isolation_readiness(
    evidence: tuple[TenantIsolationProbeEvidence, ...],
    reviewed_utc: datetime,
    reviewer_id: str,
    summary: str,
) -> TenantIsolationReadinessRecord:
    """Create a tenant-isolation readiness record and compute blockers."""

    blockers = _blockers(evidence)
    return TenantIsolationReadinessRecord(evidence, reviewed_utc, reviewer_id, summary, not blockers, blockers)


def _blockers(evidence: tuple[TenantIsolationProbeEvidence, ...]) -> tuple[str, ...]:
    """List missing or failing tenant-isolation boundaries."""

    by_boundary = {item.boundary: item for item in evidence}
    blockers: list[str] = []
    missing = tuple(boundary for boundary in REQUIRED_TENANT_ISOLATION_BOUNDARIES if boundary not in by_boundary)
    if missing:
        blockers.append("missing tenant-isolation boundaries: " + ", ".join(boundary.value for boundary in missing))
    failing = tuple(item.boundary for item in evidence if not item.passed)
    if failing:
        blockers.append("failing tenant-isolation boundaries: " + ", ".join(boundary.value for boundary in failing))
    return tuple(blockers)


def _require_text(value: str, name: str) -> None:
    """Require one visible text value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _require_aware(value: datetime, name: str) -> None:
    """Require one timezone-aware timestamp."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
