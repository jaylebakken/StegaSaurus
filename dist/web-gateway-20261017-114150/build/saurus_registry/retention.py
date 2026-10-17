"""Evaluate registry retention policy without deleting records.

Registry retention is sensitive because exports, private retained records, and
audit events can be evidence. This module deliberately produces review
decisions only. It does not delete records, redact records, or decide legal
retention policy. Production procedures still need owner approval, legal hold
handling, secure export, and audited deletion tooling.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .domain import ExportState
from .repository import RegistryRepository


class RetentionAction(str, Enum):
    """Name non-destructive retention review outcomes."""

    KEEP = "keep"
    REVIEW = "review"
    HOLD = "hold"


@dataclass(frozen=True, slots=True)
class RegistryRetentionPolicy:
    """Declare local retention thresholds for registry export review."""

    active_retention_days: int
    inactive_retention_days: int
    legal_hold: bool = False

    def __post_init__(self) -> None:
        """Validate non-negative retention thresholds."""

        if isinstance(self.active_retention_days, bool) or self.active_retention_days < 0:
            raise ValueError("active_retention_days must be non-negative")
        if isinstance(self.inactive_retention_days, bool) or self.inactive_retention_days < 0:
            raise ValueError("inactive_retention_days must be non-negative")


@dataclass(frozen=True, slots=True)
class RegistryRetentionDecision:
    """Summarize one export retention review result."""

    export_id: str
    song_id: str
    state: ExportState
    action: RetentionAction
    age_days: int
    reason: str


def review_registry_retention(
    repository: RegistryRepository,
    tenant_id: str,
    song_ids: tuple[str, ...],
    now_utc: datetime,
    policy: RegistryRetentionPolicy,
) -> tuple[RegistryRetentionDecision, ...]:
    """Return retention decisions for an authorized tenant song list."""

    _require_text(tenant_id, "tenant_id")
    _require_aware(now_utc, "now_utc")
    if repository.tenant(tenant_id) is None:
        raise ValueError("tenant_id is not registered")
    if not song_ids:
        raise ValueError("song_ids must not be empty")
    decisions: list[RegistryRetentionDecision] = []
    for song_id in song_ids:
        _require_text(song_id, "song_id")
        if repository.song(tenant_id, song_id) is None:
            raise ValueError("song_id is not registered for tenant")
        for export in repository.exports_for_song(tenant_id, song_id):
            decisions.append(_decision(export.export_id, export.song_id, export.state, export.updated_utc, now_utc, policy))
    return tuple(sorted(decisions, key=lambda item: (item.song_id, item.export_id)))


def _decision(
    export_id: str,
    song_id: str,
    state: ExportState,
    updated_utc: datetime,
    now_utc: datetime,
    policy: RegistryRetentionPolicy,
) -> RegistryRetentionDecision:
    """Build one non-destructive retention decision."""

    if updated_utc > now_utc:
        raise ValueError("export updated_utc must not be after now_utc")
    age_days = int((now_utc - updated_utc).total_seconds() // 86400)
    if policy.legal_hold:
        return RegistryRetentionDecision(export_id, song_id, state, RetentionAction.HOLD, age_days, "legal hold is active")
    threshold = policy.active_retention_days if state in {ExportState.ACTIVE, ExportState.REVOKED} else policy.inactive_retention_days
    if age_days >= threshold:
        return RegistryRetentionDecision(export_id, song_id, state, RetentionAction.REVIEW, age_days, "retention threshold reached")
    return RegistryRetentionDecision(export_id, song_id, state, RetentionAction.KEEP, age_days, "retention threshold not reached")


def _require_text(value: str, name: str) -> None:
    """Require a non-empty text value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _require_aware(value: datetime, name: str) -> None:
    """Require a timezone-aware timestamp."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
