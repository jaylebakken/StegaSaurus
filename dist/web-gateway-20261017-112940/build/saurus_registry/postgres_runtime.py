"""Keep PostgreSQL adapter mechanics out of the repository facade.

The repository module should read as the durable registry contract. This helper
holds reviewed migration application and idempotency row decoding so the hosted
adapter stays focused while still sharing the same domain records.
"""

from __future__ import annotations

from typing import Any

from .domain import IdempotencyRecord
from .postgres_migrations import postgres_migration_statements
from .sqlite_rows import time, time_text


def apply_postgres_migrations(connection: Any) -> None:
    """Apply reviewed PostgreSQL migrations that are not already present."""

    applied = _applied_versions(connection)
    for version, sql in postgres_migration_statements():
        if version in applied:
            continue
        for statement in _split_statements(sql):
            connection.execute(statement)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_utc) VALUES (%s, CURRENT_TIMESTAMP)",
            (version,),
        )


def idempotency_from_row(row: Any) -> IdempotencyRecord:
    """Build one idempotency record from a PostgreSQL row."""

    return IdempotencyRecord(
        row["tenant_id"],
        row["request_id"],
        row["method"],
        row["path"],
        row["request_digest"],
        int(row["response_status"]),
        bytes(row["response_body"]),
        time(row["created_utc"]),
    )


def idempotency_values(record: IdempotencyRecord) -> tuple[object, ...]:
    """Return SQL parameters for one idempotent response record."""

    return (
        record.tenant_id,
        record.request_id,
        record.method,
        record.path,
        record.request_digest,
        record.response_status,
        record.response_body,
        time_text(record.created_utc),
    )


def _applied_versions(connection: Any) -> set[int]:
    """Return schema migrations already visible in PostgreSQL."""

    try:
        rows = connection.execute("SELECT version FROM schema_migrations").fetchall()
    except Exception:
        connection.rollback()
        return set()
    return {int(row["version"]) for row in rows}


def _split_statements(sql: str) -> tuple[str, ...]:
    """Split reviewed migration text into executable statements."""

    return tuple(f"{part.strip()};" for part in sql.split(";") if part.strip())
