"""Store completed mutating registry API responses in SQLite.

Idempotency records let a desktop safely retry a reserve, finalize, fail, or
revoke request after a network interruption. The stored response is scoped to a
tenant and request ID, and callers must compare the original request digest
before replaying it.
"""

from __future__ import annotations

import sqlite3

from .domain import IdempotencyRecord
from .sqlite_rows import time, time_text


def fetch(connection: sqlite3.Connection, tenant_id: str, request_id: str) -> IdempotencyRecord | None:
    """Return one stored idempotency response if present."""

    row = connection.execute(
        "SELECT * FROM idempotency_records WHERE tenant_id = ? AND request_id = ?",
        (tenant_id, request_id),
    ).fetchone()
    return _record(row) if row is not None else None


def store(connection: sqlite3.Connection, record: IdempotencyRecord) -> None:
    """Persist one idempotency response or reject a duplicate key."""

    try:
        connection.execute(
            "INSERT INTO idempotency_records VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                record.tenant_id,
                record.request_id,
                record.method,
                record.path,
                record.request_digest,
                record.response_status,
                record.response_body,
                time_text(record.created_utc),
            ),
        )
    except sqlite3.IntegrityError as error:
        raise ValueError("idempotency response is already stored") from error


def _record(row: sqlite3.Row) -> IdempotencyRecord:
    """Build one domain idempotency record from a SQLite row."""

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
