"""Reconcile interrupted registry reservations without activating bad exports.

Desktop encode is a multi-step workflow: reserve a handle, encode locally, run
the clean verification gate, then finalize. If the desktop disappears between
reserve and finalize, the registry should preserve history but move stale
reservations out of the usable path. This module provides a small explicit job
for that cleanup; it does not infer that an audio artifact exists.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import datetime
import hashlib
import json
from uuid import uuid4

from .domain import ExportState, RegistryEvent
from .repository import RegistryRepository


@dataclass(frozen=True, slots=True)
class ReservationExpiryResult:
    """Summarize one stale-reservation reconciliation run."""

    expired_count: int
    export_ids: tuple[str, ...]


def expire_stale_reserved_exports(
    repository: RegistryRepository,
    *,
    tenant_id: str,
    song_id: str,
    older_than_utc: datetime,
    now_utc: datetime,
    actor_id: str,
    request_id: str,
    event_id_factory: Callable[[], str] | None = None,
) -> ReservationExpiryResult:
    """Mark stale reserved exports as failed and append audit events."""

    _require_text(tenant_id, "tenant_id")
    _require_text(song_id, "song_id")
    _require_text(actor_id, "actor_id")
    _require_text(request_id, "request_id")
    _require_aware(older_than_utc, "older_than_utc")
    _require_aware(now_utc, "now_utc")
    if now_utc < older_than_utc:
        raise ValueError("now_utc must not be before older_than_utc")
    identifiers = event_id_factory or (lambda: str(uuid4()))
    expired: list[str] = []
    for export in repository.exports_for_song(tenant_id, song_id):
        if export.state is not ExportState.RESERVED or export.created_utc > older_than_utc:
            continue
        failed = replace(export, state=ExportState.FAILED, updated_utc=now_utc)
        repository.update_export(failed)
        repository.append_event(
            _event(
                identifiers(),
                tenant_id,
                actor_id,
                export.export_id,
                request_id,
                now_utc,
            )
        )
        expired.append(export.export_id)
    return ReservationExpiryResult(len(expired), tuple(expired))


def _event(
    event_id: str,
    tenant_id: str,
    actor_id: str,
    export_id: str,
    request_id: str,
    now_utc: datetime,
) -> RegistryEvent:
    """Create one digest-only expiry audit event."""

    detail = {"reason": "reservation expired before finalize"}
    canonical = json.dumps(detail, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return RegistryEvent(
        event_id,
        tenant_id,
        actor_id,
        "export.reservation_expired",
        export_id,
        request_id,
        now_utc,
        hashlib.sha256(canonical).hexdigest(),
    )


def _require_text(value: str, name: str) -> None:
    """Require one visible text value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _require_aware(value: datetime, name: str) -> None:
    """Require one timezone-aware timestamp."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
