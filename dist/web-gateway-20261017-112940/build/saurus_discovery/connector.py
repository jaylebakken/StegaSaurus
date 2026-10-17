"""Declare source connector behavior for public-web discovery.

Connectors search approved public sources and emit page candidates only. They
own their source policy, rate limits, and retry behavior; they do not receive
private registry records or make recipient-attribution decisions.
"""

from __future__ import annotations

from typing import Protocol

from .models import ConnectorPolicy, DiscoveryTarget, PageCandidate, SourceReview


class DiscoveryConnector(Protocol):
    """Search one reviewed public source for song-level candidates."""

    @property
    def policy(self) -> ConnectorPolicy:
        """Return the connector URL and budget policy."""

    @property
    def review(self) -> SourceReview:
        """Return the recorded source policy review."""

    def search(self, target: DiscoveryTarget) -> tuple[PageCandidate, ...]:
        """Return public page candidates for one approved target song."""
