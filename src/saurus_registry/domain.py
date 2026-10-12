"""Define immutable records for the tenant-scoped Saurus registry.

The audio watermark carries only a compact opaque handle. These records retain
the durable song, export, private verification payload, and audit context around
that handle. Recipient labels remain user context, while state and timestamps
are system facts. Lineage is registry metadata rather than stacked audio proof.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class ExportState(str, Enum):
    """Name the explicit lifecycle states of one recipient export."""

    RESERVED = "reserved"
    ACTIVE = "active"
    FAILED = "failed"
    REVOKED = "revoked"


@dataclass(frozen=True, slots=True)
class TenantRecord:
    """Represent one isolated registry customer boundary."""

    tenant_id: str
    name: str
    created_utc: datetime

    def __post_init__(self) -> None:
        """Reject empty identity fields and naive timestamps."""

        _require_text(self.tenant_id, "tenant_id")
        _require_text(self.name, "name")
        _require_aware(self.created_utc, "created_utc")


@dataclass(frozen=True, slots=True)
class SongRecord:
    """Retain source identity and geometry without storing source PCM."""

    song_id: str
    tenant_id: str
    title: str
    source_digest: str
    sample_rate: int
    sample_count: int
    fingerprint_version: str
    created_utc: datetime

    def __post_init__(self) -> None:
        """Validate fields needed for deterministic export processing."""

        for value, name in (
            (self.song_id, "song_id"),
            (self.tenant_id, "tenant_id"),
            (self.title, "title"),
            (self.source_digest, "source_digest"),
            (self.fingerprint_version, "fingerprint_version"),
        ):
            _require_text(value, name)
        if self.sample_rate < 1 or self.sample_count < 1:
            raise ValueError("sample_rate and sample_count must be positive")
        _require_aware(self.created_utc, "created_utc")


@dataclass(frozen=True, slots=True)
class ExportRecord:
    """Bind one tenant-unique audio handle to registry context and state."""

    export_id: str
    tenant_id: str
    song_id: str
    handle: bytes
    recipient_label: str
    parent_export_id: str | None
    state: ExportState
    created_utc: datetime
    updated_utc: datetime

    def __post_init__(self) -> None:
        """Validate opaque identity, context, and lifecycle timestamps."""

        for value, name in (
            (self.export_id, "export_id"),
            (self.tenant_id, "tenant_id"),
            (self.song_id, "song_id"),
            (self.recipient_label, "recipient_label"),
        ):
            _require_text(value, name)
        if len(self.handle) != 4:
            raise ValueError("registry handles must contain exactly four bytes")
        if self.parent_export_id is not None:
            _require_text(self.parent_export_id, "parent_export_id")
        _require_aware(self.created_utc, "created_utc")
        _require_aware(self.updated_utc, "updated_utc")


@dataclass(frozen=True, slots=True)
class StoredAttributionRecord:
    """Store one canonical private verification payload and its digest."""

    export_id: str
    schema_version: int
    payload: bytes
    payload_digest: str
    created_utc: datetime
    key_id: str = "local-development"
    encryption_algorithm: str = "plaintext-local"

    def __post_init__(self) -> None:
        """Require a nonempty versioned payload and digest."""

        _require_text(self.export_id, "export_id")
        _require_text(self.payload_digest, "payload_digest")
        _require_text(self.key_id, "key_id")
        _require_text(self.encryption_algorithm, "encryption_algorithm")
        if self.schema_version < 1:
            raise ValueError("schema_version must be positive")
        if not self.payload:
            raise ValueError("payload must not be empty")
        _require_aware(self.created_utc, "created_utc")


@dataclass(frozen=True, slots=True)
class RegistryEvent:
    """Record one append-only registry action for operational audit."""

    event_id: str
    tenant_id: str
    actor_id: str
    action: str
    object_id: str
    request_id: str
    occurred_utc: datetime
    detail_digest: str

    def __post_init__(self) -> None:
        """Reject anonymous or untraceable audit events."""

        for value, name in (
            (self.event_id, "event_id"),
            (self.tenant_id, "tenant_id"),
            (self.actor_id, "actor_id"),
            (self.action, "action"),
            (self.object_id, "object_id"),
            (self.request_id, "request_id"),
            (self.detail_digest, "detail_digest"),
        ):
            _require_text(value, name)
        _require_aware(self.occurred_utc, "occurred_utc")


@dataclass(frozen=True, slots=True)
class IdempotencyRecord:
    """Store one completed mutating API response for safe request replay."""

    tenant_id: str
    request_id: str
    method: str
    path: str
    request_digest: str
    response_status: int
    response_body: bytes
    created_utc: datetime

    def __post_init__(self) -> None:
        """Validate replay identity and retained response bytes."""

        for value, name in (
            (self.tenant_id, "tenant_id"),
            (self.request_id, "request_id"),
            (self.method, "method"),
            (self.path, "path"),
            (self.request_digest, "request_digest"),
        ):
            _require_text(value, name)
        if self.response_status < 100 or not self.response_body:
            raise ValueError("idempotent response status and body must be present")
        _require_aware(self.created_utc, "created_utc")


def _require_text(value: str, name: str) -> None:
    """Require one visible string value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _require_aware(value: datetime, name: str) -> None:
    """Require one timezone-aware timestamp."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
