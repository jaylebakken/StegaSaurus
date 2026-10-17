"""Smoke-test the deployed alpha registry workflow through HTTPS.

The endpoint health check proves the load balancer and container can answer.
This module goes further and exercises the registry API against the deployed
database using only synthetic records: create a song, reserve and finalize
exports, read retained verification material, verify bundle and lineage routes,
post a verification event, revoke history, fail an unused reservation, and
check basic authorization denials.

It deliberately does not upload source audio, use customer data, or claim
production readiness. The signing secret is read from an environment variable
and is never printed.
"""

from __future__ import annotations

import argparse
from base64 import b64encode
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import hashlib
import json
import os
from typing import Any
from urllib.error import HTTPError
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from saurus_registry.api.auth import HmacBearerAuthenticator
from saurus_registry.serialization import serialize_block_record
from stegosaurus.audio.attribution import BlockAttributionRecord
from stegosaurus.audio.attribution_core.models import AttributionRecord
from stegosaurus.audio.transport import CarrierPlan

__all__ = ["LiveRegistrySmokeResult", "main", "smoke_live_registry"]


@dataclass(frozen=True, slots=True)
class LiveRegistrySmokeResult:
    """Summarize one deployed registry workflow smoke without private payloads."""

    endpoint: str
    tenant_id: str
    actor_id: str
    song_id: str
    export_id: str
    failed_export_id: str
    verification_event_id: str
    handle_hex: str
    checks: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate the public smoke summary."""

        if not self.endpoint.startswith("https://"):
            raise ValueError("endpoint must be https")
        if not self.checks:
            raise ValueError("checks must not be empty")


def smoke_live_registry(endpoint: str, tenant_id: str, actor_id: str, signing_secret: str) -> LiveRegistrySmokeResult:
    """Exercise live registry routes with a signed synthetic smoke identity."""

    normalized = _normalize_endpoint(endpoint)
    if not tenant_id.strip() or not actor_id.strip():
        raise ValueError("tenant_id and actor_id must not be empty")
    if len(signing_secret.encode("utf-8")) < 32:
        raise ValueError("signing_secret must contain at least 32 bytes")
    started = datetime.now(timezone.utc)
    suffix = started.strftime("%Y%m%d%H%M%S")
    token = _token(signing_secret, tenant_id, actor_id, ("registry.write", "registry.read", "registry.verify"))
    read_only = _token(signing_secret, tenant_id, actor_id + "-readonly", ("registry.read",))
    other_tenant = _token(signing_secret, tenant_id + "-other", actor_id, ("registry.read",))
    checks: list[str] = []

    _expect_error(normalized, "GET", "/v1/songs/not-registered", {"X-Request-ID": "live-smoke-anonymous"}, None, 403)
    checks.append("anonymous request denied")
    _expect_error(normalized, "POST", "/v1/songs", _headers(read_only, "readonly-create"), _song_body(suffix), 403)
    checks.append("role-limited token denied")

    song = _request(normalized, "POST", "/v1/songs", _headers(token, "song-" + suffix), _song_body(suffix), 201)["song"]
    song_replay = _request(normalized, "POST", "/v1/songs", _headers(token, "song-" + suffix), _song_body(suffix), 201)["song"]
    if song_replay["song_id"] != song["song_id"]:
        raise RuntimeError("idempotent song replay returned a different song")
    checks.append("song create and idempotent replay")

    handle = hashlib.sha256(("active-" + suffix).encode("ascii")).digest()[:4]
    export = _request(
        normalized,
        "POST",
        f"/v1/songs/{song['song_id']}/exports:reserve",
        _headers(token, "reserve-" + suffix),
        {"recipient_label": "synthetic live smoke", "requested_handle_hex": handle.hex()},
        201,
    )["export"]
    checks.append("export reserve")

    payload = serialize_block_record(_record(handle))
    finalized = _request(
        normalized,
        "POST",
        f"/v1/exports/{export['export_id']}:finalize",
        _headers(token, "finalize-" + suffix),
        {"payload_b64": b64encode(payload).decode("ascii")},
        200,
    )["export"]
    if finalized["state"] != "active":
        raise RuntimeError("finalized export is not active")
    checks.append("export finalize")

    _request(normalized, "GET", f"/v1/songs/{song['song_id']}", _headers(token, "get-song", mutating=False), None, 200)
    _request(normalized, "GET", f"/v1/exports/{export['export_id']}", _headers(token, "get-export", mutating=False), None, 200)
    record = _request(normalized, "GET", f"/v1/exports/{export['export_id']}/verification-record", _headers(token, "record", mutating=False), None, 200)["record"]
    if record["payload_digest"] != hashlib.sha256(payload).hexdigest():
        raise RuntimeError("verification record digest did not match finalized payload")
    checks.append("song/export/record read")

    bundle = _request(normalized, "GET", f"/v1/songs/{song['song_id']}/verification-bundle?limit=10", _headers(token, "bundle", mutating=False), None, 200)
    if bundle["returned_count"] != 1:
        raise RuntimeError("verification bundle did not include exactly one active export")
    lineage = _request(normalized, "GET", f"/v1/exports/{export['export_id']}/lineage", _headers(token, "lineage", mutating=False), None, 200)
    if len(lineage["lineage"]) != 1:
        raise RuntimeError("lineage did not return the root export")
    checks.append("verification bundle and lineage")

    event_id = str(
        _request(
            normalized,
            "POST",
            f"/v1/exports/{export['export_id']}:verification-result",
            _headers(token, "verification-" + suffix),
            {"accepted": True, "stage": "live-smoke", "reason": "synthetic check", "block_votes": 1, "block_count": 1, "pooled_rs_cost": 0},
            202,
        )["event_id"]
    )
    checks.append("verification event")

    revoked = _request(normalized, "POST", f"/v1/exports/{export['export_id']}:revoke", _headers(token, "revoke-" + suffix), {}, 200)["export"]
    if revoked["state"] != "revoked":
        raise RuntimeError("revoked export is not revoked")
    _request(normalized, "GET", f"/v1/exports/{export['export_id']}/verification-record", _headers(token, "record-after-revoke", mutating=False), None, 200)
    checks.append("revoke keeps retained verification available")

    failed_export_id = _reserve_and_fail(normalized, token, str(song["song_id"]), suffix)
    checks.append("reserve and fail unusable export")
    _expect_error(normalized, "GET", f"/v1/exports/{export['export_id']}", _headers(other_tenant, "cross-tenant", mutating=False), None, 404)
    checks.append("cross-tenant selected export denied")

    return LiveRegistrySmokeResult(normalized.rstrip("/"), tenant_id, actor_id, str(song["song_id"]), str(export["export_id"]), failed_export_id, event_id, handle.hex(), tuple(checks))


def main(argv: list[str] | None = None) -> int:
    """Run the deployed registry workflow smoke from the command line."""

    parser = argparse.ArgumentParser(description="Smoke-test the live Saurus alpha registry API workflow.")
    parser.add_argument("endpoint")
    parser.add_argument("--tenant-id", default="tenant-live-smoke-20261014")
    parser.add_argument("--actor-id", default="alpha-live-smoke")
    parser.add_argument("--signing-secret-env", default="SAURUS_API_SIGNING_SECRET")
    args = parser.parse_args(argv)
    secret = os.environ.get(args.signing_secret_env)
    if secret is None:
        raise ValueError(f"{args.signing_secret_env} is not set")
    result = smoke_live_registry(args.endpoint, args.tenant_id, args.actor_id, secret)
    print(json.dumps(asdict(result), indent=2, sort_keys=True))
    return 0


def _normalize_endpoint(endpoint: str) -> str:
    """Validate and normalize one endpoint root URL."""

    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("endpoint must be an absolute https URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("endpoint must not contain credentials, query, or fragment")
    return endpoint.rstrip("/") + "/"


def _token(secret: str, tenant_id: str, actor_id: str, roles: tuple[str, ...]) -> str:
    """Issue one short-lived smoke token."""

    expires = datetime.now(timezone.utc) + timedelta(hours=1)
    return HmacBearerAuthenticator(secret.encode("utf-8")).issue_token(tenant_id, actor_id, roles, expires)


def _headers(token: str, request_id: str, *, mutating: bool = True) -> dict[str, str]:
    """Build authenticated headers for one smoke request."""

    headers = {"Authorization": token}
    headers["Idempotency-Key" if mutating else "X-Request-ID"] = "live-smoke-" + request_id
    return headers


def _song_body(suffix: str) -> dict[str, object]:
    """Build one synthetic song registration payload."""

    return {
        "title": "live alpha smoke " + suffix,
        "source_digest": "sha256:" + hashlib.sha256(("source-" + suffix).encode("ascii")).hexdigest(),
        "sample_rate": 16000,
        "sample_count": 480000,
        "fingerprint_version": "live-alpha-smoke-v1",
    }


def _record(handle: bytes) -> BlockAttributionRecord:
    """Build a compact structurally valid private block record."""

    plan = CarrierPlan(4, 6, (0, 1))
    private = AttributionRecord(handle, plan, ((0, 1), (2, 3), (4, 5), (6, 7)), 16000)
    return BlockAttributionRecord(handle, 480000, 16000, (private,), 480000)


def _reserve_and_fail(endpoint: str, token: str, song_id: str, suffix: str) -> str:
    """Reserve and fail one export to check failure state handling."""

    handle = hashlib.sha256(("failed-" + suffix).encode("ascii")).digest()[:4]
    export = _request(
        endpoint,
        "POST",
        f"/v1/songs/{song_id}/exports:reserve",
        _headers(token, "fail-reserve-" + suffix),
        {"recipient_label": "synthetic failed smoke", "requested_handle_hex": handle.hex()},
        201,
    )["export"]
    _request(endpoint, "POST", f"/v1/exports/{export['export_id']}:fail", _headers(token, "fail-" + suffix), {"reason": "synthetic failure lane"}, 200)
    _expect_error(endpoint, "GET", f"/v1/exports/{export['export_id']}/verification-record", _headers(token, "failed-record", mutating=False), None, 400)
    return str(export["export_id"])


def _expect_error(endpoint: str, method: str, path: str, headers: dict[str, str], body: dict[str, object] | None, expected_status: int) -> None:
    """Require one request to fail with an expected HTTP status."""

    try:
        _request(endpoint, method, path, headers, body, expected_status)
    except RuntimeError as error:
        if f"expected HTTP {expected_status}" in str(error):
            raise


def _request(endpoint: str, method: str, path: str, headers: dict[str, str], body: dict[str, object] | None, expected_status: int) -> dict[str, Any]:
    """Send one JSON request and return its decoded response."""

    payload = b"" if body is None else json.dumps(body, sort_keys=True).encode("utf-8")
    request = Request(urljoin(endpoint, path.lstrip("/")), data=payload if method != "GET" else None, method=method, headers={**headers, "Content-Type": "application/json", "User-Agent": "saurus-live-registry-smoke/1"})
    try:
        with urlopen(request, timeout=15) as response:
            status = int(response.status)
            raw = response.read(65536)
    except HTTPError as error:
        status = int(error.code)
        raw = error.read(65536)
    document = json.loads(raw.decode("utf-8"))
    if status != expected_status:
        raise RuntimeError(f"expected HTTP {expected_status}, got {status}: {document}")
    return document


if __name__ == "__main__":
    raise SystemExit(main())
