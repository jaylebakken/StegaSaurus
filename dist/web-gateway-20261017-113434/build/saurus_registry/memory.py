"""Provide a lock-protected reference registry repository.

This implementation supports application tests and local contract development.
Its lock makes handle collision checks and export reservation one operation, but
it is not durable infrastructure. SQL implementations must provide equivalent
transactional behavior and tenant scoping.
"""

from __future__ import annotations

from threading import RLock

from .domain import ExportRecord, ExportState, IdempotencyRecord, RegistryEvent, SongRecord, StoredAttributionRecord, TenantRecord
from .repository import HandleConflictError


class InMemoryRegistryRepository:
    """Retain tenant-scoped registry records behind one reentrant lock."""

    def __init__(self) -> None:
        """Initialize empty record collections."""

        self._lock = RLock()
        self._tenants: dict[str, TenantRecord] = {}
        self._songs: dict[str, SongRecord] = {}
        self._exports: dict[str, ExportRecord] = {}
        self._handles: dict[tuple[str, bytes], str] = {}
        self._records: dict[str, StoredAttributionRecord] = {}
        self._events: list[RegistryEvent] = []
        self._idempotency: dict[tuple[str, str], IdempotencyRecord] = {}

    def add_tenant(self, tenant: TenantRecord) -> None:
        """Persist one tenant with a unique identity."""

        with self._lock:
            if tenant.tenant_id in self._tenants:
                raise ValueError("tenant_id is already registered")
            self._tenants[tenant.tenant_id] = tenant

    def tenant(self, tenant_id: str) -> TenantRecord | None:
        """Return one tenant by exact identity."""

        with self._lock:
            return self._tenants.get(tenant_id)

    def add_song(self, song: SongRecord) -> None:
        """Persist a song owned by an existing tenant."""

        with self._lock:
            if song.tenant_id not in self._tenants:
                raise ValueError("tenant_id is not registered")
            if song.song_id in self._songs:
                raise ValueError("song_id is already registered")
            self._songs[song.song_id] = song

    def song(self, tenant_id: str, song_id: str) -> SongRecord | None:
        """Return a song only when both tenant and identity match."""

        with self._lock:
            song = self._songs.get(song_id)
            return song if song is not None and song.tenant_id == tenant_id else None

    def reserve_export(self, export: ExportRecord) -> None:
        """Atomically reject duplicate identities and tenant handle collisions."""

        with self._lock:
            if self.song(export.tenant_id, export.song_id) is None:
                raise ValueError("song_id is not registered for tenant")
            if export.export_id in self._exports:
                raise ValueError("export_id is already registered")
            handle_key = (export.tenant_id, export.handle)
            if handle_key in self._handles:
                raise HandleConflictError("handle is already reserved for tenant")
            self._exports[export.export_id] = export
            self._handles[handle_key] = export.export_id

    def update_export(self, export: ExportRecord) -> None:
        """Replace a matching tenant-owned export without changing its handle."""

        with self._lock:
            current = self.export(export.tenant_id, export.export_id)
            if current is None:
                raise ValueError("export_id is not registered for tenant")
            if (current.song_id, current.handle, current.created_utc) != (
                export.song_id,
                export.handle,
                export.created_utc,
            ):
                raise ValueError("export identity fields cannot change")
            self._exports[export.export_id] = export

    def export(self, tenant_id: str, export_id: str) -> ExportRecord | None:
        """Return an export only when both tenant and identity match."""

        with self._lock:
            export = self._exports.get(export_id)
            return export if export is not None and export.tenant_id == tenant_id else None

    def exports_for_song(self, tenant_id: str, song_id: str) -> tuple[ExportRecord, ...]:
        """Return stable exports for one tenant-owned song."""

        with self._lock:
            return tuple(
                sorted(
                    (
                        export
                        for export in self._exports.values()
                        if export.tenant_id == tenant_id and export.song_id == song_id
                    ),
                    key=lambda item: (item.created_utc, item.export_id),
                )
            )

    def finalize_export(
        self,
        tenant_id: str,
        export: ExportRecord,
        record: StoredAttributionRecord,
    ) -> None:
        """Atomically store a private record and activate its reserved export."""

        with self._lock:
            current = self.export(tenant_id, export.export_id)
            if current is None:
                raise ValueError("export_id is not registered for tenant")
            if current.state is not ExportState.RESERVED or export.state is not ExportState.ACTIVE:
                raise ValueError("finalization requires a reserved export and active replacement")
            if (current.song_id, current.handle, current.created_utc) != (
                export.song_id,
                export.handle,
                export.created_utc,
            ):
                raise ValueError("export identity fields cannot change")
            if record.export_id != export.export_id:
                raise ValueError("attribution record must belong to finalized export")
            if record.export_id in self._records:
                raise ValueError("attribution record is already stored")
            self._records[record.export_id] = record
            self._exports[export.export_id] = export

    def attribution_record(self, tenant_id: str, export_id: str) -> StoredAttributionRecord | None:
        """Return a private record only for a matching tenant-owned export."""

        with self._lock:
            if self.export(tenant_id, export_id) is None:
                return None
            return self._records.get(export_id)

    def append_event(self, event: RegistryEvent) -> None:
        """Append one audit event without mutation support."""

        with self._lock:
            self._events.append(event)

    def events(self, tenant_id: str) -> tuple[RegistryEvent, ...]:
        """Return audit events for exactly one tenant."""

        with self._lock:
            return tuple(event for event in self._events if event.tenant_id == tenant_id)

    def idempotency_record(self, tenant_id: str, request_id: str) -> IdempotencyRecord | None:
        """Return one completed mutating response for replay."""

        with self._lock:
            return self._idempotency.get((tenant_id, request_id))

    def store_idempotency_record(self, record: IdempotencyRecord) -> None:
        """Persist one completed mutating response for replay."""

        with self._lock:
            key = (record.tenant_id, record.request_id)
            if key in self._idempotency:
                raise ValueError("idempotency response is already stored")
            self._idempotency[key] = record
