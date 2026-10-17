"""Translate SQLite rows into immutable Saurus registry records.

The SQLite repository owns SQL statements and transactions. This helper keeps
the mechanical row-to-domain mapping separate so the durable adapter stays
readable and under the repository's module-size ceiling.
"""

from __future__ import annotations

from datetime import datetime
import sqlite3

from .domain import ExportRecord, ExportState, RegistryEvent, SongRecord, StoredAttributionRecord, TenantRecord


def export_values(export: ExportRecord) -> tuple[object, ...]:
    """Return SQL parameters for one export record."""

    return (
        export.export_id,
        export.tenant_id,
        export.song_id,
        export.handle,
        export.recipient_label,
        export.parent_export_id,
        export.state.value,
        time_text(export.created_utc),
        time_text(export.updated_utc),
    )


def tenant(row: sqlite3.Row) -> TenantRecord:
    """Build one tenant domain record from a SQLite row."""

    return TenantRecord(row["tenant_id"], row["name"], time(row["created_utc"]))


def song(row: sqlite3.Row) -> SongRecord:
    """Build one song domain record from a SQLite row."""

    return SongRecord(
        row["song_id"],
        row["tenant_id"],
        row["title"],
        row["source_digest"],
        int(row["sample_rate"]),
        int(row["sample_count"]),
        row["fingerprint_version"],
        time(row["created_utc"]),
    )


def export(row: sqlite3.Row) -> ExportRecord:
    """Build one export domain record from a SQLite row."""

    return ExportRecord(
        row["export_id"],
        row["tenant_id"],
        row["song_id"],
        bytes(row["handle"]),
        row["recipient_label"],
        row["parent_export_id"],
        ExportState(row["state"]),
        time(row["created_utc"]),
        time(row["updated_utc"]),
    )


def record(row: sqlite3.Row) -> StoredAttributionRecord:
    """Build one stored attribution record from a SQLite row."""

    return StoredAttributionRecord(
        row["export_id"],
        int(row["schema_version"]),
        bytes(row["payload"]),
        row["payload_digest"],
        time(row["created_utc"]),
    )


def event(row: sqlite3.Row) -> RegistryEvent:
    """Build one audit event from a SQLite row."""

    return RegistryEvent(
        row["event_id"],
        row["tenant_id"],
        row["actor_id"],
        row["action"],
        row["object_id"],
        row["request_id"],
        time(row["occurred_utc"]),
        row["detail_digest"],
    )


def time_text(value: datetime) -> str:
    """Serialize one aware timestamp as sortable ISO text."""

    return value.isoformat()


def time(value: str) -> datetime:
    """Parse one ISO timestamp preserved by the repository."""

    return datetime.fromisoformat(value)


def require_same_identity(current: ExportRecord, replacement: ExportRecord) -> None:
    """Reject update attempts that change durable export identity fields."""

    if (current.song_id, current.handle, current.created_utc) != (
        replacement.song_id,
        replacement.handle,
        replacement.created_utc,
    ):
        raise ValueError("export identity fields cannot change")
