"""Canonicalize and evaluate public URLs before any crawler fetch.

This policy is intentionally conservative. It accepts only reviewed schemes and
domains, strips fragments, normalizes default ports, and rejects loopback,
private, link-local, multicast, and otherwise special IP destinations to reduce
SSRF exposure before any network request exists.
"""

from __future__ import annotations

from dataclasses import dataclass
import ipaddress
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .models import ConnectorPolicy


@dataclass(frozen=True, slots=True)
class FetchDecision:
    """Explain whether one URL is permitted for bounded public fetching."""

    allowed: bool
    canonical_url: str
    reason: str


def canonicalize_url(raw_url: str) -> str:
    """Normalize a public URL for deduplication and policy checks."""

    parts = urlsplit(raw_url.strip())
    if not parts.scheme or not parts.hostname:
        raise ValueError("URL must include a scheme and host")
    scheme = parts.scheme.lower()
    hostname = parts.hostname.lower().rstrip(".")
    port = "" if parts.port in {None, 80, 443} else f":{parts.port}"
    path = parts.path or "/"
    query = urlencode(sorted(parse_qsl(parts.query, keep_blank_values=True)))
    return urlunsplit((scheme, f"{hostname}{port}", path, query, ""))


def dedupe_urls(raw_urls: tuple[str, ...]) -> tuple[str, ...]:
    """Return stable canonical URLs without duplicates."""

    seen: set[str] = set()
    output: list[str] = []
    for raw_url in raw_urls:
        canonical = canonicalize_url(raw_url)
        if canonical not in seen:
            seen.add(canonical)
            output.append(canonical)
    return tuple(output)


def evaluate_fetch_url(raw_url: str, policy: ConnectorPolicy) -> FetchDecision:
    """Evaluate one URL against connector allowlists and SSRF guardrails."""

    try:
        canonical = canonicalize_url(raw_url)
    except ValueError as error:
        return FetchDecision(False, "", str(error))
    parts = urlsplit(canonical)
    if parts.scheme not in policy.allowed_schemes:
        return FetchDecision(False, canonical, "scheme is not approved for connector")
    host = parts.hostname or ""
    if not _domain_allowed(host, policy.allowed_domains):
        return FetchDecision(False, canonical, "host is not approved for connector")
    if _special_host(host):
        return FetchDecision(False, canonical, "host resolves to a blocked address class")
    return FetchDecision(True, canonical, "allowed")


def _domain_allowed(host: str, allowed_domains: tuple[str, ...]) -> bool:
    """Return whether host matches a connector domain rule."""

    return any(host == domain.lower() or host.endswith(f".{domain.lower()}") for domain in allowed_domains)


def _special_host(host: str) -> bool:
    """Reject localhost names and special-purpose IP literals."""

    if host in {"localhost", "localhost.localdomain"}:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return False
    return any(
        (
            address.is_private,
            address.is_loopback,
            address.is_link_local,
            address.is_multicast,
            address.is_reserved,
            address.is_unspecified,
        )
    )
