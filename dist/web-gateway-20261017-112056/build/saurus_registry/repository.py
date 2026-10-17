"""Declare persistence operations required by the registry application.

The repository owns atomic tenant-wide handle reservation and append-only audit
storage. Application policy remains independent from SQL, HTTP, or a particular
cloud. Implementations must apply tenant scope inside every lookup rather than
filtering records after retrieval.
"""

from __future__ import annotations

from typing import Protocol

from .domain import ExportRecord, IdempotencyRecord, RegistryEvent, SongRecord, StoredAttributionRecord, TenantRecord


class HandleConflictError(RuntimeError):
    """Report an atomic tenant-wide handle uniqueness conflict."""


class RegistryRepository(Protocol):
    """Describe the durable operations used by registry orchestration."""

    def add_tenant(self, tenant: TenantRecord) -> None:
        """Persist one new tenant."""

    def tenant(self, tenant_id: str) -> TenantRecord | None:
        """Return one tenant by exact identity."""

    def add_song(self, song: SongRecord) -> None:
        """Persist one tenant-owned song."""

    def song(self, tenant_id: str, song_id: str) -> SongRecord | None:
        """Return one song only within the supplied tenant."""

    def reserve_export(self, export: ExportRecord) -> None:
        """Atomically persist an export if its handle is unused by the tenant."""

    def update_export(self, export: ExportRecord) -> None:
        """Replace one existing tenant-owned export state."""

    def export(self, tenant_id: str, export_id: str) -> ExportRecord | None:
        """Return one export only within the supplied tenant."""

    def exports_for_song(self, tenant_id: str, song_id: str) -> tuple[ExportRecord, ...]:
        """Return stable tenant-owned exports for one song."""

    def finalize_export(
        self,
        tenant_id: str,
        export: ExportRecord,
        record: StoredAttributionRecord,
    ) -> None:
        """Atomically store a private record and activate its reserved export."""

    def attribution_record(self, tenant_id: str, export_id: str) -> StoredAttributionRecord | None:
        """Return one private record only within the supplied tenant."""

    def append_event(self, event: RegistryEvent) -> None:
        """Append one immutable audit event."""

    def events(self, tenant_id: str) -> tuple[RegistryEvent, ...]:
        """Return stable audit events for one tenant."""

    def idempotency_record(self, tenant_id: str, request_id: str) -> IdempotencyRecord | None:
        """Return one completed mutating response for replay."""

    def store_idempotency_record(self, record: IdempotencyRecord) -> None:
        """Persist one completed mutating response for replay."""
