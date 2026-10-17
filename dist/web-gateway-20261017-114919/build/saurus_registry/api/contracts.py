"""Define small HTTP-shaped records for the registry API.

Tests and the stdlib HTTP adapter use these immutable records so route behavior
can be verified without binding to a web framework. Bodies are raw bytes at the
edge; JSON validation and structured errors live in the router.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ApiRequest:
    """Represent one versioned registry API request."""

    method: str
    path: str
    headers: dict[str, str]
    body: bytes = b""


@dataclass(frozen=True, slots=True)
class ApiResponse:
    """Represent one registry API response."""

    status: int
    headers: dict[str, str]
    body: bytes
