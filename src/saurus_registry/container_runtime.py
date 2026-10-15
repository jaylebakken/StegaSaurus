"""Parse alpha container runtime settings that are not the HTTP server itself.

The registry container receives a mix of non-secret endpoint metadata and
managed secret values injected by ECS. This module validates those inputs for
launch checks while deliberately exposing only secret presence. A separate
credential parser returns the secret-bearing values only to the repository
factory that opens the PostgreSQL connection.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
import json

__all__ = [
    "RegistryPostgresConfig",
    "RegistryDatabaseCredentials",
    "RegistryRuntimeSecrets",
    "database_credentials_from_env",
    "postgres_config_from_env",
    "runtime_secrets_from_env",
]


@dataclass(frozen=True, slots=True)
class RegistryRuntimeSecrets:
    """Summarize injected runtime secrets without retaining secret values."""

    database_username: str | None = None
    database_password_present: bool = False
    bootstrap_admin_secret_present: bool = False
    device_enrollment_secret_present: bool = False

    def __post_init__(self) -> None:
        """Validate parsed runtime-secret metadata."""

        if self.database_password_present and not (self.database_username and self.database_username.strip()):
            raise ValueError("database secret must include username when password is present")


@dataclass(frozen=True, slots=True)
class RegistryDatabaseCredentials:
    """Carry database credentials to the repository without diagnostic output."""

    username: str
    password: str = field(repr=False)

    def __post_init__(self) -> None:
        """Validate database credentials before connection setup."""

        if not self.username.strip():
            raise ValueError("database username must not be empty")
        if not self.password.strip():
            raise ValueError("database password must not be empty")


@dataclass(frozen=True, slots=True)
class RegistryPostgresConfig:
    """Describe a managed PostgreSQL endpoint without secret material."""

    host: str
    port: int
    database: str

    def __post_init__(self) -> None:
        """Validate PostgreSQL endpoint metadata."""

        if not self.host.strip():
            raise ValueError("postgres host must not be empty")
        if self.port < 1 or self.port > 65535:
            raise ValueError("postgres port must be a TCP port")
        if not self.database.strip():
            raise ValueError("postgres database must not be empty")


def postgres_config_from_env(env: Mapping[str, str]) -> RegistryPostgresConfig | None:
    """Parse optional managed PostgreSQL endpoint settings."""

    host = env.get("SAURUS_POSTGRES_HOST")
    database = env.get("SAURUS_POSTGRES_DATABASE")
    port_text = env.get("SAURUS_POSTGRES_PORT", "5432")
    if host is None and database is None:
        return None
    if host is None or database is None:
        raise ValueError("SAURUS_POSTGRES_HOST and SAURUS_POSTGRES_DATABASE must be set together")
    try:
        port = int(port_text)
    except ValueError as error:
        raise ValueError("SAURUS_POSTGRES_PORT must be an integer") from error
    return RegistryPostgresConfig(host, port, database)


def runtime_secrets_from_env(env: Mapping[str, str]) -> RegistryRuntimeSecrets:
    """Parse injected managed secrets without exposing their values."""

    database_secret = _json_secret(env.get("SAURUS_DATABASE_SECRET_JSON"), "SAURUS_DATABASE_SECRET_JSON")
    bootstrap_secret = env.get("SAURUS_BOOTSTRAP_ADMIN_SECRET")
    device_secret = env.get("SAURUS_DEVICE_ENROLLMENT_SECRET")
    if bootstrap_secret is not None and len(bootstrap_secret.encode("utf-8")) < 32:
        raise ValueError("SAURUS_BOOTSTRAP_ADMIN_SECRET must contain at least 32 bytes")
    if device_secret is not None and len(device_secret.encode("utf-8")) < 32:
        raise ValueError("SAURUS_DEVICE_ENROLLMENT_SECRET must contain at least 32 bytes")
    return RegistryRuntimeSecrets(
        database_username=str(database_secret["username"]) if database_secret else None,
        database_password_present=bool(database_secret),
        bootstrap_admin_secret_present=bootstrap_secret is not None,
        device_enrollment_secret_present=device_secret is not None,
    )


def database_credentials_from_env(env: Mapping[str, str]) -> RegistryDatabaseCredentials | None:
    """Parse database credentials for private PostgreSQL connection setup."""

    database_secret = _json_secret(env.get("SAURUS_DATABASE_SECRET_JSON"), "SAURUS_DATABASE_SECRET_JSON")
    if database_secret is None:
        return None
    return RegistryDatabaseCredentials(
        str(database_secret["username"]),
        str(database_secret["password"]),
    )


def _json_secret(secret_text: str | None, name: str) -> dict[str, object] | None:
    """Decode one JSON secret and validate its database credential shape."""

    if secret_text is None:
        return None
    try:
        value = json.loads(secret_text)
    except json.JSONDecodeError as error:
        raise ValueError(f"{name} must be valid JSON") from error
    if not isinstance(value, dict):
        raise ValueError(f"{name} must be a JSON object")
    for field in ("username", "password"):
        if not isinstance(value.get(field), str) or not str(value[field]).strip():
            raise ValueError(f"{name} must include {field}")
    return value
