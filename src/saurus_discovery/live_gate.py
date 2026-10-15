"""Gate live discovery crawling behind pilot-readiness evidence.

Saurus discovery should remain a reviewed-feed and no-notification baseline
system until the client scope, source approvals, representative corpus, legal
review, and song-recognition engine are all explicit. This module makes that
default-deny posture executable. It does not crawl, fetch media, notify clients,
or turn a song match into recipient attribution.
"""

from __future__ import annotations

from dataclasses import dataclass

from .baseline import DiscoveryBaselineRun
from .enrollment import DiscoveryPilotEnrollment

__all__ = ["LiveCrawlGateDecision", "evaluate_live_crawl_gate"]


@dataclass(frozen=True, slots=True)
class LiveCrawlGateDecision:
    """Summarize whether live public-web crawling may be enabled."""

    enabled: bool
    blockers: tuple[str, ...]


def evaluate_live_crawl_gate(
    enrollment: DiscoveryPilotEnrollment | None,
    baseline_runs: tuple[DiscoveryBaselineRun, ...],
    representative_corpus_case_count: int,
    *,
    legal_policy_approved: bool,
    recognition_engine_name: str,
) -> LiveCrawlGateDecision:
    """Return a default-deny live-crawl decision from readiness evidence."""

    if isinstance(representative_corpus_case_count, bool) or representative_corpus_case_count < 0:
        raise ValueError("representative_corpus_case_count must not be negative")
    blockers: list[str] = []
    if enrollment is None:
        blockers.append("approved target and source enrollment is missing")
    if not baseline_runs:
        blockers.append("no-notification baseline has not run")
    if representative_corpus_case_count == 0:
        blockers.append("representative corpus is missing")
    if not legal_policy_approved:
        blockers.append("legal and source-policy approval is missing")
    if not isinstance(recognition_engine_name, str) or not recognition_engine_name.strip():
        blockers.append("song-recognition engine is not selected")
    return LiveCrawlGateDecision(not blockers, tuple(blockers))
