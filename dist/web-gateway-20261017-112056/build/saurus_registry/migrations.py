"""Create and advance the first durable Saurus registry schema.

The registry needs migrations before it has an HTTP API so local development and
deployment storage share one explicit contract. This module creates the compact
tenant, song, export, private-record, and audit-event tables used by the SQLite
repository. It does not choose a production database engine or key-management
model; it only freezes the first persistent shape.
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timezone


CURRENT_SCHEMA_VERSION = 3


MIGRATIONS: tuple[tuple[int, str], ...] = (
    (
        1,
        """
        CREATE TABLE tenants (
            tenant_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            created_utc TEXT NOT NULL
        );

        CREATE TABLE songs (
            song_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
            title TEXT NOT NULL,
            source_digest TEXT NOT NULL,
            sample_rate INTEGER NOT NULL,
            sample_count INTEGER NOT NULL,
            fingerprint_version TEXT NOT NULL,
            created_utc TEXT NOT NULL
        );

        CREATE TABLE exports (
            export_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
            song_id TEXT NOT NULL REFERENCES songs(song_id),
            handle BLOB NOT NULL,
            recipient_label TEXT NOT NULL,
            parent_export_id TEXT REFERENCES exports(export_id),
            state TEXT NOT NULL,
            created_utc TEXT NOT NULL,
            updated_utc TEXT NOT NULL,
            UNIQUE (tenant_id, handle)
        );

        CREATE TABLE attribution_records (
            export_id TEXT PRIMARY KEY REFERENCES exports(export_id),
            schema_version INTEGER NOT NULL,
            payload BLOB NOT NULL,
            payload_digest TEXT NOT NULL,
            created_utc TEXT NOT NULL
        );

        CREATE TABLE registry_events (
            event_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
            actor_id TEXT NOT NULL,
            action TEXT NOT NULL,
            object_id TEXT NOT NULL,
            request_id TEXT NOT NULL,
            occurred_utc TEXT NOT NULL,
            detail_digest TEXT NOT NULL
        );

        CREATE TABLE schema_migrations (
            version INTEGER PRIMARY KEY,
            applied_utc TEXT NOT NULL
        );

        CREATE INDEX idx_songs_tenant ON songs(tenant_id);
        CREATE INDEX idx_exports_song ON exports(tenant_id, song_id);
        CREATE INDEX idx_events_tenant_time ON registry_events(tenant_id, occurred_utc);
        """,
    ),
    (
        2,
        """
        ALTER TABLE attribution_records ADD COLUMN key_id TEXT NOT NULL DEFAULT 'local-development';
        ALTER TABLE attribution_records ADD COLUMN encryption_algorithm TEXT NOT NULL DEFAULT 'plaintext-local';
        ALTER TABLE attribution_records ADD COLUMN nonce BLOB NOT NULL DEFAULT x'';
        ALTER TABLE attribution_records ADD COLUMN auth_tag BLOB NOT NULL DEFAULT x'';
        """,
    ),
    (
        3,
        """
        CREATE TABLE idempotency_records (
            tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
            request_id TEXT NOT NULL,
            method TEXT NOT NULL,
            path TEXT NOT NULL,
            request_digest TEXT NOT NULL,
            response_status INTEGER NOT NULL,
            response_body BLOB NOT NULL,
            created_utc TEXT NOT NULL,
            PRIMARY KEY (tenant_id, request_id)
        );
        """,
    ),
)


def migrate(connection: sqlite3.Connection) -> int:
    """Apply every pending migration and return the current schema version."""

    connection.execute("PRAGMA foreign_keys = ON")
    existing = _applied_versions(connection)
    for version, sql in MIGRATIONS:
        if version in existing:
            continue
        connection.executescript(sql)
        connection.execute(
            "INSERT INTO schema_migrations(version, applied_utc) VALUES (?, ?)",
            (version, datetime.now(timezone.utc).isoformat()),
        )
        existing.add(version)
    connection.commit()
    return schema_version(connection)


def schema_version(connection: sqlite3.Connection) -> int:
    """Return the highest applied schema migration version."""

    try:
        row = connection.execute("SELECT COALESCE(MAX(version), 0) FROM schema_migrations").fetchone()
    except sqlite3.OperationalError:
        return 0
    return int(row[0])


def _applied_versions(connection: sqlite3.Connection) -> set[int]:
    """Read already applied migration versions from an initialized database."""

    try:
        rows = connection.execute("SELECT version FROM schema_migrations").fetchall()
    except sqlite3.OperationalError:
        return set()
    return {int(row[0]) for row in rows}
