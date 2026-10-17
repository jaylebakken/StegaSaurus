"""Adapt API Gateway HTTP API events to the Saurus registry gateway.

The preferred alpha front door is API Gateway HTTP API with a Cognito JWT
authorizer. API Gateway validates the token signature, issuer, audience, and
expiry before invoking Lambda. This module translates the resulting event into
the repository's small `ApiRequest` record, extracts the validated JWT claims,
and calls `RegistryGateway.handle_verified`.

It does not create AWS resources, fetch Cognito JWKS documents, or decide tenant
policy. Tenant mapping remains an injected resolver so alpha can start with a
small explicit allow-list and later move to durable account records.
"""

from __future__ import annotations

from base64 import b64decode, b64encode
from dataclasses import dataclass
import json
from typing import Any

from saurus_registry.api.contracts import ApiRequest, ApiResponse

from .gateway import GatewayPrincipal, JwtClaims, RegistryGateway


@dataclass(frozen=True, slots=True)
class StaticTenantResolver:
    """Resolve a small explicit allow-list of JWT identities to tenants."""

    principals_by_subject: dict[str, GatewayPrincipal]
    principals_by_email: dict[str, GatewayPrincipal]

    @classmethod
    def from_records(cls, records: tuple[dict[str, object], ...]) -> StaticTenantResolver:
        """Build a resolver from JSON-like account mapping records."""

        subjects: dict[str, GatewayPrincipal] = {}
        emails: dict[str, GatewayPrincipal] = {}
        for record in records:
            principal = GatewayPrincipal(
                _required_text(record, "tenant_id"),
                _required_text(record, "actor_id"),
                tuple(_required_text_list(record, "roles")),
            )
            subject = _optional_text(record, "subject")
            email = _optional_text(record, "email")
            if not subject and not email:
                raise ValueError("tenant mapping requires subject or email")
            if subject:
                subjects[subject] = principal
            if email:
                emails[email.lower()] = principal
        return cls(subjects, emails)

    def resolve(self, claims: JwtClaims) -> GatewayPrincipal:
        """Return the registry principal for verified JWT claims."""

        if claims.subject in self.principals_by_subject:
            return self.principals_by_subject[claims.subject]
        email = claims.email.lower()
        if email in self.principals_by_email:
            return self.principals_by_email[email]
        raise PermissionError("account is not enrolled")


def api_request_from_http_api_event(event: dict[str, Any]) -> ApiRequest:
    """Translate one API Gateway HTTP API v2 event to an API request."""

    context = event.get("requestContext")
    if not isinstance(context, dict):
        raise ValueError("requestContext is required")
    http = context.get("http")
    if not isinstance(http, dict):
        raise ValueError("requestContext.http is required")
    method = _required_event_text(http, "method")
    path = _required_event_text(event, "rawPath")
    query = event.get("rawQueryString", "")
    if query:
        path = f"{path}?{query}"
    headers = event.get("headers") or {}
    if not isinstance(headers, dict):
        raise ValueError("headers must be an object")
    body_text = event.get("body") or ""
    if not isinstance(body_text, str):
        raise ValueError("body must be a string")
    body = b64decode(body_text.encode("ascii")) if event.get("isBase64Encoded") else body_text.encode("utf-8")
    return ApiRequest(method, path, {str(key): str(value) for key, value in headers.items()}, body)


def jwt_claims_from_http_api_event(event: dict[str, Any]) -> JwtClaims:
    """Extract already-validated JWT claims from an HTTP API event."""

    context = event.get("requestContext")
    if not isinstance(context, dict):
        raise ValueError("requestContext is required")
    authorizer = context.get("authorizer")
    if not isinstance(authorizer, dict):
        raise PermissionError("JWT authorizer context is required")
    jwt = authorizer.get("jwt")
    if not isinstance(jwt, dict):
        raise PermissionError("JWT claims are required")
    claims = jwt.get("claims")
    if not isinstance(claims, dict):
        raise PermissionError("JWT claims are required")
    return JwtClaims(
        _required_event_text(claims, "sub"),
        _required_event_text(claims, "email"),
        _required_event_text(claims, "iss"),
        _claim_audience(claims),
    )


def http_api_response_from_api_response(response: ApiResponse) -> dict[str, object]:
    """Translate one gateway API response into a Lambda proxy response."""

    content_type = response.headers.get("Content-Type", "")
    is_text = content_type.startswith("application/json") or content_type.startswith("text/")
    body = response.body.decode("utf-8") if is_text else b64encode(response.body).decode("ascii")
    return {
        "statusCode": response.status,
        "headers": response.headers,
        "isBase64Encoded": not is_text,
        "body": body,
    }


def handle_http_api_event(event: dict[str, Any], gateway: RegistryGateway) -> dict[str, object]:
    """Handle one API Gateway HTTP API event with a configured gateway."""

    try:
        request = api_request_from_http_api_event(event)
        claims = jwt_claims_from_http_api_event(event)
        return http_api_response_from_api_response(gateway.handle_verified(request, claims))
    except PermissionError as error:
        return _lambda_error(403, "authorization", str(error))
    except ValueError as error:
        return _lambda_error(400, "validation", str(error))


def _lambda_error(status: int, code: str, message: str) -> dict[str, object]:
    """Build a browser-safe Lambda proxy error response."""

    body = json.dumps({"schema_version": 1, "error": {"code": code, "message": message}}, sort_keys=True)
    return {
        "statusCode": status,
        "headers": {"Content-Type": "application/json", "Access-Control-Allow-Origin": "https://saurus-audio.com"},
        "isBase64Encoded": False,
        "body": body,
    }


def _claim_audience(claims: dict[str, object]) -> str:
    """Return ID-token `aud` or access-token `client_id` from claims."""

    audience = claims.get("aud") or claims.get("client_id")
    if not isinstance(audience, str) or not audience.strip():
        raise ValueError("JWT audience claim is required")
    return audience.strip()


def _required_event_text(values: dict[str, object], name: str) -> str:
    """Return one required non-empty event text field."""

    value = values.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def _required_text(record: dict[str, object], name: str) -> str:
    """Return one required non-empty mapping text field."""

    value = record.get(name)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} is required")
    return value.strip()


def _optional_text(record: dict[str, object], name: str) -> str:
    """Return one optional text field from a mapping record."""

    value = record.get(name)
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ValueError(f"{name} must be text")
    return value.strip()


def _required_text_list(record: dict[str, object], name: str) -> tuple[str, ...]:
    """Return one required list of non-empty text values."""

    value = record.get(name)
    if not isinstance(value, list) or not value:
        raise ValueError(f"{name} must be a non-empty list")
    normalized = tuple(item.strip() for item in value if isinstance(item, str) and item.strip())
    if len(normalized) != len(value):
        raise ValueError(f"{name} must contain only non-empty text")
    return normalized
