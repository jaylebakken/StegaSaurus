"""Replay completed mutating registry API requests safely.

The desktop may lose its network connection after the registry completes a
reserve or finalize operation. These helpers compare a stable request digest
before replaying the original response, so retries do not create duplicate
exports or conflicting state transitions.
"""

from __future__ import annotations

from collections.abc import Callable, Iterator
from contextlib import contextmanager
from datetime import datetime
import hashlib
from threading import Lock
from urllib.parse import urlsplit

from ..domain import IdempotencyRecord
from ..repository import RegistryRepository
from .auth import RequestContext
from .contracts import ApiRequest, ApiResponse


class IdempotencyConflictError(RuntimeError):
    """Report reuse of an idempotency key for different request content."""


class InFlightIdempotencyGuard:
    """Reject duplicate mutating idempotency keys while work is still running."""

    def __init__(self) -> None:
        """Initialize an empty in-process request guard."""

        self._lock = Lock()
        self._requests: dict[tuple[str, str], tuple[str, str, str]] = {}

    @contextmanager
    def track(self, context: RequestContext, request: ApiRequest) -> Iterator[None]:
        """Hold one in-flight request identity until dispatch finishes."""

        key = (context.tenant_id, context.request_id)
        identity = _identity(request)
        with self._lock:
            existing = self._requests.get(key)
            if existing is not None:
                if existing == identity:
                    raise IdempotencyConflictError("idempotency key is already in flight")
                raise IdempotencyConflictError("idempotency key was reused for a different request")
            self._requests[key] = identity
        try:
            yield
        finally:
            with self._lock:
                if self._requests.get(key) == identity:
                    del self._requests[key]


def replay_response(
    repository: RegistryRepository,
    context: RequestContext,
    request: ApiRequest,
) -> ApiResponse | None:
    """Return a stored response when a matching mutating request is retried."""

    record = repository.idempotency_record(context.tenant_id, context.request_id)
    if record is None:
        return None
    if (record.method, record.path, record.request_digest) != _identity(request):
        raise IdempotencyConflictError("idempotency key was reused for a different request")
    return ApiResponse(record.response_status, {"Content-Type": "application/json"}, record.response_body)


def store_response(
    repository: RegistryRepository,
    context: RequestContext,
    request: ApiRequest,
    response: ApiResponse,
    clock: Callable[[], datetime],
) -> None:
    """Store one successful mutating response for later replay."""

    if response.status >= 400:
        return
    method, path, request_digest = _identity(request)
    repository.store_idempotency_record(
        IdempotencyRecord(
            context.tenant_id,
            context.request_id,
            method,
            path,
            request_digest,
            response.status,
            response.body,
            clock(),
        )
    )


def _identity(request: ApiRequest) -> tuple[str, str, str]:
    """Return the stable idempotency identity for one API request."""

    path = urlsplit(request.path).path
    digest = hashlib.sha256(request.body).hexdigest()
    return request.method.upper(), path, digest
