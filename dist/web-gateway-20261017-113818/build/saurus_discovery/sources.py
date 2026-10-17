"""Register discovery sources one at a time before connector expansion.

The crawler plan requires every public source to have an owner and policy
record before it is expanded. This in-memory catalog binds source review,
connector policy, and operational control state without performing live
crawling or granting access to private registry material.
"""

from __future__ import annotations

from dataclasses import dataclass

from .controls import ConnectorControlPlane, ConnectorHealthSnapshot
from .models import ConnectorPolicy, SourceReview


@dataclass(frozen=True, slots=True)
class SourceCatalogEntry:
    """Bind one source policy record to its review and control state."""

    source_id: str
    owner: str
    policy: ConnectorPolicy
    review: SourceReview
    control: ConnectorHealthSnapshot

    def __post_init__(self) -> None:
        """Validate source identity and ownership consistency."""

        if self.source_id != self.policy.source_id or self.source_id != self.review.source_id:
            raise ValueError("source identifiers must match")
        if self.owner != self.review.owner:
            raise ValueError("source owner must match review owner")

    @property
    def expansion_ready(self) -> bool:
        """Return whether this source has enough local evidence to expand."""

        return self.review.approved and self.review.robots_reviewed and self.review.terms_reviewed and self.control.enabled


class SourceCatalog:
    """Track reviewed discovery sources and their connector policies."""

    def __init__(self, control_plane: ConnectorControlPlane | None = None) -> None:
        """Initialize an empty source catalog."""

        self._control_plane = control_plane or ConnectorControlPlane()
        self._entries: dict[str, SourceCatalogEntry] = {}

    def register(self, policy: ConnectorPolicy, review: SourceReview) -> SourceCatalogEntry:
        """Register one source after matching its policy and review records."""

        if policy.source_id != review.source_id:
            raise ValueError("source policy and review identifiers must match")
        if policy.source_id in self._entries:
            raise ValueError("source_id is already registered")
        entry = SourceCatalogEntry(
            policy.source_id,
            review.owner,
            policy,
            review,
            self._control_plane.snapshot(policy.source_id),
        )
        self._entries[policy.source_id] = entry
        return entry

    def entry(self, source_id: str) -> SourceCatalogEntry:
        """Return one registered source entry with the latest control state."""

        stored = self._entries.get(source_id)
        if stored is None:
            raise ValueError("source_id is not registered")
        refreshed = SourceCatalogEntry(
            stored.source_id,
            stored.owner,
            stored.policy,
            stored.review,
            self._control_plane.snapshot(source_id),
        )
        self._entries[source_id] = refreshed
        return refreshed

    def ready_sources(self) -> tuple[SourceCatalogEntry, ...]:
        """Return registered sources ready for connector expansion."""

        return tuple(entry for entry in (self.entry(source_id) for source_id in self._entries) if entry.expansion_ready)

    def entries(self) -> tuple[SourceCatalogEntry, ...]:
        """Return all registered sources with refreshed control state."""

        return tuple(self.entry(source_id) for source_id in sorted(self._entries))
