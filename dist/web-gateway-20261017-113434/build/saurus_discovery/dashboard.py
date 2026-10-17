"""Build local discovery dashboard snapshots and operator alerts.

The discovery pilot needs a visible control surface before live crawling or
client notifications. This module composes existing source-coverage and review
metrics into a small dashboard record. It does not send alerts, crawl sources,
or score media; it only names conditions that need human attention.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from .coverage import SourceCoverageSnapshot, source_coverage_snapshot
from .review import ReviewQueue
from .review_metrics import ReviewMetricsSnapshot, review_metrics_snapshot
from .sources import SourceCatalog


class DiscoveryAlertSeverity(str, Enum):
    """Name the severity of one discovery dashboard alert."""

    INFO = "info"
    WARNING = "warning"
    BLOCKER = "blocker"


@dataclass(frozen=True, slots=True)
class DiscoveryAlert:
    """Describe one operator-visible discovery condition."""

    severity: DiscoveryAlertSeverity
    code: str
    message: str
    source_id: str = ""

    def __post_init__(self) -> None:
        """Validate alert identity and visible text."""

        _require_text(self.code, "code")
        _require_text(self.message, "message")


@dataclass(frozen=True, slots=True)
class DiscoveryDashboardSnapshot:
    """Summarize discovery health for an internal pilot dashboard."""

    coverage: SourceCoverageSnapshot
    review_metrics: ReviewMetricsSnapshot
    alerts: tuple[DiscoveryAlert, ...]

    @property
    def blocker_count(self) -> int:
        """Return how many dashboard alerts block pilot expansion."""

        return sum(1 for alert in self.alerts if alert.severity is DiscoveryAlertSeverity.BLOCKER)

    @property
    def warning_count(self) -> int:
        """Return how many dashboard alerts need operator attention."""

        return sum(1 for alert in self.alerts if alert.severity is DiscoveryAlertSeverity.WARNING)


def discovery_dashboard_snapshot(
    catalog: SourceCatalog,
    review_queue: ReviewQueue,
    *,
    pending_warning_count: int,
    median_review_warning_minutes: float,
) -> DiscoveryDashboardSnapshot:
    """Return one local dashboard snapshot for source health and review burden."""

    if pending_warning_count < 0:
        raise ValueError("pending_warning_count must not be negative")
    if median_review_warning_minutes < 0:
        raise ValueError("median_review_warning_minutes must not be negative")
    coverage = source_coverage_snapshot(catalog)
    review_metrics = review_metrics_snapshot(review_queue)
    return DiscoveryDashboardSnapshot(
        coverage,
        review_metrics,
        _alerts(catalog, coverage, review_metrics, pending_warning_count, median_review_warning_minutes),
    )


def _alerts(
    catalog: SourceCatalog,
    coverage: SourceCoverageSnapshot,
    review_metrics: ReviewMetricsSnapshot,
    pending_warning_count: int,
    median_review_warning_minutes: float,
) -> tuple[DiscoveryAlert, ...]:
    """Build deterministic dashboard alerts from local snapshots."""

    alerts: list[DiscoveryAlert] = []
    if coverage.registered_source_count == 0:
        alerts.append(DiscoveryAlert(DiscoveryAlertSeverity.BLOCKER, "no-sources", "No discovery sources are registered."))
    if coverage.ready_source_count == 0 and coverage.registered_source_count > 0:
        alerts.append(DiscoveryAlert(DiscoveryAlertSeverity.BLOCKER, "no-ready-sources", "No registered discovery sources are ready."))
    for entry in catalog.entries():
        if not entry.control.enabled:
            alerts.append(DiscoveryAlert(DiscoveryAlertSeverity.WARNING, "source-disabled", entry.control.disabled_reason, entry.source_id))
        if entry.control.last_error:
            alerts.append(DiscoveryAlert(DiscoveryAlertSeverity.WARNING, "source-error", entry.control.last_error, entry.source_id))
        if entry.control.canary_passed is False:
            reason = entry.control.canary_reason or "Connector canary failed."
            alerts.append(DiscoveryAlert(DiscoveryAlertSeverity.BLOCKER, "canary-failed", reason, entry.source_id))
    if review_metrics.pending_count > pending_warning_count:
        alerts.append(DiscoveryAlert(DiscoveryAlertSeverity.WARNING, "review-backlog", "Pending candidate count exceeds the dashboard threshold."))
    if review_metrics.median_review_minutes > median_review_warning_minutes:
        alerts.append(DiscoveryAlert(DiscoveryAlertSeverity.WARNING, "review-latency", "Median review time exceeds the dashboard threshold."))
    if not alerts:
        alerts.append(DiscoveryAlert(DiscoveryAlertSeverity.INFO, "healthy", "Discovery dashboard has no local alerts."))
    return tuple(alerts)


def _require_text(value: str, name: str) -> None:
    """Require one visible text value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")
