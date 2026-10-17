"""Record cross-system incident response drills for production readiness.

Saurus has separate runbooks for registry credential exposure and mistaken
discovery alerts. A production launch gate needs evidence that both kinds of
incident can move through the same basic loop:

1. Contain the risky workflow.
2. Assess affected systems and evidence.
3. Recover or correct state without deleting audit history.
4. Communicate with approved, neutral language.
5. Review the drill with an owner and second reviewer.

This module records drill evidence only. It does not rotate keys, disable
connectors, send notices, or prove the production paging program is staffed.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from enum import Enum

__all__ = [
    "IncidentDrillPhase",
    "ProductionIncidentDrillRecord",
    "ProductionIncidentScenario",
    "REQUIRED_INCIDENT_DRILL_PHASES",
    "REQUIRED_PRODUCTION_INCIDENT_SCENARIOS",
    "record_production_incident_drill",
]


class ProductionIncidentScenario(str, Enum):
    """Name one required production incident drill scenario."""

    REGISTRY_CREDENTIAL_EXPOSURE = "registry_credential_exposure"
    MISTAKEN_DISCOVERY_ALERT = "mistaken_discovery_alert"


class IncidentDrillPhase(str, Enum):
    """Name one required incident drill phase."""

    CONTAIN = "contain"
    ASSESS = "assess"
    RECOVER = "recover"
    COMMUNICATE = "communicate"
    REVIEW = "review"


REQUIRED_PRODUCTION_INCIDENT_SCENARIOS: tuple[ProductionIncidentScenario, ...] = tuple(ProductionIncidentScenario)
REQUIRED_INCIDENT_DRILL_PHASES: tuple[IncidentDrillPhase, ...] = tuple(IncidentDrillPhase)


@dataclass(frozen=True, slots=True)
class ProductionIncidentDrillRecord:
    """Summarize one incident response drill for release gates."""

    scenario: ProductionIncidentScenario
    drill_id: str
    runbook_reference: str
    owner_id: str
    reviewer_id: str
    drilled_utc: datetime
    phases_completed: tuple[IncidentDrillPhase, ...]
    summary: str
    complete: bool
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate drill provenance and completion consistency."""

        if not isinstance(self.scenario, ProductionIncidentScenario):
            raise TypeError("scenario must be a ProductionIncidentScenario")
        for value, name in (
            (self.drill_id, "drill_id"),
            (self.runbook_reference, "runbook_reference"),
            (self.owner_id, "owner_id"),
            (self.reviewer_id, "reviewer_id"),
            (self.summary, "summary"),
        ):
            _require_text(value, name)
        _require_aware(self.drilled_utc, "drilled_utc")
        for phase in self.phases_completed:
            if not isinstance(phase, IncidentDrillPhase):
                raise TypeError("phases_completed must contain IncidentDrillPhase values")
        if self.complete and self.blockers:
            raise ValueError("complete cannot be true while blockers exist")


def record_production_incident_drill(
    scenario: ProductionIncidentScenario,
    drill_id: str,
    runbook_reference: str,
    owner_id: str,
    reviewer_id: str,
    drilled_utc: datetime,
    phases_completed: tuple[IncidentDrillPhase, ...],
    summary: str,
) -> ProductionIncidentDrillRecord:
    """Create one incident drill record and mark missing phases as blockers."""

    unique_phases = tuple(dict.fromkeys(phases_completed))
    missing = tuple(phase for phase in REQUIRED_INCIDENT_DRILL_PHASES if phase not in unique_phases)
    blockers = ("missing incident drill phases: " + ", ".join(phase.value for phase in missing),) if missing else ()
    return ProductionIncidentDrillRecord(
        scenario,
        drill_id,
        runbook_reference,
        owner_id,
        reviewer_id,
        drilled_utc,
        unique_phases,
        summary,
        not blockers,
        blockers,
    )


def _require_text(value: str, name: str) -> None:
    """Require one visible text value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _require_aware(value: datetime, name: str) -> None:
    """Require one timezone-aware timestamp."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
