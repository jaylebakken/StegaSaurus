"""Evaluate registry launch metrics against explicit thresholds.

The registry plan names launch gates for finalize success, stale-reservation
reconciliation, API latency, bounded verification bundles, audit identity, and
backup restore time. This module turns those measurements into a written local
decision record. It does not pick production SLOs; callers must pass thresholds
derived from a real pilot or deployment review.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .access_review import RegistryAccessReviewSnapshot
from .api_metrics import RegistryApiMetricsSnapshot
from .maintenance import BackupRestoreRehearsalResult
from .metrics import RegistryMetricsSnapshot


@dataclass(frozen=True, slots=True)
class RegistryLaunchThresholds:
    """Declare explicit numeric gates for registry launch review."""

    minimum_finalize_rate: float
    maximum_reconciliation_rate: float
    minimum_audit_identity_rate: float
    minimum_access_probe_pass_rate: float
    maximum_access_probe_failures: int
    maximum_handle_collision_count: int
    maximum_issuance_attempts_per_active_export: float
    maximum_p95_latency_ms: float
    maximum_api_error_rate: float
    maximum_response_bytes: int
    maximum_bundle_record_count: int
    maximum_truncated_bundle_count: int
    maximum_backup_restore_ms: float

    def __post_init__(self) -> None:
        """Validate threshold ranges."""

        for value, name in (
            (self.minimum_finalize_rate, "minimum_finalize_rate"),
            (self.maximum_reconciliation_rate, "maximum_reconciliation_rate"),
            (self.minimum_audit_identity_rate, "minimum_audit_identity_rate"),
            (self.minimum_access_probe_pass_rate, "minimum_access_probe_pass_rate"),
            (self.maximum_api_error_rate, "maximum_api_error_rate"),
        ):
            _require_rate(value, name)
        if self.maximum_access_probe_failures < 0:
            raise ValueError("maximum_access_probe_failures must not be negative")
        if self.maximum_handle_collision_count < 0:
            raise ValueError("maximum_handle_collision_count must not be negative")
        if self.maximum_p95_latency_ms < 0 or self.maximum_backup_restore_ms < 0 or self.maximum_issuance_attempts_per_active_export < 0:
            raise ValueError("latency and restore thresholds must not be negative")
        if self.maximum_response_bytes < 0 or self.maximum_bundle_record_count < 0 or self.maximum_truncated_bundle_count < 0:
            raise ValueError("size and bundle thresholds must not be negative")


@dataclass(frozen=True, slots=True)
class RegistryLaunchDecision:
    """Summarize whether measured registry gates pass."""

    go: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class RegistryLaunchDecisionRecord:
    """Bind one registry launch decision to reviewer and measured evidence."""

    metrics: RegistryMetricsSnapshot
    access_review: RegistryAccessReviewSnapshot
    api_metrics: RegistryApiMetricsSnapshot
    backup_restore: BackupRestoreRehearsalResult
    thresholds: RegistryLaunchThresholds
    reviewer_id: str
    decided_utc: datetime
    summary: str
    decision: RegistryLaunchDecision

    def __post_init__(self) -> None:
        """Validate written decision metadata."""

        _require_text(self.reviewer_id, "reviewer_id")
        _require_text(self.summary, "summary")
        _require_aware(self.decided_utc, "decided_utc")


def evaluate_registry_launch(
    metrics: RegistryMetricsSnapshot,
    access_review: RegistryAccessReviewSnapshot,
    api_metrics: RegistryApiMetricsSnapshot,
    backup_restore: BackupRestoreRehearsalResult,
    thresholds: RegistryLaunchThresholds,
) -> RegistryLaunchDecision:
    """Evaluate measured registry launch metrics against declared thresholds."""

    reasons: list[str] = []
    if metrics.finalize_rate < thresholds.minimum_finalize_rate:
        reasons.append("finalize rate is below threshold")
    if metrics.reconciliation_rate > thresholds.maximum_reconciliation_rate:
        reasons.append("reconciliation rate is above threshold")
    if metrics.audit_identity_rate < thresholds.minimum_audit_identity_rate:
        reasons.append("audit identity rate is below threshold")
    if access_review.pass_rate < thresholds.minimum_access_probe_pass_rate:
        reasons.append("access probe pass rate is below threshold")
    if access_review.failed_count > thresholds.maximum_access_probe_failures:
        reasons.append("access probe failures are above threshold")
    if metrics.handle_collision_count > thresholds.maximum_handle_collision_count:
        reasons.append("handle collision count is above threshold")
    if metrics.issuance_attempts_per_active_export > thresholds.maximum_issuance_attempts_per_active_export:
        reasons.append("issuance attempts per active export is above threshold")
    if api_metrics.p95_latency_ms > thresholds.maximum_p95_latency_ms:
        reasons.append("p95 API latency is above threshold")
    if api_metrics.error_rate > thresholds.maximum_api_error_rate:
        reasons.append("API error rate is above threshold")
    if api_metrics.max_response_bytes > thresholds.maximum_response_bytes:
        reasons.append("API response size is above threshold")
    if api_metrics.max_bundle_record_count > thresholds.maximum_bundle_record_count:
        reasons.append("verification bundle size is above threshold")
    if api_metrics.truncated_bundle_count > thresholds.maximum_truncated_bundle_count:
        reasons.append("verification bundles were truncated above threshold")
    if backup_restore.total_elapsed_ms > thresholds.maximum_backup_restore_ms:
        reasons.append("backup restore rehearsal time is above threshold")
    return RegistryLaunchDecision(not reasons, tuple(reasons))


def record_registry_launch_decision(
    metrics: RegistryMetricsSnapshot,
    access_review: RegistryAccessReviewSnapshot,
    api_metrics: RegistryApiMetricsSnapshot,
    backup_restore: BackupRestoreRehearsalResult,
    thresholds: RegistryLaunchThresholds,
    reviewer_id: str,
    decided_utc: datetime,
    summary: str,
) -> RegistryLaunchDecisionRecord:
    """Create a written registry launch decision from measured gates."""

    return RegistryLaunchDecisionRecord(
        metrics,
        access_review,
        api_metrics,
        backup_restore,
        thresholds,
        reviewer_id,
        decided_utc,
        summary,
        evaluate_registry_launch(metrics, access_review, api_metrics, backup_restore, thresholds),
    )


def _require_rate(value: float, name: str) -> None:
    """Require one numeric rate from zero through one."""

    if not 0.0 <= value <= 1.0:
        raise ValueError(f"{name} must be between zero and one")


def _require_text(value: str, name: str) -> None:
    """Require one visible text value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _require_aware(value: datetime, name: str) -> None:
    """Require one timezone-aware timestamp."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
