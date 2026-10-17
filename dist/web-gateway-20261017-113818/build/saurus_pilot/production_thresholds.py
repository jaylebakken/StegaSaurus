"""Record production registry launch thresholds derived from pilot data.

Local alpha thresholds are intentionally permissive. Production launch needs a
separate threshold packet that cites pilot measurements and records the concrete
registry launch-gate thresholds to use. This module records that packet without
inventing pilot data or approving production launch.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from saurus_registry import RegistryLaunchThresholds

__all__ = ["ProductionThresholdRecord", "record_production_thresholds"]


@dataclass(frozen=True, slots=True)
class ProductionThresholdRecord:
    """Bind pilot evidence to production registry launch-gate thresholds."""

    pilot_data_reference: str
    thresholds: RegistryLaunchThresholds
    reviewer_id: str
    reviewed_utc: datetime
    summary: str
    ready: bool
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate production threshold provenance and consistency."""

        for value, name in (
            (self.pilot_data_reference, "pilot_data_reference"),
            (self.reviewer_id, "reviewer_id"),
            (self.summary, "summary"),
        ):
            _require_text(value, name)
        _require_aware(self.reviewed_utc, "reviewed_utc")
        if self.ready and self.blockers:
            raise ValueError("ready cannot be true while blockers exist")


def record_production_thresholds(
    pilot_data_reference: str,
    thresholds: RegistryLaunchThresholds,
    reviewer_id: str,
    reviewed_utc: datetime,
    summary: str,
) -> ProductionThresholdRecord:
    """Create a production threshold packet from pilot data evidence."""

    blockers: tuple[str, ...] = ()
    if "local" in pilot_data_reference.lower() or "draft" in pilot_data_reference.lower():
        blockers = ("pilot data reference must identify real pilot measurements",)
    return ProductionThresholdRecord(pilot_data_reference, thresholds, reviewer_id, reviewed_utc, summary, not blockers, blockers)


def _require_text(value: str, name: str) -> None:
    """Require one visible text value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _require_aware(value: datetime, name: str) -> None:
    """Require one timezone-aware timestamp."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
