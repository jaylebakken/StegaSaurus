"""Render the first PostgreSQL migration plan for hosted registry alpha.

The local registry adapter uses SQLite for desktop and rehearsal workflows, but
the AWS alpha persistence decision is managed PostgreSQL. This module keeps the
PostgreSQL schema plan explicit and version-aligned with the current durable
registry contract so operators can review the SQL before it is applied by a
deployment tool.

It does not open network connections, apply migrations, or replace the SQLite
repository used by local tests.
"""

from __future__ import annotations

from .migrations import CURRENT_SCHEMA_VERSION


POSTGRES_SCHEMA_VERSION = CURRENT_SCHEMA_VERSION

POSTGRES_MIGRATIONS: tuple[tuple[int, str], ...] = (
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
            sample_count BIGINT NOT NULL,
            fingerprint_version TEXT NOT NULL,
            created_utc TEXT NOT NULL
        );

        CREATE TABLE exports (
            export_id TEXT PRIMARY KEY,
            tenant_id TEXT NOT NULL REFERENCES tenants(tenant_id),
            song_id TEXT NOT NULL REFERENCES songs(song_id),
            handle BYTEA NOT NULL,
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
            payload BYTEA NOT NULL,
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
        ALTER TABLE attribution_records ADD COLUMN nonce BYTEA NOT NULL DEFAULT decode('', 'hex');
        ALTER TABLE attribution_records ADD COLUMN auth_tag BYTEA NOT NULL DEFAULT decode('', 'hex');
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
            response_body BYTEA NOT NULL,
            created_utc TEXT NOT NULL,
            PRIMARY KEY (tenant_id, request_id)
        );
        """,
    ),
)


def postgres_migration_statements() -> tuple[tuple[int, str], ...]:
    """Return immutable PostgreSQL migration SQL by schema version."""

    return POSTGRES_MIGRATIONS


def render_postgres_migration_plan() -> str:
    """Render the hosted alpha PostgreSQL migration plan for review."""

    chunks = [f"-- Saurus registry PostgreSQL schema v{POSTGRES_SCHEMA_VERSION}"]
    for version, sql in POSTGRES_MIGRATIONS:
        chunks.append(f"-- migration {version}")
        chunks.append(sql.strip())
        chunks.append(
            "INSERT INTO schema_migrations(version, applied_utc) "
            f"VALUES ({version}, CURRENT_TIMESTAMP);"
        )
    return "\n\n".join(chunks) + "\n"
