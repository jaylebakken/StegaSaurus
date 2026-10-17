"""Record production monitoring, alerting, paging, and budget readiness.

Local metrics and dashboards are useful, but production launch needs evidence
that the right signals are actually wired to operator-owned alert routes. This
module records that gate without depending on a specific monitoring vendor:

1. Name the required monitoring controls.
2. Require an evidence reference and paging owner for each control.
3. Block production readiness if any control is missing, not live, or lacks a
   paging route.

The record does not publish metrics, page anyone, or validate hosted CloudWatch
logs. It keeps the production monitoring gate explicit and auditable.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

__all__ = [
    "MonitoringControl",
    "MonitoringControlEvidence",
    "MonitoringReadinessRecord",
    "REQUIRED_MONITORING_CONTROLS",
    "record_monitoring_readiness",
]


class MonitoringControl(str, Enum):
    """Name one required production monitoring control."""

    REGISTRY_API_METRICS = "registry_api_metrics"
    REGISTRY_HEALTH = "registry_health"
    KMS_GRANT_ALERTS = "kms_grant_alerts"
    BACKUP_RESTORE_ALERTS = "backup_restore_alerts"
    DISCOVERY_DASHBOARD = "discovery_dashboard"
    LOG_PRIVACY_VALIDATION = "log_privacy_validation"
    BUDGET_ALERT = "budget_alert"
    PAGER_ROUTE = "pager_route"


REQUIRED_MONITORING_CONTROLS: tuple[MonitoringControl, ...] = tuple(MonitoringControl)


@dataclass(frozen=True, slots=True)
class MonitoringControlEvidence:
    """Record one monitoring control's deployment evidence."""

    control: MonitoringControl
    evidence_reference: str
    paging_owner_id: str
    live: bool

    def __post_init__(self) -> None:
        """Validate one monitoring control record."""

        if not isinstance(self.control, MonitoringControl):
            raise TypeError("control must be a MonitoringControl")
        _require_text(self.evidence_reference, "evidence_reference")
        _require_text(self.paging_owner_id, "paging_owner_id")


@dataclass(frozen=True, slots=True)
class MonitoringReadinessRecord:
    """Summarize production monitoring readiness for launch gates."""

    controls: tuple[MonitoringControlEvidence, ...]
    reviewed_utc: datetime
    reviewer_id: str
    summary: str
    production_ready: bool
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate monitoring readiness provenance."""

        _require_aware(self.reviewed_utc, "reviewed_utc")
        _require_text(self.reviewer_id, "reviewer_id")
        _require_text(self.summary, "summary")
        if self.production_ready and self.blockers:
            raise ValueError("production_ready cannot be true while blockers exist")


def record_monitoring_readiness(
    controls: tuple[MonitoringControlEvidence, ...],
    reviewed_utc: datetime,
    reviewer_id: str,
    summary: str,
) -> MonitoringReadinessRecord:
    """Create a production monitoring record and compute launch blockers."""

    blockers = _blockers(controls)
    return MonitoringReadinessRecord(controls, reviewed_utc, reviewer_id, summary, not blockers, blockers)


def _blockers(controls: tuple[MonitoringControlEvidence, ...]) -> tuple[str, ...]:
    """List missing or not-live monitoring controls."""

    by_control = {item.control: item for item in controls}
    blockers: list[str] = []
    missing = tuple(control for control in REQUIRED_MONITORING_CONTROLS if control not in by_control)
    if missing:
        blockers.append("missing monitoring controls: " + ", ".join(control.value for control in missing))
    not_live = tuple(item.control for item in controls if not item.live)
    if not_live:
        blockers.append("not-live monitoring controls: " + ", ".join(control.value for control in not_live))
    return tuple(blockers)


def _require_text(value: str, name: str) -> None:
    """Require one visible text value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _require_aware(value: datetime, name: str) -> None:
    """Require one timezone-aware timestamp."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
