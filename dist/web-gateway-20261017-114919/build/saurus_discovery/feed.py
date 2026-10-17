"""Search reviewed public feed snapshots for song-level candidates.

This connector is the smallest useful public-source integration shape. A caller
supplies entries from an already-reviewed official feed or API snapshot; the
connector filters those entries with target text, URL policy, and stable
deduplication before returning public page candidates.

No network access, media fetching, recipient attribution, or private registry
material belongs here. Live source adapters can later create ``FeedEntry``
values after their own policy, robots, rate-limit, and retry reviews.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import re

from .models import ConnectorPolicy, DiscoveryTarget, PageCandidate, SourceReview
from .url_policy import evaluate_fetch_url


@dataclass(frozen=True, slots=True)
class FeedEntry:
    """Represent one public entry from a reviewed feed or API snapshot."""

    title: str
    url: str
    summary: str
    published_utc: datetime

    def __post_init__(self) -> None:
        """Validate visible entry metadata before matching."""

        for value, name in ((self.title, "title"), (self.url, "url")):
            if not isinstance(value, str) or not value.strip():
                raise ValueError(f"{name} must not be empty")
        if not isinstance(self.summary, str):
            raise TypeError("summary must be a string")
        if self.published_utc.tzinfo is None or self.published_utc.utcoffset() is None:
            raise ValueError("published_utc must be timezone-aware")


@dataclass(frozen=True, slots=True)
class ReviewedFeedConnector:
    """Filter a reviewed feed snapshot into policy-approved page candidates."""

    policy: ConnectorPolicy
    review: SourceReview
    entries: tuple[FeedEntry, ...]

    def __post_init__(self) -> None:
        """Ensure the feed connector is tied to one approved source policy."""

        if self.policy.source_id != self.review.source_id:
            raise ValueError("policy and review source_id values must match")
        if not self.review.approved or not self.review.robots_reviewed or not self.review.terms_reviewed:
            raise ValueError("feed source review is not approved")

    def search(self, target: DiscoveryTarget) -> tuple[PageCandidate, ...]:
        """Return matching entries after URL policy and deduplication checks."""

        candidates: list[PageCandidate] = []
        seen_urls: set[str] = set()
        for entry in self.entries:
            if not _matches_target(entry, target):
                continue
            decision = evaluate_fetch_url(entry.url, self.policy)
            if not decision.allowed or decision.canonical_url in seen_urls:
                continue
            seen_urls.add(decision.canonical_url)
            candidates.append(PageCandidate(self.policy.source_id, decision.canonical_url, entry.title.strip(), entry.published_utc))
            if len(candidates) >= self.policy.max_results_per_job:
                break
        return tuple(candidates)


def _matches_target(entry: FeedEntry, target: DiscoveryTarget) -> bool:
    """Return whether public entry text mentions the target title or fingerprint."""

    haystack = _normalize_text(f"{entry.title} {entry.summary}")
    title = _normalize_text(target.title)
    public_fingerprint = _normalize_text(target.public_fingerprint_id)
    return title in haystack or public_fingerprint in haystack


def _normalize_text(value: str) -> str:
    """Normalize user-visible text for conservative feed matching."""

    return re.sub(r"\s+", " ", value.casefold()).strip()
