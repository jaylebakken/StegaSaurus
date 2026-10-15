"""Build the Lambda gateway process from alpha runtime environment values.

API Gateway validates Cognito JWTs before Lambda runs. The Lambda runtime then
has a narrower job:

1. Read registry endpoint, database, signing-secret, and tenant-mapping values.
2. Build the existing registry API with the same repository/authenticator code
   used by the alpha container.
3. Build a `RegistryGateway` that maps verified Cognito claims to one allowed
   tenant principal.
4. Translate each HTTP API event through `lambda_adapter`.

This module intentionally avoids AWS SDK calls during invocation. CloudFormation
injects dynamic secret values into environment variables, which keeps the first
alpha Lambda out of the business of fetching Secrets Manager values from a VPC
without NAT.
"""

from __future__ import annotations

from dataclasses import dataclass
import json
import os
from typing import Any

from saurus_registry import HmacBearerAuthenticator, RegistryApi, RegistryService
from saurus_registry.container import build_registry_repository, container_config_from_env
from saurus_registry.container_runtime import database_credentials_from_env, postgres_config_from_env

from .gateway import JwtClaims, RegistryGateway
from .lambda_adapter import StaticTenantResolver, handle_http_api_event

__all__ = [
    "GatewayRuntimeConfig",
    "build_gateway_from_env",
    "lambda_handler",
    "reset_runtime_cache",
]


@dataclass(frozen=True, slots=True)
class GatewayRuntimeConfig:
    """Declare the Lambda-only gateway settings parsed from environment."""

    tenant_records: tuple[dict[str, object], ...]
    token_lifetime_seconds: int = 60

    def __post_init__(self) -> None:
        """Validate gateway runtime settings before any request is handled."""

        if not self.tenant_records:
            raise ValueError("tenant mapping must include at least one record")
        if self.token_lifetime_seconds < 1 or self.token_lifetime_seconds > 300:
            raise ValueError("token lifetime must be between 1 and 300 seconds")


class _GatewayAuthorizerVerifier:
    """Document that JWT verification happens before Lambda invocation."""

    def verify(self, token: str) -> JwtClaims:
        """Reject direct browser-token verification inside the Lambda runtime."""

        raise PermissionError("JWT verification is delegated to API Gateway")


_GATEWAY: RegistryGateway | None = None


def lambda_handler(event: dict[str, Any], context: object) -> dict[str, object]:
    """Handle one API Gateway HTTP API v2 Lambda event."""

    del context
    return handle_http_api_event(event, _cached_gateway())


def build_gateway_from_env(env: dict[str, str] | None = None) -> RegistryGateway:
    """Build a registry gateway from environment-style runtime settings."""

    values = dict(os.environ if env is None else env)
    container_config = container_config_from_env(values)
    if container_config.api_signing_secret is None:
        raise ValueError("SAURUS_API_SIGNING_SECRET is required for the web gateway")
    postgres_config = postgres_config_from_env(values)
    database_credentials = database_credentials_from_env(values)
    repository = build_registry_repository(container_config, postgres_config, database_credentials)
    service = RegistryService(repository)
    authenticator = HmacBearerAuthenticator(container_config.api_signing_secret)
    registry_api = RegistryApi(service, repository, authenticator=authenticator)
    gateway_config = _gateway_config_from_env(values)
    return RegistryGateway(
        registry_api,
        _GatewayAuthorizerVerifier(),
        StaticTenantResolver.from_records(gateway_config.tenant_records),
        authenticator,
        token_lifetime_seconds=gateway_config.token_lifetime_seconds,
    )


def reset_runtime_cache() -> None:
    """Clear the cached gateway so tests or warm-start checks can rebuild it."""

    global _GATEWAY
    _GATEWAY = None


def _cached_gateway() -> RegistryGateway:
    """Return the warm Lambda gateway instance, building it once per process."""

    global _GATEWAY
    if _GATEWAY is None:
        _GATEWAY = build_gateway_from_env()
    return _GATEWAY


def _gateway_config_from_env(env: dict[str, str]) -> GatewayRuntimeConfig:
    """Parse Lambda gateway-only environment values."""

    records = _tenant_records(env.get("SAURUS_GATEWAY_TENANT_MAPPINGS_JSON"))
    lifetime_text = env.get("SAURUS_GATEWAY_TOKEN_LIFETIME_SECONDS", "60")
    try:
        lifetime = int(lifetime_text)
    except ValueError as error:
        raise ValueError("SAURUS_GATEWAY_TOKEN_LIFETIME_SECONDS must be an integer") from error
    return GatewayRuntimeConfig(records, lifetime)


def _tenant_records(secret_text: str | None) -> tuple[dict[str, object], ...]:
    """Decode the tenant mapping secret used by the static alpha resolver."""

    if secret_text is None:
        raise ValueError("SAURUS_GATEWAY_TENANT_MAPPINGS_JSON is required")
    try:
        value = json.loads(secret_text)
    except json.JSONDecodeError as error:
        raise ValueError("SAURUS_GATEWAY_TENANT_MAPPINGS_JSON must be valid JSON") from error
    if not isinstance(value, dict):
        raise ValueError("SAURUS_GATEWAY_TENANT_MAPPINGS_JSON must be a JSON object")
    records = value.get("records")
    if not isinstance(records, list):
        raise ValueError("tenant mapping must include a records list")
    normalized: list[dict[str, object]] = []
    for record in records:
        if not isinstance(record, dict):
            raise ValueError("tenant mapping records must be JSON objects")
        normalized.append(dict(record))
    return tuple(normalized)
