"""Track connector health, canaries, budgets, and disable controls.

Discovery connectors should be expandable one source at a time. Before that can
happen safely, operators need a small control surface: disable one connector
without stopping all discovery, record canary health, and count run outcomes for
dashboards or manual review. This module is in-memory for the pilot and does
not perform live crawling.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime


@dataclass(frozen=True, slots=True)
class ConnectorHealthSnapshot:
    """Summarize one connector's operational control and health state."""

    source_id: str
    enabled: bool
    disabled_reason: str
    run_count: int
    candidate_count: int
    failure_count: int
    last_error: str
    canary_passed: bool | None
    canary_checked_utc: datetime | None
    canary_latency_ms: float | None
    canary_reason: str


class ConnectorControlPlane:
    """Hold per-connector disable state, canary results, and run budgets."""

    def __init__(self) -> None:
        """Initialize an empty control plane with connectors enabled by default."""

        self._snapshots: dict[str, ConnectorHealthSnapshot] = {}

    def disable(self, source_id: str, reason: str) -> ConnectorHealthSnapshot:
        """Disable one connector with an operator-visible reason."""

        _require_text(reason, "reason")
        current = self._snapshot(source_id)
        updated = replace(current, enabled=False, disabled_reason=reason.strip())
        self._snapshots[current.source_id] = updated
        return updated

    def enable(self, source_id: str) -> ConnectorHealthSnapshot:
        """Enable one connector and clear its disable reason."""

        current = self._snapshot(source_id)
        updated = replace(current, enabled=True, disabled_reason="")
        self._snapshots[current.source_id] = updated
        return updated

    def record_run(self, source_id: str, candidate_count: int, error: str = "") -> ConnectorHealthSnapshot:
        """Record one scheduled connector run for dashboard counters."""

        if candidate_count < 0:
            raise ValueError("candidate_count must not be negative")
        current = self._snapshot(source_id)
        updated = replace(
            current,
            run_count=current.run_count + 1,
            candidate_count=current.candidate_count + candidate_count,
            failure_count=current.failure_count + (1 if error else 0),
            last_error=error.strip(),
        )
        self._snapshots[current.source_id] = updated
        return updated

    def record_canary(
        self,
        source_id: str,
        *,
        passed: bool,
        checked_utc: datetime,
        latency_ms: float,
        reason: str = "",
    ) -> ConnectorHealthSnapshot:
        """Record one connector canary result without fetching live media."""

        if checked_utc.tzinfo is None or checked_utc.utcoffset() is None:
            raise ValueError("checked_utc must be timezone-aware")
        if latency_ms < 0:
            raise ValueError("latency_ms must not be negative")
        current = self._snapshot(source_id)
        updated = replace(
            current,
            canary_passed=passed,
            canary_checked_utc=checked_utc,
            canary_latency_ms=latency_ms,
            canary_reason=reason.strip(),
        )
        self._snapshots[current.source_id] = updated
        return updated

    def snapshot(self, source_id: str) -> ConnectorHealthSnapshot:
        """Return the current connector health snapshot."""

        return self._snapshot(source_id)

    def is_enabled(self, source_id: str) -> bool:
        """Return whether one connector is allowed to run jobs."""

        return self._snapshot(source_id).enabled

    def _snapshot(self, source_id: str) -> ConnectorHealthSnapshot:
        """Return an existing snapshot or create the enabled default."""

        _require_text(source_id, "source_id")
        return self._snapshots.setdefault(source_id.strip(), _default_snapshot(source_id.strip()))


def _default_snapshot(source_id: str) -> ConnectorHealthSnapshot:
    """Build the default enabled health snapshot for one connector."""

    return ConnectorHealthSnapshot(source_id, True, "", 0, 0, 0, "", None, None, None, "")


def _require_text(value: str, name: str) -> None:
    """Require one visible text value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")
