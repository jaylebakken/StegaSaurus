"""Record discovery pilot enrollment before baseline runs.

The controlled pilot should start from explicitly approved songs and reviewed
public sources. This module creates a local enrollment record that binds target
songs to ready source catalog entries. It does not crawl, fetch media, notify
clients, or prove source licensing; those approvals remain external launch work.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .models import DiscoveryTarget
from .sources import SourceCatalog


@dataclass(frozen=True, slots=True)
class DiscoveryPilotEnrollment:
    """Record approved targets and ready sources for one pilot baseline."""

    enrollment_id: str
    owner_id: str
    enrolled_utc: datetime
    targets: tuple[DiscoveryTarget, ...]
    source_ids: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate enrollment identity and non-empty approved scope."""

        _require_text(self.enrollment_id, "enrollment_id")
        _require_text(self.owner_id, "owner_id")
        _require_aware(self.enrolled_utc, "enrolled_utc")
        if not self.targets:
            raise ValueError("targets must not be empty")
        if not self.source_ids:
            raise ValueError("source_ids must not be empty")


def enroll_discovery_pilot(
    enrollment_id: str,
    owner_id: str,
    enrolled_utc: datetime,
    targets: tuple[DiscoveryTarget, ...],
    catalog: SourceCatalog,
) -> DiscoveryPilotEnrollment:
    """Return an enrollment over client-approved targets and ready sources."""

    ready_sources = catalog.ready_sources()
    if not ready_sources:
        raise ValueError("at least one reviewed source must be ready")
    tenant_ids = {target.tenant_id for target in targets}
    if len(tenant_ids) != 1:
        raise ValueError("pilot targets must belong to one tenant")
    return DiscoveryPilotEnrollment(
        enrollment_id,
        owner_id,
        enrolled_utc,
        targets,
        tuple(entry.source_id for entry in ready_sources),
    )


def _require_text(value: str, name: str) -> None:
    """Require one visible text value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _require_aware(value: datetime, name: str) -> None:
    """Require one timezone-aware timestamp."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
