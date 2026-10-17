"""Record the pilot go/no-go gate before client notifications.

Registry and discovery each produce their own measured decisions. The pilot
still needs one written cross-functional decision that names owners, counsel
review, client review context, and whether notifications may begin. This module
is deliberately a gate record only; it does not send notifications, crawl public
sources, or reinterpret attribution evidence.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from saurus_discovery import DiscoveryPilotDecisionRecord
from saurus_registry import RegistryLaunchDecisionRecord

__all__ = ["PilotGoNoGoDecisionRecord", "PilotOwnerAssignments", "record_pilot_go_no_go"]


@dataclass(frozen=True, slots=True)
class PilotOwnerAssignments:
    """Name accountable owners for each pilot launch area."""

    registry_owner_id: str
    desktop_owner_id: str
    discovery_owner_id: str
    security_owner_id: str
    policy_owner_id: str

    def __post_init__(self) -> None:
        """Validate every owner assignment is explicit."""

        for value, name in (
            (self.registry_owner_id, "registry_owner_id"),
            (self.desktop_owner_id, "desktop_owner_id"),
            (self.discovery_owner_id, "discovery_owner_id"),
            (self.security_owner_id, "security_owner_id"),
            (self.policy_owner_id, "policy_owner_id"),
        ):
            _require_text(value, name)


@dataclass(frozen=True, slots=True)
class PilotGoNoGoDecisionRecord:
    """Bind registry, discovery, owners, and counsel to one pilot decision."""

    owners: PilotOwnerAssignments
    registry_decision: RegistryLaunchDecisionRecord
    discovery_decision: DiscoveryPilotDecisionRecord
    reviewer_id: str
    counsel_reviewer_id: str
    client_review_reference: str
    decided_utc: datetime
    summary: str
    client_notifications_allowed: bool
    go: bool
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate written go/no-go provenance and notification safety."""

        for value, name in (
            (self.reviewer_id, "reviewer_id"),
            (self.counsel_reviewer_id, "counsel_reviewer_id"),
            (self.client_review_reference, "client_review_reference"),
            (self.summary, "summary"),
        ):
            _require_text(value, name)
        _require_aware(self.decided_utc, "decided_utc")
        if self.client_notifications_allowed and not self.go:
            raise ValueError("client notifications require a go decision")


def record_pilot_go_no_go(
    owners: PilotOwnerAssignments,
    registry_decision: RegistryLaunchDecisionRecord,
    discovery_decision: DiscoveryPilotDecisionRecord,
    reviewer_id: str,
    counsel_reviewer_id: str,
    client_review_reference: str,
    decided_utc: datetime,
    summary: str,
    *,
    request_client_notifications: bool = False,
) -> PilotGoNoGoDecisionRecord:
    """Create one pilot decision and block notifications unless all gates pass."""

    blockers: list[str] = []
    if not registry_decision.decision.go:
        blockers.append("registry launch decision is not go")
    if not discovery_decision.decision.go:
        blockers.append("discovery pilot decision is not go")
    go = not blockers
    return PilotGoNoGoDecisionRecord(
        owners,
        registry_decision,
        discovery_decision,
        reviewer_id,
        counsel_reviewer_id,
        client_review_reference,
        decided_utc,
        summary,
        request_client_notifications and go,
        go,
        tuple(blockers),
    )


def _require_text(value: str, name: str) -> None:
    """Require one visible text value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _require_aware(value: datetime, name: str) -> None:
    """Require one timezone-aware timestamp."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
