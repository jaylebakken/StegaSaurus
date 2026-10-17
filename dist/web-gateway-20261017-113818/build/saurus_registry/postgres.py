"""Persist the hosted Saurus registry contract in PostgreSQL.

The desktop and local rehearsals keep using SQLite, but the AWS alpha registry
needs the same repository protocol backed by managed PostgreSQL. This adapter
keeps PostgreSQL-specific connection setup, migrations, row locks, and `%s`
parameter SQL out of the application service. It expects a psycopg v3 client at
runtime and remains optional for local installs that do not deploy the alpha.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any

from . import sqlite_records
from .domain import ExportRecord, ExportState, IdempotencyRecord, RegistryEvent, SongRecord, StoredAttributionRecord, TenantRecord
from .envelope import RecordCipher
from .postgres_runtime import apply_postgres_migrations, idempotency_from_row, idempotency_values
from .repository import HandleConflictError
from .sqlite_rows import event as event_row
from .sqlite_rows import export as export_row
from .sqlite_rows import export_values, require_same_identity, song as song_row
from .sqlite_rows import tenant as tenant_row
from .sqlite_rows import time_text


@dataclass(frozen=True, slots=True)
class PostgresConnectionSettings:
    """Declare the secret-bearing PostgreSQL connection inputs."""

    host: str
    port: int
    database: str
    username: str
    password: str
    sslmode: str = "require"
    connect_timeout_seconds: int = 5

    def __post_init__(self) -> None:
        """Validate connection settings before a network connection is opened."""

        for value, name in ((self.host, "host"), (self.database, "database"), (self.username, "username"), (self.password, "password")):
            if not value.strip():
                raise ValueError(f"{name} must not be empty")
        if self.port < 1 or self.port > 65535:
            raise ValueError("port must be a TCP port")
        if self.connect_timeout_seconds < 1:
            raise ValueError("connect_timeout_seconds must be positive")


class PostgresRegistryRepository:
    """Store registry records in a managed PostgreSQL database."""

    def __init__(self, connect: Callable[[], Any], cipher: RecordCipher | None = None, *, migrate_schema: bool = True) -> None:
        """Bind a connection factory and optionally apply reviewed migrations."""

        self._connect = connect
        self._cipher = cipher
        if migrate_schema:
            with self._connection() as connection:
                apply_postgres_migrations(connection)

    @classmethod
    def from_settings(cls, settings: PostgresConnectionSettings, cipher: RecordCipher | None = None) -> PostgresRegistryRepository:
        """Create a psycopg-backed repository from validated settings."""

        try:
            import psycopg
            from psycopg.rows import dict_row
        except ImportError as error:
            raise RuntimeError("PostgreSQL registry mode requires the psycopg package") from error

        def connect() -> Any:
            """Open one configured psycopg connection."""

            return psycopg.connect(
                host=settings.host,
                port=settings.port,
                dbname=settings.database,
                user=settings.username,
                password=settings.password,
                sslmode=settings.sslmode,
                connect_timeout=settings.connect_timeout_seconds,
                autocommit=True,
                row_factory=dict_row,
            )

        return cls(connect, cipher)

    def add_tenant(self, tenant: TenantRecord) -> None:
        """Persist one tenant with a unique identity."""

        with self._connection() as connection:
            try:
                connection.execute("INSERT INTO tenants(tenant_id, name, created_utc) VALUES (%s, %s, %s)", (tenant.tenant_id, tenant.name, time_text(tenant.created_utc)))
            except Exception as error:
                if not _is_integrity_error(error):
                    raise
                raise ValueError("tenant_id is already registered") from error

    def tenant(self, tenant_id: str) -> TenantRecord | None:
        """Return one tenant by exact identity."""

        with self._connection() as connection:
            row = connection.execute("SELECT * FROM tenants WHERE tenant_id = %s", (tenant_id,)).fetchone()
        return tenant_row(row) if row is not None else None

    def add_song(self, song: SongRecord) -> None:
        """Persist one song owned by an existing tenant."""

        with self._connection() as connection:
            try:
                connection.execute("INSERT INTO songs VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", (song.song_id, song.tenant_id, song.title, song.source_digest, song.sample_rate, song.sample_count, song.fingerprint_version, time_text(song.created_utc)))
            except Exception as error:
                if not _is_integrity_error(error):
                    raise
                raise ValueError("song_id or tenant_id is invalid") from error

    def song(self, tenant_id: str, song_id: str) -> SongRecord | None:
        """Return one song only within the supplied tenant."""

        with self._connection() as connection:
            row = connection.execute("SELECT * FROM songs WHERE tenant_id = %s AND song_id = %s", (tenant_id, song_id)).fetchone()
        return song_row(row) if row is not None else None

    def reserve_export(self, export: ExportRecord) -> None:
        """Atomically persist an export if its handle is unused by the tenant."""

        with self._connection() as connection:
            try:
                connection.execute("INSERT INTO exports VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)", export_values(export))
            except Exception as error:
                if not _is_integrity_error(error):
                    raise
                if self._handle_exists(connection, export.tenant_id, export.handle):
                    raise HandleConflictError("handle is already reserved for tenant") from error
                raise ValueError("export identity or relationship is invalid") from error

    def update_export(self, export: ExportRecord) -> None:
        """Replace one existing tenant-owned export state without identity drift."""

        with self._connection() as connection:
            with connection.transaction():
                current = self._export_for_update(connection, export.tenant_id, export.export_id)
                require_same_identity(current, export)
                connection.execute("UPDATE exports SET recipient_label = %s, parent_export_id = %s, state = %s, updated_utc = %s WHERE tenant_id = %s AND export_id = %s", (export.recipient_label, export.parent_export_id, export.state.value, time_text(export.updated_utc), export.tenant_id, export.export_id))

    def export(self, tenant_id: str, export_id: str) -> ExportRecord | None:
        """Return one export only within the supplied tenant."""

        with self._connection() as connection:
            row = connection.execute("SELECT * FROM exports WHERE tenant_id = %s AND export_id = %s", (tenant_id, export_id)).fetchone()
        return export_row(row) if row is not None else None

    def exports_for_song(self, tenant_id: str, song_id: str) -> tuple[ExportRecord, ...]:
        """Return stable tenant-owned exports for one song."""

        with self._connection() as connection:
            result = connection.execute("SELECT * FROM exports WHERE tenant_id = %s AND song_id = %s ORDER BY created_utc, export_id", (tenant_id, song_id)).fetchall()
        return tuple(export_row(row) for row in result)

    def finalize_export(self, tenant_id: str, export: ExportRecord, record: StoredAttributionRecord) -> None:
        """Atomically store a private record and activate its reserved export."""

        with self._connection() as connection:
            with connection.transaction():
                current = self._export_for_update(connection, tenant_id, export.export_id)
                require_same_identity(current, export)
                if current.state is not ExportState.RESERVED or export.state is not ExportState.ACTIVE:
                    raise ValueError("finalization requires a reserved export and active replacement")
                if record.export_id != export.export_id:
                    raise ValueError("attribution record must belong to finalized export")
                connection.execute("INSERT INTO attribution_records VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)", sqlite_records.insert_values(record, self._cipher))
                connection.execute("UPDATE exports SET state = %s, updated_utc = %s WHERE tenant_id = %s AND export_id = %s", (export.state.value, time_text(export.updated_utc), tenant_id, export.export_id))

    def attribution_record(self, tenant_id: str, export_id: str) -> StoredAttributionRecord | None:
        """Return one private record only within the supplied tenant."""

        with self._connection() as connection:
            row = connection.execute("SELECT attribution_records.* FROM attribution_records INNER JOIN exports USING (export_id) WHERE exports.tenant_id = %s AND exports.export_id = %s", (tenant_id, export_id)).fetchone()
        return sqlite_records.stored_record(row, self._cipher) if row is not None else None

    def append_event(self, event: RegistryEvent) -> None:
        """Append one immutable audit event."""

        with self._connection() as connection:
            try:
                connection.execute("INSERT INTO registry_events VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", (event.event_id, event.tenant_id, event.actor_id, event.action, event.object_id, event.request_id, time_text(event.occurred_utc), event.detail_digest))
            except Exception as error:
                if not _is_integrity_error(error):
                    raise
                raise ValueError("registry event identity or tenant is invalid") from error

    def events(self, tenant_id: str) -> tuple[RegistryEvent, ...]:
        """Return stable audit events for one tenant."""

        with self._connection() as connection:
            result = connection.execute("SELECT * FROM registry_events WHERE tenant_id = %s ORDER BY occurred_utc, event_id", (tenant_id,)).fetchall()
        return tuple(event_row(row) for row in result)

    def idempotency_record(self, tenant_id: str, request_id: str) -> IdempotencyRecord | None:
        """Return one completed mutating response for replay."""

        with self._connection() as connection:
            row = connection.execute("SELECT * FROM idempotency_records WHERE tenant_id = %s AND request_id = %s", (tenant_id, request_id)).fetchone()
        return idempotency_from_row(row) if row is not None else None

    def store_idempotency_record(self, record: IdempotencyRecord) -> None:
        """Persist one completed mutating response for replay."""

        with self._connection() as connection:
            try:
                connection.execute("INSERT INTO idempotency_records VALUES (%s, %s, %s, %s, %s, %s, %s, %s)", idempotency_values(record))
            except Exception as error:
                if not _is_integrity_error(error):
                    raise
                raise ValueError("idempotency response is already stored") from error

    @contextmanager
    def _connection(self) -> Iterator[Any]:
        """Open, yield, and close one PostgreSQL connection."""

        connection = self._connect()
        try:
            yield connection
        finally:
            connection.close()

    def _handle_exists(self, connection: Any, tenant_id: str, handle: bytes) -> bool:
        """Return whether one tenant has already consumed a handle."""

        row = connection.execute("SELECT 1 FROM exports WHERE tenant_id = %s AND handle = %s", (tenant_id, handle)).fetchone()
        return row is not None

    def _export_for_update(self, connection: Any, tenant_id: str, export_id: str) -> ExportRecord:
        """Read one export under a row lock and reject cross-tenant access."""

        row = connection.execute("SELECT * FROM exports WHERE tenant_id = %s AND export_id = %s FOR UPDATE", (tenant_id, export_id)).fetchone()
        if row is None:
            raise ValueError("export_id is not registered for tenant")
        return export_row(row)


def _is_integrity_error(error: Exception) -> bool:
    """Return whether an optional psycopg error is a constraint failure."""

    return any(cls.__name__ in {"IntegrityError", "UniqueViolation", "ForeignKeyViolation"} for cls in type(error).__mro__)
