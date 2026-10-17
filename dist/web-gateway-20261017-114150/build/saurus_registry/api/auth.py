"""Authenticate concise registry API requests before service dispatch.

The first registry API accepted tenant and actor headers as a local development
contract. This module keeps that fallback for tests and migration, while adding
a signed bearer-token path with explicit tenant, actor, role, and optional
expiry claims. It is deliberately small and framework-free; production can swap
the authenticator without changing registry application services.
"""

from __future__ import annotations

from base64 import urlsafe_b64decode, urlsafe_b64encode
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
from typing import Protocol

from .contracts import ApiRequest


@dataclass(frozen=True, slots=True)
class RequestContext:
    """Hold authenticated tenant, actor, request, and role metadata."""

    tenant_id: str
    actor_id: str
    request_id: str
    roles: tuple[str, ...] = ()

    def require_role(self, role: str) -> None:
        """Reject the context unless it carries one required role."""

        if role not in self.roles:
            raise PermissionError(f"missing required role: {role}")


class RegistryAuthenticator(Protocol):
    """Validate registry API credentials and return request identity claims."""

    def authenticate(self, request: ApiRequest) -> RequestContext:
        """Authenticate one request before route authorization."""


class HmacBearerAuthenticator:
    """Authenticate compact signed bearer tokens for registry API tests and pilots."""

    def __init__(self, secret: bytes, *, clock: Callable[[], datetime] | None = None) -> None:
        """Initialize token verification with explicit secret and clock seams."""

        if not secret:
            raise ValueError("secret must not be empty")
        self._secret = secret
        self._clock = clock or (lambda: datetime.now(timezone.utc))

    def authenticate(self, request: ApiRequest) -> RequestContext:
        """Validate the bearer token signature, expiry, and visible claims."""

        token = header_value(request.headers, "Authorization")
        if token is None or not token.startswith("Bearer "):
            raise PermissionError("authorization bearer token is required")
        version, payload_text, signature_text = _split_token(token.removeprefix("Bearer ").strip())
        if version != "saurus-v1":
            raise PermissionError("authorization token version is not supported")
        expected = _signature(self._secret, payload_text)
        if not hmac.compare_digest(signature_text, expected):
            raise PermissionError("authorization token signature is invalid")
        payload = _payload(payload_text)
        expires = payload.get("expires_utc")
        if isinstance(expires, str) and datetime.fromisoformat(expires) <= self._now():
            raise PermissionError("authorization token has expired")
        return RequestContext(
            _text_claim(payload, "tenant_id"),
            _text_claim(payload, "actor_id"),
            "",
            tuple(_roles(payload)),
        )

    def issue_token(
        self,
        tenant_id: str,
        actor_id: str,
        roles: tuple[str, ...],
        expires_utc: datetime | None = None,
    ) -> str:
        """Create a signed bearer token for tests, pilots, or device enrollment spikes."""

        if expires_utc is not None and (expires_utc.tzinfo is None or expires_utc.utcoffset() is None):
            raise ValueError("expires_utc must be timezone-aware")
        payload: dict[str, object] = {"tenant_id": tenant_id, "actor_id": actor_id, "roles": list(roles)}
        if expires_utc is not None:
            payload["expires_utc"] = expires_utc.isoformat()
        payload_text = _b64(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8"))
        return f"Bearer saurus-v1.{payload_text}.{_signature(self._secret, payload_text)}"

    def _now(self) -> datetime:
        """Return a timezone-aware authentication timestamp."""

        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return now


def request_context(
    request: ApiRequest,
    *,
    mutating: bool,
    authenticator: RegistryAuthenticator | None,
    required_role: str,
) -> RequestContext:
    """Extract request identity from signed auth or development headers."""

    request_id = header_value(request.headers, "Idempotency-Key") if mutating else header_value(request.headers, "X-Request-ID")
    if not request_id:
        raise ValueError("tenant, actor, and request identifiers are required")
    if authenticator is None:
        tenant_id = header_value(request.headers, "X-Saurus-Tenant")
        actor_id = header_value(request.headers, "X-Saurus-Actor")
        if not tenant_id or not actor_id:
            raise ValueError("tenant, actor, and request identifiers are required")
        return RequestContext(tenant_id, actor_id, request_id, (required_role,))
    context = authenticator.authenticate(request)
    context.require_role(required_role)
    tenant_header = header_value(request.headers, "X-Saurus-Tenant")
    if tenant_header is not None and tenant_header != context.tenant_id:
        raise PermissionError("tenant header does not match authorization token")
    return RequestContext(context.tenant_id, context.actor_id, request_id, context.roles)


def header_value(headers: dict[str, str], name: str) -> str | None:
    """Return one case-insensitive header value."""

    lowered = name.lower()
    for key, value in headers.items():
        if key.lower() == lowered:
            return value
    return None


def _split_token(token: str) -> tuple[str, str, str]:
    """Split one compact bearer token into version, payload, and signature."""

    parts = token.split(".")
    if len(parts) != 3:
        raise PermissionError("authorization token is malformed")
    return parts[0], parts[1], parts[2]


def _payload(payload_text: str) -> dict[str, object]:
    """Decode one bearer token JSON payload."""

    try:
        value = json.loads(urlsafe_b64decode(_pad(payload_text)).decode("utf-8"))
    except (ValueError, json.JSONDecodeError) as error:
        raise PermissionError(f"authorization token payload is invalid: {error}") from error
    if not isinstance(value, dict):
        raise PermissionError("authorization token payload must be an object")
    return value


def _roles(payload: dict[str, object]) -> tuple[str, ...]:
    """Return normalized role names from one payload."""

    value = payload.get("roles")
    if not isinstance(value, list) or not all(isinstance(item, str) and item.strip() for item in value):
        raise PermissionError("authorization token roles are invalid")
    return tuple(item.strip() for item in value)


def _text_claim(payload: dict[str, object], name: str) -> str:
    """Return one non-empty text claim from a token payload."""

    value = payload.get(name)
    if not isinstance(value, str) or not value.strip():
        raise PermissionError(f"authorization token claim is missing: {name}")
    return value.strip()


def _signature(secret: bytes, payload_text: str) -> str:
    """Sign one payload body with HMAC-SHA256."""

    return hmac.new(secret, payload_text.encode("ascii"), hashlib.sha256).hexdigest()


def _b64(value: bytes) -> str:
    """Encode unpadded URL-safe base64 text."""

    return urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _pad(value: str) -> bytes:
    """Restore URL-safe base64 padding for decoding."""

    return (value + "=" * (-len(value) % 4)).encode("ascii")
