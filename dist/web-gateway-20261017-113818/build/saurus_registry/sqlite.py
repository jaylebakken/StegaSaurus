"""Persist the Saurus registry contract in a small SQLite database.

The adapter gives Phase 1 durable local/test storage behind a narrow protocol:
one connection per operation, tenant-scoped SQL, and foreign-key checks.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path
import sqlite3

from . import sqlite_idempotency, sqlite_rows as rows
from . import sqlite_records
from .domain import ExportRecord, ExportState, IdempotencyRecord, RegistryEvent, SongRecord, StoredAttributionRecord, TenantRecord
from .envelope import RecordCipher
from .migrations import migrate, schema_version
from .repository import HandleConflictError


class SQLiteRegistryRepository:
    """Store registry records in a migrated SQLite database file."""

    def __init__(self, database_path: str | Path, cipher: RecordCipher | None = None) -> None:
        """Remember the database file path and create its schema if needed."""
        self._database_path = Path(database_path)
        self._cipher = cipher
        with self._connection() as connection:
            migrate(connection)

    def schema_version(self) -> int:
        """Return the durable schema version visible to this repository."""
        with self._connection() as connection:
            return schema_version(connection)

    def add_tenant(self, tenant: TenantRecord) -> None:
        """Persist one tenant with a unique identity."""
        with self._connection() as connection:
            try:
                connection.execute(
                    "INSERT INTO tenants(tenant_id, name, created_utc) VALUES (?, ?, ?)",
                    (tenant.tenant_id, tenant.name, rows.time_text(tenant.created_utc)),
                )
            except sqlite3.IntegrityError as error:
                raise ValueError("tenant_id is already registered") from error

    def tenant(self, tenant_id: str) -> TenantRecord | None:
        """Return one tenant by exact identity."""
        with self._connection() as connection:
            row = connection.execute("SELECT * FROM tenants WHERE tenant_id = ?", (tenant_id,)).fetchone()
        return rows.tenant(row) if row is not None else None

    def add_song(self, song: SongRecord) -> None:
        """Persist one song owned by an existing tenant."""
        with self._connection() as connection:
            try:
                connection.execute(
                    "INSERT INTO songs VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        song.song_id,
                        song.tenant_id,
                        song.title,
                        song.source_digest,
                        song.sample_rate,
                        song.sample_count,
                        song.fingerprint_version,
                        rows.time_text(song.created_utc),
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise ValueError("song_id or tenant_id is invalid") from error

    def song(self, tenant_id: str, song_id: str) -> SongRecord | None:
        """Return one song only within the supplied tenant."""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM songs WHERE tenant_id = ? AND song_id = ?",
                (tenant_id, song_id),
            ).fetchone()
        return rows.song(row) if row is not None else None

    def reserve_export(self, export: ExportRecord) -> None:
        """Atomically persist an export if its handle is unused by the tenant."""
        with self._connection() as connection:
            try:
                connection.execute(
                    "INSERT INTO exports VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    rows.export_values(export),
                )
            except sqlite3.IntegrityError as error:
                if self._handle_exists(connection, export.tenant_id, export.handle):
                    raise HandleConflictError("handle is already reserved for tenant") from error
                raise ValueError("export identity or relationship is invalid") from error

    def update_export(self, export: ExportRecord) -> None:
        """Replace one existing tenant-owned export state without identity drift."""
        with self._connection() as connection:
            current = self._export_for_update(connection, export.tenant_id, export.export_id)
            rows.require_same_identity(current, export)
            connection.execute(
                """
                UPDATE exports SET recipient_label = ?, parent_export_id = ?, state = ?, updated_utc = ?
                WHERE tenant_id = ? AND export_id = ?
                """,
                (
                    export.recipient_label,
                    export.parent_export_id,
                    export.state.value,
                    rows.time_text(export.updated_utc),
                    export.tenant_id,
                    export.export_id,
                ),
            )

    def export(self, tenant_id: str, export_id: str) -> ExportRecord | None:
        """Return one export only within the supplied tenant."""
        with self._connection() as connection:
            row = connection.execute(
                "SELECT * FROM exports WHERE tenant_id = ? AND export_id = ?",
                (tenant_id, export_id),
            ).fetchone()
        return rows.export(row) if row is not None else None

    def exports_for_song(self, tenant_id: str, song_id: str) -> tuple[ExportRecord, ...]:
        """Return stable tenant-owned exports for one song."""
        with self._connection() as connection:
            result = connection.execute(
                "SELECT * FROM exports WHERE tenant_id = ? AND song_id = ? ORDER BY created_utc, export_id",
                (tenant_id, song_id),
            ).fetchall()
        return tuple(rows.export(row) for row in result)

    def finalize_export(
        self,
        tenant_id: str,
        export: ExportRecord,
        record: StoredAttributionRecord,
    ) -> None:
        """Atomically store a private record and activate its reserved export."""
        with self._connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            current = self._export_for_update(connection, tenant_id, export.export_id)
            rows.require_same_identity(current, export)
            if current.state is not ExportState.RESERVED or export.state is not ExportState.ACTIVE:
                raise ValueError("finalization requires a reserved export and active replacement")
            if record.export_id != export.export_id:
                raise ValueError("attribution record must belong to finalized export")
            connection.execute(
                "INSERT INTO attribution_records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
                sqlite_records.insert_values(record, self._cipher),
            )
            connection.execute(
                "UPDATE exports SET state = ?, updated_utc = ? WHERE tenant_id = ? AND export_id = ?",
                (export.state.value, rows.time_text(export.updated_utc), tenant_id, export.export_id),
            )
            connection.commit()

    def attribution_record(self, tenant_id: str, export_id: str) -> StoredAttributionRecord | None:
        """Return one private record only within the supplied tenant."""
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT attribution_records.* FROM attribution_records
                INNER JOIN exports USING (export_id)
                WHERE exports.tenant_id = ? AND exports.export_id = ?
                """,
                (tenant_id, export_id),
            ).fetchone()
        return sqlite_records.stored_record(row, self._cipher) if row is not None else None

    def append_event(self, event: RegistryEvent) -> None:
        """Append one immutable audit event."""

        with self._connection() as connection:
            try:
                connection.execute(
                    "INSERT INTO registry_events VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        event.event_id,
                        event.tenant_id,
                        event.actor_id,
                        event.action,
                        event.object_id,
                        event.request_id,
                        rows.time_text(event.occurred_utc),
                        event.detail_digest,
                    ),
                )
            except sqlite3.IntegrityError as error:
                raise ValueError("registry event identity or tenant is invalid") from error

    def events(self, tenant_id: str) -> tuple[RegistryEvent, ...]:
        """Return stable audit events for one tenant."""

        with self._connection() as connection:
            result = connection.execute(
                "SELECT * FROM registry_events WHERE tenant_id = ? ORDER BY occurred_utc, event_id",
                (tenant_id,),
            ).fetchall()
        return tuple(rows.event(row) for row in result)

    def idempotency_record(self, tenant_id: str, request_id: str) -> IdempotencyRecord | None:
        """Return one completed mutating response for replay."""

        with self._connection() as connection:
            return sqlite_idempotency.fetch(connection, tenant_id, request_id)

    def store_idempotency_record(self, record: IdempotencyRecord) -> None:
        """Persist one completed mutating response for replay."""

        with self._connection() as connection:
            sqlite_idempotency.store(connection, record)

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        """Open, yield, and close one configured SQLite connection."""

        connection = sqlite3.connect(self._database_path, timeout=5.0, isolation_level=None)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA journal_mode = WAL")
        try:
            yield connection
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _handle_exists(self, connection: sqlite3.Connection, tenant_id: str, handle: bytes) -> bool:
        """Return whether one tenant has already consumed a handle."""

        row = connection.execute(
            "SELECT 1 FROM exports WHERE tenant_id = ? AND handle = ?",
            (tenant_id, handle),
        ).fetchone()
        return row is not None

    def _export_for_update(self, connection: sqlite3.Connection, tenant_id: str, export_id: str) -> ExportRecord:
        """Read one export in a write path and reject cross-tenant access."""

        row = connection.execute(
            "SELECT * FROM exports WHERE tenant_id = ? AND export_id = ?",
            (tenant_id, export_id),
        ).fetchone()
        if row is None:
            raise ValueError("export_id is not registered for tenant")
        return rows.export(row)
