"""Record the final production launch decision without replacing evidence.

Production launch needs more than a successful local pilot gate. The service
must have live KMS grants, production-shaped restore and rotation drills,
approved retention policy, monitoring, tenant-isolation probes, incident
drills, legal review, and external security review evidence. This module turns
those required gates into one explicit launch record:

1. Collect named gate evidence from the accountable owner.
2. Bind the evidence to owner, security, and policy signoff.
3. Refuse production approval if any required gate is missing or marked not
   ready.

The record does not deploy infrastructure, send notices, or prove robustness. It
prevents a launch decision from being reduced to an informal checklist memory.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

__all__ = [
    "ProductionGate",
    "ProductionGateEvidence",
    "ProductionLaunchDecisionRecord",
    "REQUIRED_PRODUCTION_GATES",
    "record_production_launch_decision",
]


class ProductionGate(str, Enum):
    """Name one required production launch gate."""

    EXTERNAL_SECURITY_REVIEW = "external_security_review"
    KMS_GRANTS_LIVE = "kms_grants_live"
    BACKUP_RESTORE_DRILL = "backup_restore_drill"
    KEY_ROTATION_DRILL = "key_rotation_drill"
    RETENTION_DELETION_POLICY = "retention_deletion_policy"
    MONITORING_ALERTING_BUDGET = "monitoring_alerting_budget"
    TENANT_ISOLATION_PROBES = "tenant_isolation_probes"
    INCIDENT_RESPONSE_DRILLS = "incident_response_drills"
    LEGAL_POLICY_REVIEW = "legal_policy_review"


REQUIRED_PRODUCTION_GATES: tuple[ProductionGate, ...] = tuple(ProductionGate)


@dataclass(frozen=True, slots=True)
class ProductionGateEvidence:
    """Record one gate's evidence reference and readiness status."""

    gate: ProductionGate
    reference: str
    ready: bool
    reviewer_id: str

    def __post_init__(self) -> None:
        """Validate one production gate evidence item."""

        if not isinstance(self.gate, ProductionGate):
            raise TypeError("gate must be a ProductionGate")
        _require_text(self.reference, "reference")
        _require_text(self.reviewer_id, "reviewer_id")


@dataclass(frozen=True, slots=True)
class ProductionLaunchDecisionRecord:
    """Bind required production gates to accountable launch signoff."""

    evidence: tuple[ProductionGateEvidence, ...]
    owner_id: str
    security_owner_id: str
    policy_owner_id: str
    decided_utc: datetime
    summary: str
    launch_approved: bool
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate final launch decision provenance."""

        _require_text(self.owner_id, "owner_id")
        _require_text(self.security_owner_id, "security_owner_id")
        _require_text(self.policy_owner_id, "policy_owner_id")
        _require_text(self.summary, "summary")
        _require_aware(self.decided_utc, "decided_utc")
        if self.launch_approved and self.blockers:
            raise ValueError("launch_approved cannot be true while blockers exist")


def record_production_launch_decision(
    evidence: tuple[ProductionGateEvidence, ...],
    owner_id: str,
    security_owner_id: str,
    policy_owner_id: str,
    decided_utc: datetime,
    summary: str,
    *,
    request_launch: bool = False,
) -> ProductionLaunchDecisionRecord:
    """Create a production launch decision and block approval unless all gates pass."""

    blockers = _blockers(evidence)
    return ProductionLaunchDecisionRecord(
        evidence,
        owner_id,
        security_owner_id,
        policy_owner_id,
        decided_utc,
        summary,
        request_launch and not blockers,
        blockers,
    )


def _blockers(evidence: tuple[ProductionGateEvidence, ...]) -> tuple[str, ...]:
    """List missing and not-ready production gates."""

    by_gate = {item.gate: item for item in evidence}
    blockers: list[str] = []
    missing = tuple(gate for gate in REQUIRED_PRODUCTION_GATES if gate not in by_gate)
    if missing:
        blockers.append("missing production gates: " + ", ".join(gate.value for gate in missing))
    not_ready = tuple(item.gate for item in evidence if not item.ready)
    if not_ready:
        blockers.append("not-ready production gates: " + ", ".join(gate.value for gate in not_ready))
    return tuple(blockers)


def _require_text(value: str, name: str) -> None:
    """Require one visible text value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _require_aware(value: datetime, name: str) -> None:
    """Require one timezone-aware timestamp."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
