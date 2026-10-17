"""Build the desktop's local registry-backed alpha connection.

The desktop should prove the server-style workflow before AWS exists: reserve a
handle through the registry API, encode locally, finalize the retained record,
and later verify from a private recovery receipt. This module creates that
connection with the existing SQLite repository and in-process API router. It is
not a production hosted service, KMS provider, or discovery endpoint.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3

from saurus_registry import RegistryApi, RegistryService, SQLiteRegistryRepository, TenantRecord

from .remote_registry import ApiRegistryBackend

__all__ = ["LocalRegistryConfig", "LocalRegistryHealth", "default_local_registry_path", "local_registry_backend", "local_registry_health"]


DEFAULT_TENANT_ID = "desktop-alpha-tenant"
DEFAULT_TENANT_NAME = "Saurus Desktop Alpha"
DEFAULT_ACTOR_ID = "desktop-user"


@dataclass(frozen=True, slots=True)
class LocalRegistryConfig:
    """Declare one desktop-local registry database and identity."""

    database_path: Path
    tenant_id: str = DEFAULT_TENANT_ID
    tenant_name: str = DEFAULT_TENANT_NAME
    actor_id: str = DEFAULT_ACTOR_ID
    registry_url: str = "local-sqlite-registry"


@dataclass(frozen=True, slots=True)
class LocalRegistryHealth:
    """Summarize operator-visible health for the desktop-local registry."""

    database_path: Path
    exists: bool
    schema_version: int | None
    database_bytes: int
    tenant_registered: bool
    song_count: int
    export_count: int
    reserved_count: int
    active_count: int
    failed_count: int
    revoked_count: int
    audit_event_count: int


def default_local_registry_path() -> Path:
    """Return the friendly default SQLite registry path for desktop alpha use."""

    return Path.home() / ".saurus" / "registry-alpha.sqlite"


def local_registry_backend(config: LocalRegistryConfig) -> ApiRegistryBackend:
    """Create an API-backed desktop registry over a local SQLite database."""

    database_path = config.database_path.expanduser()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    repository = SQLiteRegistryRepository(database_path)
    _ensure_tenant(repository, config)
    service = RegistryService(repository)
    return ApiRegistryBackend(
        RegistryApi(service, repository),
        config.tenant_id,
        config.actor_id,
        registry_url=config.registry_url,
    )


def local_registry_health(config: LocalRegistryConfig) -> LocalRegistryHealth:
    """Return a read-only health snapshot for the desktop-local registry."""

    database_path = config.database_path.expanduser()
    if not database_path.exists():
        return LocalRegistryHealth(database_path, False, None, 0, False, 0, 0, 0, 0, 0, 0, 0)
    repository = SQLiteRegistryRepository(database_path)
    with sqlite3.connect(database_path) as connection:
        song_count = _count(connection, "SELECT COUNT(*) FROM songs WHERE tenant_id = ?", config.tenant_id)
        export_count = _count(connection, "SELECT COUNT(*) FROM exports WHERE tenant_id = ?", config.tenant_id)
        reserved_count = _count(connection, "SELECT COUNT(*) FROM exports WHERE tenant_id = ? AND state = 'reserved'", config.tenant_id)
        active_count = _count(connection, "SELECT COUNT(*) FROM exports WHERE tenant_id = ? AND state = 'active'", config.tenant_id)
        failed_count = _count(connection, "SELECT COUNT(*) FROM exports WHERE tenant_id = ? AND state = 'failed'", config.tenant_id)
        revoked_count = _count(connection, "SELECT COUNT(*) FROM exports WHERE tenant_id = ? AND state = 'revoked'", config.tenant_id)
    return LocalRegistryHealth(
        database_path,
        True,
        repository.schema_version(),
        database_path.stat().st_size,
        repository.tenant(config.tenant_id) is not None,
        song_count,
        export_count,
        reserved_count,
        active_count,
        failed_count,
        revoked_count,
        len(repository.events(config.tenant_id)) if repository.tenant(config.tenant_id) is not None else 0,
    )


def _ensure_tenant(repository: SQLiteRegistryRepository, config: LocalRegistryConfig) -> None:
    """Create the desktop alpha tenant if this database is new."""

    if repository.tenant(config.tenant_id) is not None:
        return
    repository.add_tenant(
        TenantRecord(
            config.tenant_id,
            config.tenant_name,
            datetime.now(timezone.utc),
        )
    )


def _count(connection: sqlite3.Connection, sql: str, tenant_id: str) -> int:
    """Return one integer count from a tenant-scoped query."""

    row = connection.execute(sql, (tenant_id,)).fetchone()
    return int(row[0])
