"""Test the browser-to-registry gateway contract.

These tests keep the web alpha gateway below any AWS network dependency. They
prove the important local contract: browser JWTs are verified through an
injected seam, mapped to tenant-scoped registry principals, and replaced with
server-held HMAC registry credentials before the private registry API sees the
request.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from itertools import count
import json

from saurus_gateway import (
    GatewayPrincipal,
    JwtClaims,
    RegistryGateway,
    StaticTenantResolver,
    api_request_from_http_api_event,
    handle_http_api_event,
    jwt_claims_from_http_api_event,
)
from saurus_gateway.runtime import build_gateway_from_env, lambda_handler, reset_runtime_cache
from saurus_registry import ApiRequest, HmacBearerAuthenticator, InMemoryRegistryRepository, RegistryApi, RegistryService


NOW = datetime(2026, 10, 15, 12, 0, tzinfo=timezone.utc)


@dataclass(frozen=True, slots=True)
class _FakeJwtVerifier:
    """Verify deterministic token strings for gateway tests."""

    claims_by_token: dict[str, JwtClaims]

    def verify(self, token: str) -> JwtClaims:
        """Return claims for one known token."""

        if token not in self.claims_by_token:
            raise PermissionError("JWT is not trusted")
        return self.claims_by_token[token]


@dataclass(frozen=True, slots=True)
class _FakeTenantResolver:
    """Map verified JWT subjects to registry principals."""

    principals_by_subject: dict[str, GatewayPrincipal]

    def resolve(self, claims: JwtClaims) -> GatewayPrincipal:
        """Return the registry principal for one verified subject."""

        if claims.subject not in self.principals_by_subject:
            raise PermissionError("account is not enrolled")
        return self.principals_by_subject[claims.subject]


def _json_response(response) -> dict:
    """Decode one JSON response body."""

    return json.loads(response.body.decode("utf-8"))


def _api_body(**values: object) -> bytes:
    """Encode one JSON request body."""

    return json.dumps(values, sort_keys=True).encode("utf-8")


def _gateway(roles: tuple[str, ...]) -> tuple[RegistryGateway, RegistryService, InMemoryRegistryRepository]:
    """Build a gateway wired to a private HMAC-protected registry API."""

    identifiers = count(1)
    repository = InMemoryRegistryRepository()
    service = RegistryService(repository, clock=lambda: NOW, identifier_factory=lambda: f"id-{next(identifiers)}")
    tenant = service.register_tenant("Alpha Tenant", "owner", "request-tenant")
    registry_authenticator = HmacBearerAuthenticator(b"server-side-registry-secret", clock=lambda: NOW)
    registry_api = RegistryApi(service, repository, authenticator=registry_authenticator, clock=lambda: NOW)
    claims = JwtClaims("user-1", "artist@example.test", "https://issuer.example.test", "web-client")
    verifier = _FakeJwtVerifier({"browser.jwt": claims})
    resolver = _FakeTenantResolver({"user-1": GatewayPrincipal(tenant.tenant_id, "web-user-1", roles)})
    return (
        RegistryGateway(registry_api, verifier, resolver, registry_authenticator, clock=lambda: NOW),
        service,
        repository,
    )


def _browser_headers(request_id: str, *, mutating: bool = True) -> dict[str, str]:
    """Build browser request headers with no registry secret material."""

    headers = {"Authorization": "Bearer browser.jwt"}
    headers["Idempotency-Key" if mutating else "X-Request-ID"] = request_id
    return headers


def test_gateway_creates_song_with_server_side_registry_credentials() -> None:
    """Forward a browser JWT request by minting private registry credentials."""

    gateway, _, repository = _gateway(("registry.write", "registry.read", "registry.verify"))
    response = gateway.handle(
        ApiRequest(
            "POST",
            "/v1/songs",
            _browser_headers("request-song"),
            _api_body(
                title="Web Alpha Song",
                source_digest="sha256:web",
                sample_rate=48000,
                sample_count=96000,
                fingerprint_version="web-alpha-v1",
            ),
        )
    )
    body = _json_response(response)

    assert response.status == 201
    assert response.headers["Access-Control-Allow-Origin"] == "https://saurus-audio.com"
    assert body["song"]["title"] == "Web Alpha Song"
    assert repository.events(body["song"]["tenant_id"])[-1].actor_id == "web-user-1"


def test_gateway_rejects_missing_jwt_and_tenant_spoofing() -> None:
    """Block anonymous requests and browser-supplied tenant mismatch."""

    gateway, _, _ = _gateway(("registry.write",))

    missing = gateway.handle(ApiRequest("POST", "/v1/songs", {"Idempotency-Key": "request-missing"}, b"{}"))
    spoofed = gateway.handle(
        ApiRequest(
            "POST",
            "/v1/songs",
            {**_browser_headers("request-spoofed"), "X-Saurus-Tenant": "wrong-tenant"},
            b"{}",
        )
    )

    assert (missing.status, _json_response(missing)["error"]["message"]) == (403, "browser bearer token is required")
    assert (spoofed.status, _json_response(spoofed)["error"]["message"]) == (403, "tenant header does not match authenticated account")


def test_gateway_enforces_route_roles_before_forwarding() -> None:
    """Require route-specific registry roles at the web gateway."""

    gateway, _, _ = _gateway(("registry.read",))

    denied_write = gateway.handle(ApiRequest("POST", "/v1/songs", _browser_headers("request-denied-write"), b"{}"))
    denied_verify = gateway.handle(
        ApiRequest(
            "GET",
            "/v1/songs/song-any/verification-bundle?limit=1",
            _browser_headers("request-denied-verify", mutating=False),
        )
    )

    assert (denied_write.status, _json_response(denied_write)["error"]["message"]) == (403, "missing required role: registry.write")
    assert (denied_verify.status, _json_response(denied_verify)["error"]["message"]) == (403, "missing required role: registry.verify")


def test_gateway_handles_cors_preflight_and_unknown_routes() -> None:
    """Return browser-safe responses for preflight and unsupported routes."""

    gateway, _, _ = _gateway(("registry.write", "registry.read", "registry.verify"))

    preflight = gateway.handle(ApiRequest("OPTIONS", "/v1/songs", {}, b""))
    unknown = gateway.handle(ApiRequest("GET", "/v1/not-real", _browser_headers("request-missing-route", mutating=False), b""))

    assert preflight.status == 204
    assert preflight.headers["Access-Control-Allow-Methods"] == "GET, POST, OPTIONS"
    assert (unknown.status, _json_response(unknown)["error"]["message"]) == (404, "route is not registered for the web gateway")


def _http_api_event(body: bytes, *, method: str = "POST", path: str = "/v1/songs") -> dict[str, object]:
    """Build one API Gateway HTTP API v2 event with JWT authorizer claims."""

    return {
        "version": "2.0",
        "rawPath": path,
        "rawQueryString": "",
        "headers": {
            "authorization": "Bearer browser.jwt",
            "content-type": "application/json",
            "idempotency-key": "request-http-api",
        },
        "requestContext": {
            "http": {"method": method},
            "authorizer": {
                "jwt": {
                    "claims": {
                        "sub": "user-1",
                        "email": "artist@example.test",
                        "iss": "https://cognito-idp.us-east-2.amazonaws.com/pool",
                        "aud": "web-client",
                    }
                }
            },
        },
        "isBase64Encoded": False,
        "body": body.decode("utf-8"),
    }


def test_http_api_adapter_translates_event_and_authorizer_claims() -> None:
    """Translate API Gateway event fields into gateway request and claims."""

    event = _http_api_event(b'{"ok": true}', method="GET", path="/v1/songs/song-1")
    event["rawQueryString"] = "limit=1"

    request = api_request_from_http_api_event(event)
    claims = jwt_claims_from_http_api_event(event)

    assert request.method == "GET"
    assert request.path == "/v1/songs/song-1?limit=1"
    assert request.body == b'{"ok": true}'
    assert claims.subject == "user-1"
    assert claims.email == "artist@example.test"
    assert claims.audience == "web-client"


def test_http_api_adapter_handles_verified_claims_with_static_tenant_mapping() -> None:
    """Handle an API Gateway event after JWT authorizer verification."""

    repository = InMemoryRegistryRepository()
    service = RegistryService(repository, clock=lambda: NOW, identifier_factory=lambda: "id-1")
    tenant = service.register_tenant("Alpha Tenant", "owner", "request-tenant")
    registry_authenticator = HmacBearerAuthenticator(b"server-side-registry-secret", clock=lambda: NOW)
    registry_api = RegistryApi(service, repository, authenticator=registry_authenticator, clock=lambda: NOW)
    resolver = StaticTenantResolver.from_records(
        (
            {
                "email": "artist@example.test",
                "tenant_id": tenant.tenant_id,
                "actor_id": "web-user-1",
                "roles": ["registry.write", "registry.read"],
            },
        )
    )
    gateway = RegistryGateway(
        registry_api,
        _FakeJwtVerifier({}),
        resolver,
        registry_authenticator,
        clock=lambda: NOW,
    )
    event = _http_api_event(
        _api_body(
            title="HTTP API Song",
            source_digest="sha256:http-api",
            sample_rate=48000,
            sample_count=96000,
            fingerprint_version="web-alpha-v1",
        )
    )

    response = handle_http_api_event(event, gateway)
    body = json.loads(str(response["body"]))

    assert response["statusCode"] == 201
    assert body["song"]["title"] == "HTTP API Song"
    assert repository.events(tenant.tenant_id)[-1].actor_id == "web-user-1"


def test_http_api_adapter_rejects_missing_authorizer_context() -> None:
    """Return an auth error when API Gateway did not provide JWT claims."""

    gateway, _, _ = _gateway(("registry.write",))
    event = _http_api_event(b"{}")
    event["requestContext"] = {"http": {"method": "POST"}}

    response = handle_http_api_event(event, gateway)
    body = json.loads(str(response["body"]))

    assert response["statusCode"] == 403
    assert body["error"]["message"] == "JWT authorizer context is required"


def _runtime_env(database_path: object) -> dict[str, str]:
    """Build Lambda runtime env values with no live AWS dependency."""

    return {
        "SAURUS_REGISTRY_DATABASE_PATH": str(database_path),
        "SAURUS_API_SIGNING_SECRET": "x" * 32,
        "SAURUS_GATEWAY_TENANT_MAPPINGS_JSON": json.dumps(
            {
                "records": [
                    {
                        "email": "artist@example.test",
                        "tenant_id": "tenant-runtime",
                        "actor_id": "web-user-1",
                        "roles": ["registry.write", "registry.read"],
                    }
                ]
            },
            sort_keys=True,
        ),
    }


def test_gateway_runtime_builds_from_environment(tmp_path) -> None:
    """Construct the Lambda runtime gateway from explicit environment values."""

    gateway = build_gateway_from_env(_runtime_env(tmp_path / "registry.sqlite3"))
    event = _http_api_event(
        _api_body(
            title="Runtime Song",
            source_digest="sha256:runtime",
            sample_rate=48000,
            sample_count=96000,
            fingerprint_version="web-alpha-v1",
        )
    )

    response = handle_http_api_event(event, gateway)
    body = json.loads(str(response["body"]))

    assert response["statusCode"] == 404
    assert body["error"]["message"] == "tenant_id is not registered"


def test_lambda_handler_uses_cached_runtime_gateway(monkeypatch, tmp_path) -> None:
    """Serve API Gateway events through the cached Lambda runtime builder."""

    reset_runtime_cache()
    for name, value in _runtime_env(tmp_path / "registry.sqlite3").items():
        monkeypatch.setenv(name, value)
    event = _http_api_event(b"{}", path="/v1/songs/song-1", method="GET")
    event["headers"] = {"x-request-id": "request-runtime-read"}

    try:
        response = lambda_handler(event, object())
    finally:
        reset_runtime_cache()
    body = json.loads(str(response["body"]))

    assert response["statusCode"] == 404
    assert body["error"]["message"] == "song_id is not registered for tenant"
