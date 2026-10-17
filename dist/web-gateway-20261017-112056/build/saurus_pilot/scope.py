"""Record controlled pilot track, source, and threshold selection.

The pilot should not begin with informal song names or vague source choices.
Before baseline runs, Saurus needs a written scope packet that names licensed or
owned tracks, approved public sources, and numeric discovery thresholds. This
module records that packet:

1. Each track needs an ownership or licensing reference.
2. Each public source needs a permitted-access reference and policy reviewer.
3. Discovery thresholds must be attached before the scope can be marked ready.

The record does not prove copyright ownership, crawl public sources, or approve
client notifications. It keeps the pilot setup evidence explicit.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from saurus_discovery import DiscoveryPilotThresholds

__all__ = ["PilotScopeRecord", "PilotSourceSelection", "PilotTrackSelection", "record_pilot_scope"]


@dataclass(frozen=True, slots=True)
class PilotTrackSelection:
    """Record one pilot track and its ownership or licensing reference."""

    tenant_id: str
    song_id: str
    title: str
    ownership_reference: str

    def __post_init__(self) -> None:
        """Validate pilot track identity and licensing evidence."""

        for value, name in (
            (self.tenant_id, "tenant_id"),
            (self.song_id, "song_id"),
            (self.title, "title"),
            (self.ownership_reference, "ownership_reference"),
        ):
            _require_text(value, name)


@dataclass(frozen=True, slots=True)
class PilotSourceSelection:
    """Record one approved public source for a controlled pilot."""

    source_id: str
    access_reference: str
    policy_reviewer_id: str

    def __post_init__(self) -> None:
        """Validate public source approval evidence."""

        for value, name in (
            (self.source_id, "source_id"),
            (self.access_reference, "access_reference"),
            (self.policy_reviewer_id, "policy_reviewer_id"),
        ):
            _require_text(value, name)


@dataclass(frozen=True, slots=True)
class PilotScopeRecord:
    """Bind tracks, sources, and thresholds into one pilot scope packet."""

    scope_id: str
    owner_id: str
    reviewed_utc: datetime
    tracks: tuple[PilotTrackSelection, ...]
    sources: tuple[PilotSourceSelection, ...]
    thresholds: DiscoveryPilotThresholds | None
    ready: bool
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate scope provenance and readiness consistency."""

        _require_text(self.scope_id, "scope_id")
        _require_text(self.owner_id, "owner_id")
        _require_aware(self.reviewed_utc, "reviewed_utc")
        if self.ready and self.blockers:
            raise ValueError("ready cannot be true while blockers exist")


def record_pilot_scope(
    scope_id: str,
    owner_id: str,
    reviewed_utc: datetime,
    tracks: tuple[PilotTrackSelection, ...],
    sources: tuple[PilotSourceSelection, ...],
    thresholds: DiscoveryPilotThresholds | None,
) -> PilotScopeRecord:
    """Create a pilot scope packet and compute setup blockers."""

    blockers = _blockers(tracks, sources, thresholds)
    return PilotScopeRecord(scope_id, owner_id, reviewed_utc, tracks, sources, thresholds, not blockers, blockers)


def _blockers(
    tracks: tuple[PilotTrackSelection, ...],
    sources: tuple[PilotSourceSelection, ...],
    thresholds: DiscoveryPilotThresholds | None,
) -> tuple[str, ...]:
    """List missing pilot setup evidence."""

    blockers: list[str] = []
    if not tracks:
        blockers.append("pilot tracks are missing")
    if not sources:
        blockers.append("approved public sources are missing")
    if thresholds is None:
        blockers.append("numeric pilot thresholds are missing")
    tenant_ids = {track.tenant_id for track in tracks}
    if len(tenant_ids) > 1:
        blockers.append("pilot tracks must belong to one tenant")
    return tuple(blockers)


def _require_text(value: str, name: str) -> None:
    """Require one visible text value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _require_aware(value: datetime, name: str) -> None:
    """Require one timezone-aware timestamp."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
