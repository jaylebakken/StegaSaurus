"""Smoke-test a deployed Saurus alpha registry endpoint.

This helper is intentionally small and safe to run from a release checklist.
It checks the public HTTPS edge only: the `/health` route must answer with the
expected JSON shape, and the response must not include obvious secret material.
It does not create songs, issue grants, mutate the registry, or prove AWS IAM,
KMS, CloudTrail, alarms, or PostgreSQL behavior.
"""

from __future__ import annotations

import argparse
from collections.abc import Callable
from dataclasses import asdict, dataclass
import json
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

__all__ = ["AlphaEndpointSmokeResult", "main", "smoke_alpha_endpoint"]

_FORBIDDEN_RESPONSE_MARKERS = ("Bearer ", "password", "secret", "token", "payload_b64")


@dataclass(frozen=True, slots=True)
class AlphaEndpointSmokeResult:
    """Summarize one deployed alpha endpoint smoke check."""

    endpoint: str
    health_url: str
    status: int
    body_bytes: int
    ok: bool

    def __post_init__(self) -> None:
        """Validate smoke result fields."""

        if not self.endpoint.startswith("https://"):
            raise ValueError("endpoint must be https")
        if self.status < 100 or self.status > 599:
            raise ValueError("status must be an HTTP status code")
        if self.body_bytes < 0:
            raise ValueError("body_bytes must be non-negative")


def smoke_alpha_endpoint(
    endpoint: str,
    *,
    timeout_seconds: float = 10.0,
    fetch: Callable[[str, float], tuple[int, bytes]] | None = None,
) -> AlphaEndpointSmokeResult:
    """Check the deployed registry health route and response privacy."""

    normalized = _normalize_endpoint(endpoint)
    health_url = urljoin(normalized, "/health")
    status, body = (fetch or _fetch)(health_url, timeout_seconds)
    text = body.decode("utf-8")
    if status != 200:
        raise ValueError(f"health check returned HTTP {status}")
    try:
        document = json.loads(text)
    except json.JSONDecodeError as error:
        raise ValueError("health check did not return JSON") from error
    if document != {"status": "ok"}:
        raise ValueError("health check JSON shape is not recognized")
    lowered = text.lower()
    for marker in _FORBIDDEN_RESPONSE_MARKERS:
        if marker.lower() in lowered:
            raise ValueError(f"health response included forbidden marker: {marker}")
    return AlphaEndpointSmokeResult(normalized.rstrip("/"), health_url, status, len(body), True)


def main(argv: list[str] | None = None) -> int:
    """Run the deployed alpha endpoint smoke check from the command line."""

    parser = argparse.ArgumentParser(description="Smoke-test a deployed Saurus alpha registry endpoint.")
    parser.add_argument("endpoint", help="HTTPS endpoint root, for example https://registry-alpha.example.test")
    parser.add_argument("--timeout-seconds", type=float, default=10.0)
    args = parser.parse_args(argv)
    print(json.dumps(asdict(smoke_alpha_endpoint(args.endpoint, timeout_seconds=args.timeout_seconds)), indent=2, sort_keys=True))
    return 0


def _normalize_endpoint(endpoint: str) -> str:
    """Validate and normalize one endpoint root URL."""

    parsed = urlparse(endpoint)
    if parsed.scheme != "https" or not parsed.netloc:
        raise ValueError("endpoint must be an absolute https URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ValueError("endpoint must not contain credentials, query, or fragment")
    return endpoint.rstrip("/") + "/"


def _fetch(url: str, timeout_seconds: float) -> tuple[int, bytes]:
    """Fetch one URL with a small explicit user agent."""

    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    request = Request(url, headers={"User-Agent": "saurus-alpha-smoke/1"})
    with urlopen(request, timeout=timeout_seconds) as response:
        return int(response.status), response.read(4096)


if __name__ == "__main__":
    raise SystemExit(main())
