"""Plan recurring registry maintenance without starting a daemon.

The registry has explicit operations for stale-reservation reconciliation,
backup rehearsal, restore rehearsal, and key-rotation rehearsal. Deployment
still decides how those jobs are run. This module only records a small schedule
contract: which operations are enabled, when they are due, and how to advance a
job after it completes.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timedelta


@dataclass(frozen=True, slots=True)
class ScheduledRegistryOperation:
    """Describe one recurring registry operation."""

    name: str
    interval: timedelta
    next_due_utc: datetime
    enabled: bool = True


def default_registry_operations(start_utc: datetime) -> tuple[ScheduledRegistryOperation, ...]:
    """Return the initial local schedule for registry operational jobs."""

    _require_aware(start_utc, "start_utc")
    return (
        ScheduledRegistryOperation("expire-stale-reservations", timedelta(minutes=15), start_utc),
        ScheduledRegistryOperation("backup-restore-rehearsal", timedelta(days=1), start_utc + timedelta(days=1)),
        ScheduledRegistryOperation("record-key-rotation-rehearsal", timedelta(days=30), start_utc + timedelta(days=30)),
    )


def due_registry_operations(
    operations: tuple[ScheduledRegistryOperation, ...],
    now_utc: datetime,
) -> tuple[ScheduledRegistryOperation, ...]:
    """Return enabled operations due at or before ``now_utc``."""

    _require_aware(now_utc, "now_utc")
    checked = tuple(_validated(operation) for operation in operations)
    return tuple(sorted((operation for operation in checked if operation.enabled and operation.next_due_utc <= now_utc), key=lambda item: item.next_due_utc))


def mark_registry_operation_run(operation: ScheduledRegistryOperation, completed_utc: datetime) -> ScheduledRegistryOperation:
    """Advance one operation after a successful run."""

    checked = _validated(operation)
    _require_aware(completed_utc, "completed_utc")
    return replace(checked, next_due_utc=completed_utc + checked.interval)


def _validated(operation: ScheduledRegistryOperation) -> ScheduledRegistryOperation:
    """Validate one operation record before schedule decisions."""

    _require_text(operation.name, "name")
    if operation.interval <= timedelta(0):
        raise ValueError("interval must be positive")
    _require_aware(operation.next_due_utc, "next_due_utc")
    return operation


def _require_text(value: str, name: str) -> None:
    """Require a non-empty string."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _require_aware(value: datetime, name: str) -> None:
    """Require a timezone-aware timestamp."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
