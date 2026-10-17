"""Persist encode-grant issuance into the registry audit stream.

Managed KMS grants are useful only if operators can later answer who issued
which export-scoped working key and under what request. This module records the
non-secret grant projection as an append-only registry event. The event stores
only a digest of the JSON-safe grant metadata; plaintext working keys, wrapped
grant blobs, and KMS authentication tags stay out of durable audit details.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict
from datetime import datetime, timezone
import hashlib
import json
from uuid import uuid4

from .domain import RegistryEvent
from .key_custody import EncodeGrant, EncodeGrantAuditRecord, encode_grant_audit_record
from .repository import RegistryRepository

ENCODE_GRANT_ISSUED_ACTION = "encode_grant.issued"

__all__ = ["ENCODE_GRANT_ISSUED_ACTION", "encode_grant_audit_digest", "record_encode_grant_issuance"]


def record_encode_grant_issuance(
    repository: RegistryRepository,
    grant: EncodeGrant,
    *,
    event_id_factory: Callable[[], str] = lambda: str(uuid4()),
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc),
) -> RegistryEvent:
    """Append one durable grant-issuance audit event without key material."""

    audit = encode_grant_audit_record(grant)
    event = RegistryEvent(
        event_id_factory(),
        audit.tenant_id,
        audit.actor_id,
        ENCODE_GRANT_ISSUED_ACTION,
        audit.grant_id,
        audit.request_id,
        clock(),
        encode_grant_audit_digest(audit),
    )
    repository.append_event(event)
    return event


def encode_grant_audit_digest(audit: EncodeGrantAuditRecord) -> str:
    """Return a stable digest over JSON-safe grant audit metadata."""

    payload = json.dumps(asdict(audit), sort_keys=True, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()
