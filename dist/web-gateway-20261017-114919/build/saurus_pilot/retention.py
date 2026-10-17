"""Record production retention and deletion readiness evidence.

Retention and deletion are higher-risk than ordinary cleanup because retained
registry records, grant audit events, and discovery candidates can be evidence.
Saurus already has draft policy language and deletion-request audit tooling; a
production launch still needs one readiness record that binds counsel approval,
retention review, backup/export prerequisite, and deletion audit evidence.

This module records that gate only. It does not delete data, redact payloads, or
provide legal advice.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from saurus_registry import DeletionApprovalStatus, RegistryDeletionApproval

__all__ = ["RetentionDeletionReadinessRecord", "record_retention_deletion_readiness"]


@dataclass(frozen=True, slots=True)
class RetentionDeletionReadinessRecord:
    """Summarize retention/deletion readiness for production launch."""

    approval: RegistryDeletionApproval
    retention_review_reference: str
    backup_or_export_reference: str
    deletion_audit_reference: str
    destructive_deletion_enabled: bool
    reviewer_id: str
    reviewed_utc: datetime
    production_ready: bool
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate readiness provenance and consistency."""

        for value, name in (
            (self.retention_review_reference, "retention_review_reference"),
            (self.backup_or_export_reference, "backup_or_export_reference"),
            (self.deletion_audit_reference, "deletion_audit_reference"),
            (self.reviewer_id, "reviewer_id"),
        ):
            _require_text(value, name)
        _require_aware(self.reviewed_utc, "reviewed_utc")
        if self.production_ready and self.blockers:
            raise ValueError("production_ready cannot be true while blockers exist")


def record_retention_deletion_readiness(
    approval: RegistryDeletionApproval,
    retention_review_reference: str,
    backup_or_export_reference: str,
    deletion_audit_reference: str,
    destructive_deletion_enabled: bool,
    reviewer_id: str,
    reviewed_utc: datetime,
) -> RetentionDeletionReadinessRecord:
    """Create a retention/deletion readiness record and compute blockers."""

    blockers = _blockers(approval, destructive_deletion_enabled)
    return RetentionDeletionReadinessRecord(
        approval,
        retention_review_reference,
        backup_or_export_reference,
        deletion_audit_reference,
        destructive_deletion_enabled,
        reviewer_id,
        reviewed_utc,
        not blockers,
        blockers,
    )


def _blockers(approval: RegistryDeletionApproval, destructive_deletion_enabled: bool) -> tuple[str, ...]:
    """List retention/deletion readiness blockers."""

    blockers: list[str] = []
    if approval.status is not DeletionApprovalStatus.COUNSEL_APPROVED:
        blockers.append("retention/deletion policy is not counsel approved")
    if not destructive_deletion_enabled:
        blockers.append("destructive deletion implementation is not enabled")
    return tuple(blockers)


def _require_text(value: str, name: str) -> None:
    """Require one visible text value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _require_aware(value: datetime, name: str) -> None:
    """Require one timezone-aware timestamp."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
