"""Rehearse discovery incident response steps for the pilot.

The discovery pilot needs an incident drill before launch, but a full
production incident program still requires owners, paging, counsel review, and
runbooks. This module records a minimal local drill: detect, contain, restore,
and review. It can disable a connector through the control plane to prove the
containment path works without live crawling.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

from .controls import ConnectorControlPlane


class IncidentStep(str, Enum):
    """Name the required discovery incident rehearsal steps."""

    DETECTED = "detected"
    CONTAINED = "contained"
    RESTORED = "restored"
    REVIEWED = "reviewed"


@dataclass(frozen=True, slots=True)
class IncidentAction:
    """Record one discovery incident drill action."""

    incident_id: str
    step: IncidentStep
    actor_id: str
    reason: str
    occurred_utc: datetime

    def __post_init__(self) -> None:
        """Validate incident action identity and timestamp."""

        for value, name in ((self.incident_id, "incident_id"), (self.actor_id, "actor_id"), (self.reason, "reason")):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        if self.occurred_utc.tzinfo is None or self.occurred_utc.utcoffset() is None:
            raise ValueError("occurred_utc must be timezone-aware")


@dataclass(frozen=True, slots=True)
class IncidentDrillResult:
    """Summarize whether an incident drill covered required steps."""

    incident_id: str
    complete: bool
    missing_steps: tuple[IncidentStep, ...]


class DiscoveryIncidentDrill:
    """Record and evaluate one discovery incident response rehearsal."""

    def __init__(self, incident_id: str, control_plane: ConnectorControlPlane) -> None:
        """Initialize one incident drill."""

        if not isinstance(incident_id, str) or not incident_id.strip():
            raise ValueError("incident_id must not be empty")
        self._incident_id = incident_id.strip()
        self._control_plane = control_plane
        self._actions: list[IncidentAction] = []

    def record(self, step: IncidentStep, actor_id: str, reason: str, occurred_utc: datetime) -> IncidentAction:
        """Record one drill step."""

        action = IncidentAction(self._incident_id, step, actor_id, reason, occurred_utc)
        self._actions.append(action)
        return action

    def contain_connector(self, source_id: str, actor_id: str, reason: str, occurred_utc: datetime) -> IncidentAction:
        """Disable one connector and record the containment step."""

        self._control_plane.disable(source_id, reason)
        return self.record(IncidentStep.CONTAINED, actor_id, reason, occurred_utc)

    def result(self) -> IncidentDrillResult:
        """Return whether all required drill steps were recorded."""

        observed = {action.step for action in self._actions}
        required = (IncidentStep.DETECTED, IncidentStep.CONTAINED, IncidentStep.RESTORED, IncidentStep.REVIEWED)
        missing = tuple(step for step in required if step not in observed)
        return IncidentDrillResult(self._incident_id, not missing, missing)

    def actions(self) -> tuple[IncidentAction, ...]:
        """Return the recorded incident drill actions."""

        return tuple(self._actions)
