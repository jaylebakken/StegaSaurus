"""Run the registry API inside a lightweight alpha container harness.

The production registry service will eventually sit behind managed database and
secret adapters. The alpha container still needs a real entrypoint so the ECS
task definition is not a placeholder. This module builds the existing
`RegistryApi` router with SQLite by default or managed PostgreSQL when ECS
injects the alpha database endpoint and credentials. It exposes a simple health
endpoint and can perform a launch check without starting a long-running server.

It does not fetch AWS Secrets Manager directly or validate CloudTrail/KMS
evidence. Those remain alpha deployment gates.
"""

from __future__ import annotations

import argparse
from collections.abc import Mapping
from dataclasses import asdict, dataclass
import json
import os
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from .api import ApiRequest, HmacBearerAuthenticator, RegistryApi
from .application import RegistryService
from .container_runtime import (
    RegistryDatabaseCredentials,
    RegistryPostgresConfig,
    RegistryRuntimeSecrets,
    database_credentials_from_env,
    postgres_config_from_env,
    runtime_secrets_from_env,
)
from .postgres import PostgresConnectionSettings, PostgresRegistryRepository
from .repository import RegistryRepository
from .sqlite import SQLiteRegistryRepository

__all__ = [
    "RegistryDatabaseCredentials",
    "RegistryContainerConfig",
    "RegistryPostgresConfig",
    "RegistryRuntimeSecrets",
    "build_registry_container_api",
    "build_registry_repository",
    "container_config_from_env",
    "database_credentials_from_env",
    "main",
    "registry_container_handler",
    "postgres_config_from_env",
    "runtime_secrets_from_env",
]


@dataclass(frozen=True, slots=True)
class RegistryContainerConfig:
    """Declare alpha registry container runtime settings."""

    database_path: Path
    host: str = "0.0.0.0"
    port: int = 8080
    api_signing_secret: bytes | None = None

    def __post_init__(self) -> None:
        """Validate container settings before server startup."""

        if not self.host.strip():
            raise ValueError("host must not be empty")
        if self.port < 1 or self.port > 65535:
            raise ValueError("port must be a TCP port")
        if self.api_signing_secret is not None and len(self.api_signing_secret) < 32:
            raise ValueError("api_signing_secret must contain at least 32 bytes")


def container_config_from_env(env: Mapping[str, str]) -> RegistryContainerConfig:
    """Build container settings from environment-style values."""

    database_path = Path(env.get("SAURUS_REGISTRY_DATABASE_PATH", "/tmp/saurus-alpha/registry.sqlite3"))
    host = env.get("SAURUS_REGISTRY_HOST", "0.0.0.0")
    port_text = env.get("SAURUS_REGISTRY_PORT", "8080")
    try:
        port = int(port_text)
    except ValueError as error:
        raise ValueError("SAURUS_REGISTRY_PORT must be an integer") from error
    signing_secret = env.get("SAURUS_API_SIGNING_SECRET")
    return RegistryContainerConfig(
        database_path=database_path,
        host=host,
        port=port,
        api_signing_secret=signing_secret.encode("utf-8") if signing_secret else None,
    )


def build_registry_repository(
    config: RegistryContainerConfig,
    postgres_config: RegistryPostgresConfig | None = None,
    database_credentials: RegistryDatabaseCredentials | None = None,
) -> RegistryRepository:
    """Build the durable repository for one alpha container process."""

    if postgres_config is None:
        config.database_path.parent.mkdir(parents=True, exist_ok=True)
        return SQLiteRegistryRepository(config.database_path)
    if database_credentials is None:
        raise ValueError("PostgreSQL registry mode requires SAURUS_DATABASE_SECRET_JSON")
    return PostgresRegistryRepository.from_settings(
        PostgresConnectionSettings(
            postgres_config.host,
            postgres_config.port,
            postgres_config.database,
            database_credentials.username,
            database_credentials.password,
        )
    )


def build_registry_container_api(
    config: RegistryContainerConfig,
    postgres_config: RegistryPostgresConfig | None = None,
    database_credentials: RegistryDatabaseCredentials | None = None,
) -> RegistryApi:
    """Build the registry API router for one container process."""

    repository = build_registry_repository(config, postgres_config, database_credentials)
    service = RegistryService(repository)
    authenticator = HmacBearerAuthenticator(config.api_signing_secret) if config.api_signing_secret else None
    return RegistryApi(service, repository, authenticator=authenticator)


def registry_container_handler(api: RegistryApi) -> type[BaseHTTPRequestHandler]:
    """Return an HTTP handler with health and registry API routes."""

    class RegistryContainerHandler(BaseHTTPRequestHandler):
        """Serve health checks and versioned registry API requests."""

        def do_GET(self) -> None:
            """Handle one GET request."""

            self._handle()

        def do_POST(self) -> None:
            """Handle one POST request."""

            self._handle()

        def _handle(self) -> None:
            """Translate HTTP server state to a registry API request."""

            if self.path == "/health":
                self._send(200, b'{"status":"ok"}', {"Content-Type": "application/json"})
                return
            length = int(self.headers.get("Content-Length", "0"))
            body = self.rfile.read(length) if length else b""
            response = api.handle(ApiRequest(self.command, self.path, dict(self.headers.items()), body))
            self._send(response.status, response.body, response.headers)

        def _send(self, status: int, body: bytes, headers: Mapping[str, str]) -> None:
            """Send one HTTP response."""

            self.send_response(status)
            for name, value in headers.items():
                self.send_header(name, value)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    return RegistryContainerHandler


def main(argv: list[str] | None = None) -> int:
    """Run the alpha registry container harness."""

    parser = argparse.ArgumentParser(description="Run the Saurus alpha registry HTTP container.")
    parser.add_argument("--database-path", type=Path)
    parser.add_argument("--host")
    parser.add_argument("--port", type=int)
    parser.add_argument("--launch-check", action="store_true")
    args = parser.parse_args(argv)
    config = container_config_from_env(os.environ)
    postgres_config = postgres_config_from_env(os.environ)
    database_credentials = database_credentials_from_env(os.environ)
    runtime_secrets = runtime_secrets_from_env(os.environ)
    if args.database_path is not None:
        config = RegistryContainerConfig(args.database_path, config.host, config.port, config.api_signing_secret)
    if args.host is not None:
        config = RegistryContainerConfig(config.database_path, args.host, config.port, config.api_signing_secret)
    if args.port is not None:
        config = RegistryContainerConfig(config.database_path, config.host, args.port, config.api_signing_secret)
    if args.launch_check:
        print(
            json.dumps(
                {
                    "launch_check": "ok",
                    "repository": "postgresql" if postgres_config else "sqlite",
                    "config": {**asdict(config), "database_path": str(config.database_path), "api_signing_secret": bool(config.api_signing_secret)},
                    "postgres": asdict(postgres_config) if postgres_config else None,
                    "runtime_secrets": asdict(runtime_secrets),
                },
                sort_keys=True,
            )
        )
        return 0
    api = build_registry_container_api(config, postgres_config, database_credentials)
    server = HTTPServer((config.host, config.port), registry_container_handler(api))
    server.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
