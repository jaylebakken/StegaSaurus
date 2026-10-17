"""Expose the versioned Saurus registry API boundary.

The API layer is intentionally thin: it translates HTTP-shaped requests into
registry application calls, serializes domain records, validates optional signed
bearer credentials, records successful mutating responses for idempotent retry,
and emits structured errors. Deployment credential issuance and encryption
remain separate Phase 1 checklist items.
"""

from __future__ import annotations

from .auth import HmacBearerAuthenticator, RegistryAuthenticator, RequestContext
from .contracts import ApiRequest, ApiResponse
from .http_server import registry_handler
from .idempotency import IdempotencyConflictError
from .router import RegistryApi

__all__ = [
    "ApiRequest",
    "ApiResponse",
    "HmacBearerAuthenticator",
    "IdempotencyConflictError",
    "RegistryApi",
    "RegistryAuthenticator",
    "RequestContext",
    "registry_handler",
]
