"""Measure reviewed feed filtering without crawling or notifying clients.

Discovery pilot metrics include policy denials, duplicate public pages, source
errors, and candidate counts. The feed connector already filters denied and
duplicate entries, but launch review needs those dropped counts to stay visible.
This module audits a reviewed feed snapshot using the same conservative target
matching and URL policy rules, without fetching media or sending notifications.
"""

from __future__ import annotations

from dataclasses import dataclass
import re

from .feed import FeedEntry
from .models import ConnectorPolicy, DiscoveryTarget
from .url_policy import evaluate_fetch_url


@dataclass(frozen=True, slots=True)
class FeedSourceMetricsSnapshot:
    """Summarize filtering outcomes for one reviewed feed snapshot."""

    source_id: str
    entry_count: int
    target_match_count: int
    emitted_candidate_count: int
    policy_denial_count: int
    duplicate_count: int

    def __post_init__(self) -> None:
        """Validate source identity and non-negative counters."""

        _require_text(self.source_id, "source_id")
        for value, name in (
            (self.entry_count, "entry_count"),
            (self.target_match_count, "target_match_count"),
            (self.emitted_candidate_count, "emitted_candidate_count"),
            (self.policy_denial_count, "policy_denial_count"),
            (self.duplicate_count, "duplicate_count"),
        ):
            if value < 0:
                raise ValueError(f"{name} must not be negative")


def feed_source_metrics_snapshot(
    policy: ConnectorPolicy,
    target: DiscoveryTarget,
    entries: tuple[FeedEntry, ...],
) -> FeedSourceMetricsSnapshot:
    """Return policy-denial and duplicate counters for one feed snapshot."""

    seen_urls: set[str] = set()
    target_matches = 0
    emitted = 0
    policy_denials = 0
    duplicates = 0
    for entry in entries:
        if not _matches_target(entry, target):
            continue
        target_matches += 1
        decision = evaluate_fetch_url(entry.url, policy)
        if not decision.allowed:
            policy_denials += 1
            continue
        if decision.canonical_url in seen_urls:
            duplicates += 1
            continue
        seen_urls.add(decision.canonical_url)
        if emitted < policy.max_results_per_job:
            emitted += 1
    return FeedSourceMetricsSnapshot(policy.source_id, len(entries), target_matches, emitted, policy_denials, duplicates)


def _matches_target(entry: FeedEntry, target: DiscoveryTarget) -> bool:
    """Return whether public entry text mentions the target title or fingerprint."""

    haystack = _normalize_text(f"{entry.title} {entry.summary}")
    return _normalize_text(target.title) in haystack or _normalize_text(target.public_fingerprint_id) in haystack


def _normalize_text(value: str) -> str:
    """Normalize visible text for conservative feed matching."""

    return re.sub(r"\s+", " ", value.casefold()).strip()


def _require_text(value: str, name: str) -> None:
    """Require one visible text value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")
