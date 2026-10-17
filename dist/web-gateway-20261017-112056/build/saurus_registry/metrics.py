"""Calculate registry launch-gate metrics from tenant-scoped records.

Operational gates in the registry plan need repeatable measurements, not prose.
This module computes a small snapshot from an explicitly authorized tenant song
list and the tenant audit log. It does not define production SLOs or upload
metrics anywhere; deployment can later publish these values to dashboards.
"""

from __future__ import annotations

from dataclasses import dataclass

from .domain import ExportState, RegistryEvent
from .repository import RegistryRepository


@dataclass(frozen=True, slots=True)
class RegistryMetricsSnapshot:
    """Summarize tenant-scoped registry operation metrics."""

    tenant_id: str
    song_count: int
    export_count: int
    reserved_count: int
    active_count: int
    failed_count: int
    revoked_count: int
    finalize_rate: float
    reconciliation_rate: float
    audit_event_count: int
    audit_identity_rate: float
    handle_collision_count: int = 0
    issuance_attempt_count: int = 0
    issuance_attempts_per_active_export: float = 0.0


def registry_metrics_snapshot(
    repository: RegistryRepository,
    tenant_id: str,
    song_ids: tuple[str, ...],
) -> RegistryMetricsSnapshot:
    """Return launch-gate metrics for an authorized tenant song list."""

    _require_text(tenant_id, "tenant_id")
    if repository.tenant(tenant_id) is None:
        raise ValueError("tenant_id is not registered")
    if not song_ids:
        raise ValueError("song_ids must not be empty")
    states: list[ExportState] = []
    for song_id in song_ids:
        _require_text(song_id, "song_id")
        if repository.song(tenant_id, song_id) is None:
            raise ValueError("song_id is not registered for tenant")
        states.extend(export.state for export in repository.exports_for_song(tenant_id, song_id))
    events = repository.events(tenant_id)
    active = states.count(ExportState.ACTIVE)
    revoked = states.count(ExportState.REVOKED)
    failed = states.count(ExportState.FAILED)
    reserved = states.count(ExportState.RESERVED)
    completed = active + revoked
    terminal = completed + failed
    reserved_events = _count_events(events, "export.reserved")
    expired_events = _count_events(events, "export.reservation_expired")
    collision_events = _count_events(events, "export.handle_collision")
    issuance_attempts = reserved_events + collision_events
    return RegistryMetricsSnapshot(
        tenant_id,
        len(song_ids),
        len(states),
        reserved,
        active,
        failed,
        revoked,
        _ratio(completed, terminal),
        _ratio(expired_events, reserved_events),
        len(events),
        _audit_identity_rate(events),
        collision_events,
        issuance_attempts,
        _ratio(issuance_attempts, active),
    )


def _count_events(events: tuple[RegistryEvent, ...], action: str) -> int:
    """Count audit events for one action name."""

    return sum(1 for event in events if event.action == action)


def _ratio(numerator: int, denominator: int) -> float:
    """Return a stable zero-safe ratio."""

    return 0.0 if denominator == 0 else numerator / denominator


def _audit_identity_rate(events: tuple[RegistryEvent, ...]) -> float:
    """Return the share of audit events with actor and request identity."""

    if not events:
        return 1.0
    complete = sum(1 for event in events if event.actor_id.strip() and event.request_id.strip())
    return complete / len(events)


def _require_text(value: str, name: str) -> None:
    """Require a non-empty text value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")
