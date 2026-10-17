"""Bridge browser JWT requests into the private registry API.

The live registry API uses a server-held HMAC bearer token. That is a good
internal service credential but unsafe for browser code. This module provides a
small gateway process map:

1. Accept a browser-shaped `ApiRequest` with `Authorization: Bearer <jwt>`.
2. Verify the JWT through an injected verifier.
3. Resolve the verified subject into tenant, actor, and registry roles.
4. Replace the browser token with a short-lived internal registry token.
5. Forward the request to the existing `RegistryApi` router.

The module deliberately does not implement Cognito JWKS verification itself.
Production can put API Gateway's JWT authorizer in front of this layer or inject
a maintained Cognito verifier. Tests can inject deterministic verifiers without
network access.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
import json
from typing import Protocol
from urllib.parse import urlsplit

from saurus_registry.api.auth import HmacBearerAuthenticator
from saurus_registry.api.auth import header_value
from saurus_registry.api.contracts import ApiRequest, ApiResponse
from saurus_registry.api.router import RegistryApi

_JSON_HEADERS = {"Content-Type": "application/json"}
_CORS_HEADERS = {
    "Access-Control-Allow-Origin": "https://saurus-audio.com",
    "Access-Control-Allow-Headers": "Authorization, Content-Type, Idempotency-Key, X-Request-ID",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Vary": "Origin",
}


@dataclass(frozen=True, slots=True)
class JwtClaims:
    """Represent the verified browser identity claims needed by the gateway."""

    subject: str
    email: str
    issuer: str
    audience: str

    def __post_init__(self) -> None:
        """Validate required JWT identity fields."""

        for name, value in (("subject", self.subject), ("email", self.email), ("issuer", self.issuer), ("audience", self.audience)):
            if not value.strip():
                raise ValueError(f"{name} must not be empty")


@dataclass(frozen=True, slots=True)
class GatewayPrincipal:
    """Represent the registry identity allowed for one verified web user."""

    tenant_id: str
    actor_id: str
    roles: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate tenant, actor, and registry role values."""

        if not self.tenant_id.strip():
            raise ValueError("tenant_id must not be empty")
        if not self.actor_id.strip():
            raise ValueError("actor_id must not be empty")
        if not self.roles or any(not role.strip() for role in self.roles):
            raise ValueError("roles must contain at least one non-empty role")

    def require_role(self, role: str) -> None:
        """Reject the principal unless it carries one registry role."""

        if role not in self.roles:
            raise PermissionError(f"missing required role: {role}")


class JwtVerifier(Protocol):
    """Verify a browser bearer token and return trusted identity claims."""

    def verify(self, token: str) -> JwtClaims:
        """Verify one JWT string."""


class TenantResolver(Protocol):
    """Map verified browser identity claims to registry access."""

    def resolve(self, claims: JwtClaims) -> GatewayPrincipal:
        """Resolve one verified user into a registry principal."""


class RegistryGateway:
    """Authorize browser requests and forward them to the private registry."""

    def __init__(
        self,
        registry_api: RegistryApi,
        jwt_verifier: JwtVerifier,
        tenant_resolver: TenantResolver,
        registry_authenticator: HmacBearerAuthenticator,
        *,
        principal_hook: Callable[[GatewayPrincipal], None] | None = None,
        token_lifetime_seconds: int = 60,
        clock: Callable[[], datetime] | None = None,
    ) -> None:
        """Bind gateway dependencies and internal token lifetime."""

        if token_lifetime_seconds < 1 or token_lifetime_seconds > 300:
            raise ValueError("token_lifetime_seconds must be between 1 and 300")
        self._registry_api = registry_api
        self._jwt_verifier = jwt_verifier
        self._tenant_resolver = tenant_resolver
        self._registry_authenticator = registry_authenticator
        self._principal_hook = principal_hook or (lambda _principal: None)
        self._token_lifetime = timedelta(seconds=token_lifetime_seconds)
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def handle(self, request: ApiRequest) -> ApiResponse:
        """Handle one browser request and return a browser-safe response."""

        try:
            if request.method.upper() == "OPTIONS":
                return _with_cors(ApiResponse(204, {}, b""))
            token = _browser_token(request)
            claims = self._jwt_verifier.verify(token)
            return self.handle_verified(request, claims)
        except PermissionError as error:
            return _with_cors(_error(403, "authorization", str(error), _request_id(request)))
        except ValueError as error:
            status = 404 if "route is not registered" in str(error) else 400
            return _with_cors(_error(status, "validation", str(error), _request_id(request)))

    def handle_verified(self, request: ApiRequest, claims: JwtClaims) -> ApiResponse:
        """Handle a request whose JWT was verified by a trusted front door."""

        try:
            if request.method.upper() == "OPTIONS":
                return _with_cors(ApiResponse(204, {}, b""))
            role = _route_role(request.method, request.path)
            principal = self._tenant_resolver.resolve(claims)
            principal.require_role(role)
            self._principal_hook(principal)
            forwarded = self._forward_request(request, principal)
            return _with_cors(self._registry_api.handle(forwarded))
        except PermissionError as error:
            return _with_cors(_error(403, "authorization", str(error), _request_id(request)))
        except ValueError as error:
            status = 404 if "route is not registered" in str(error) else 400
            return _with_cors(_error(status, "validation", str(error), _request_id(request)))

    def _forward_request(self, request: ApiRequest, principal: GatewayPrincipal) -> ApiRequest:
        """Replace browser credentials with internal registry credentials."""

        tenant_header = header_value(request.headers, "X-Saurus-Tenant")
        if tenant_header is not None and tenant_header != principal.tenant_id:
            raise PermissionError("tenant header does not match authenticated account")
        headers = {key: value for key, value in request.headers.items() if key.lower() != "authorization"}
        headers["X-Saurus-Tenant"] = principal.tenant_id
        headers["Authorization"] = self._registry_authenticator.issue_token(
            principal.tenant_id,
            principal.actor_id,
            principal.roles,
            self._now() + self._token_lifetime,
        )
        return ApiRequest(request.method, request.path, headers, request.body)

    def _now(self) -> datetime:
        """Return a timezone-aware gateway timestamp."""

        now = self._clock()
        if not isinstance(now, datetime) or now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return now


def _browser_token(request: ApiRequest) -> str:
    """Extract the browser bearer token without logging it."""

    authorization = header_value(request.headers, "Authorization")
    if authorization is None or not authorization.startswith("Bearer "):
        raise PermissionError("browser bearer token is required")
    token = authorization.removeprefix("Bearer ").strip()
    if not token:
        raise PermissionError("browser bearer token is required")
    return token


def _route_role(method: str, path: str) -> str:
    """Return the registry role required by one browser route."""

    segments = [part for part in urlsplit(path).path.split("/") if part]
    upper_method = method.upper()
    if upper_method == "POST" and segments == ["v1", "songs"]:
        return "registry.write"
    if upper_method == "GET" and len(segments) == 3 and segments[1] == "songs":
        return "registry.read"
    if upper_method == "GET" and len(segments) == 4 and segments[1] == "songs" and segments[3] == "verification-bundle":
        return "registry.verify"
    if upper_method == "POST" and len(segments) == 4 and segments[1] == "songs" and segments[3] == "exports:reserve":
        return "registry.write"
    if upper_method == "GET" and len(segments) == 3 and segments[1] == "exports":
        return "registry.read"
    if upper_method == "GET" and len(segments) == 4 and segments[1] == "exports" and segments[3] == "verification-record":
        return "registry.verify"
    if upper_method == "GET" and len(segments) == 4 and segments[1] == "exports" and segments[3] == "lineage":
        return "registry.read"
    if upper_method == "POST" and len(segments) == 3 and segments[1] == "exports":
        _, _, action = segments[2].partition(":")
        return "registry.verify" if action == "verification-result" else "registry.write"
    raise ValueError("route is not registered for the web gateway")


def _request_id(request: ApiRequest) -> str:
    """Return a stable request identifier for gateway errors."""

    return header_value(request.headers, "Idempotency-Key") or header_value(request.headers, "X-Request-ID") or ""


def _error(status: int, code: str, message: str, request_id: str) -> ApiResponse:
    """Build one gateway JSON error response."""

    payload = {"schema_version": 1, "request_id": request_id, "error": {"code": code, "message": message}}
    return ApiResponse(status, dict(_JSON_HEADERS), json.dumps(payload, sort_keys=True).encode("utf-8"))


def _with_cors(response: ApiResponse) -> ApiResponse:
    """Attach browser CORS headers to one response."""

    headers = dict(response.headers)
    headers.update(_CORS_HEADERS)
    return ApiResponse(response.status, headers, response.body)
