"""Record concise verification events without receiving audio.

Desktop verification should keep audio local by default. This helper validates
the selected export, records decision diagnostics as a digest-only registry
event, and returns the event identity for a client receipt or log.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
import hashlib
import json
from typing import Any
from uuid import uuid4

from ..application import RegistryService
from ..domain import RegistryEvent
from ..repository import RegistryRepository
from .auth import RequestContext


def record_verification_event(
    service: RegistryService,
    repository: RegistryRepository,
    context: RequestContext,
    export_id: str,
    body: dict[str, Any],
    clock: Callable[[], datetime],
) -> RegistryEvent:
    """Append one digest-only verification event for a tenant export."""

    service.resolve_export(context.tenant_id, export_id)
    detail = {
        "accepted": bool(body["accepted"]),
        "stage": str(body["stage"]),
        "reason": str(body["reason"]),
        "block_votes": int(body["block_votes"]),
        "block_count": int(body["block_count"]),
        "pooled_rs_cost": int(body["pooled_rs_cost"]),
    }
    canonical = json.dumps(detail, sort_keys=True, separators=(",", ":")).encode("utf-8")
    event = RegistryEvent(
        str(uuid4()),
        context.tenant_id,
        context.actor_id,
        "verification.reported",
        export_id,
        context.request_id,
        clock(),
        hashlib.sha256(canonical).hexdigest(),
    )
    repository.append_event(event)
    return event
