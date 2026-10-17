"""Gate registry deletion requests behind approved retention policy.

Retention review can identify records that deserve human review, but production
deletion must not happen until counsel and an accountable owner approve a policy.
This module records that approval boundary as code. It appends only a digest-only
audit event for an approved deletion request; it does not delete retained
records, redact payloads, or weaken append-only registry history.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import datetime
from enum import Enum
import hashlib
import json
from uuid import uuid4

from .domain import RegistryEvent
from .repository import RegistryRepository
from .retention import RegistryRetentionDecision, RetentionAction

REGISTRY_DELETION_REQUESTED_ACTION = "retention.deletion_requested"

__all__ = [
    "REGISTRY_DELETION_REQUESTED_ACTION",
    "DeletionApprovalStatus",
    "RegistryDeletionApproval",
    "record_registry_deletion_request",
]


class DeletionApprovalStatus(str, Enum):
    """Name whether deletion policy has approval to run."""

    DRAFT = "draft"
    COUNSEL_APPROVED = "counsel approved"


@dataclass(frozen=True, slots=True)
class RegistryDeletionApproval:
    """Record the policy approval required before deletion tooling runs."""

    policy_id: str
    owner_id: str
    counsel_reviewer_id: str
    approved_utc: datetime
    status: DeletionApprovalStatus
    summary: str

    def __post_init__(self) -> None:
        """Validate deletion approval provenance."""

        for value, name in (
            (self.policy_id, "policy_id"),
            (self.owner_id, "owner_id"),
            (self.counsel_reviewer_id, "counsel_reviewer_id"),
            (self.summary, "summary"),
        ):
            _require_text(value, name)
        _require_aware(self.approved_utc, "approved_utc")


def record_registry_deletion_request(
    repository: RegistryRepository,
    tenant_id: str,
    decision: RegistryRetentionDecision,
    approval: RegistryDeletionApproval,
    actor_id: str,
    request_id: str,
    reason: str,
    occurred_utc: datetime,
    *,
    event_id_factory: Callable[[], str] = lambda: str(uuid4()),
) -> RegistryEvent:
    """Append an approved deletion-request audit event without deleting data."""

    _require_text(tenant_id, "tenant_id")
    _require_text(actor_id, "actor_id")
    _require_text(request_id, "request_id")
    _require_text(reason, "reason")
    _require_aware(occurred_utc, "occurred_utc")
    if approval.status is not DeletionApprovalStatus.COUNSEL_APPROVED:
        raise ValueError("deletion policy is not counsel approved")
    if decision.action is not RetentionAction.REVIEW:
        raise ValueError("retention decision is not eligible for deletion review")
    event = RegistryEvent(
        event_id_factory(),
        tenant_id,
        actor_id,
        REGISTRY_DELETION_REQUESTED_ACTION,
        decision.export_id,
        request_id,
        occurred_utc,
        _detail_digest(decision, approval, reason),
    )
    repository.append_event(event)
    return event


def _detail_digest(decision: RegistryRetentionDecision, approval: RegistryDeletionApproval, reason: str) -> str:
    """Return a stable digest of non-secret deletion request details."""

    document = {
        "approval": asdict(approval),
        "decision": asdict(decision),
        "reason": reason,
    }
    payload = json.dumps(document, sort_keys=True, separators=(",", ":"), default=str).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def _require_text(value: str, name: str) -> None:
    """Require one visible text value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _require_aware(value: datetime, name: str) -> None:
    """Require one timezone-aware timestamp."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
