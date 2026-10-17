"""Project registry requests into privacy-safe log records.

Hosted alpha still needs real CloudWatch validation, but the application can
define what is safe to log before deployment. This module keeps request logging
as an explicit projection: method, route, status, timing, request ID, and tenant
hint are allowed; bearer tokens, JSON bodies, retained records, carrier maps,
source audio paths, and recipient notes are not copied.
"""

from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlsplit

from .api import ApiRequest, ApiResponse
from .api.auth import header_value

__all__ = ["RegistryRequestLogRecord", "registry_request_log_record"]


@dataclass(frozen=True, slots=True)
class RegistryRequestLogRecord:
    """Hold one privacy-safe registry API request log projection."""

    method: str
    path: str
    status: int
    request_id: str
    tenant_hint: str
    elapsed_ms: float
    response_bytes: int

    def __post_init__(self) -> None:
        """Validate the projected log fields."""

        if not self.method.strip():
            raise ValueError("method must not be empty")
        if not self.path.startswith("/"):
            raise ValueError("path must start with /")
        if self.status < 100 or self.status > 599:
            raise ValueError("status must be an HTTP status code")
        if self.elapsed_ms < 0:
            raise ValueError("elapsed_ms must be non-negative")
        if self.response_bytes < 0:
            raise ValueError("response_bytes must be non-negative")


def registry_request_log_record(
    request: ApiRequest,
    response: ApiResponse,
    elapsed_ms: float,
) -> RegistryRequestLogRecord:
    """Return a request log projection without headers or body content."""

    request_id = header_value(request.headers, "Idempotency-Key") or header_value(request.headers, "X-Request-ID") or ""
    tenant_hint = header_value(request.headers, "X-Saurus-Tenant") or ""
    return RegistryRequestLogRecord(
        request.method.upper(),
        urlsplit(request.path).path,
        response.status,
        request_id,
        tenant_hint,
        elapsed_ms,
        len(response.body),
    )
