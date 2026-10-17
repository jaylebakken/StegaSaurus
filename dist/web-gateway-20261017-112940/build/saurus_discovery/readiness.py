"""Run a local no-notification discovery baseline rehearsal.

Discovery should not move from planning into live public-web crawling just
because connector code exists. This module exercises the safe local path:
reviewed feed entries, URL policy filtering, candidate adjudication, and a
baseline record with zero client notifications. It does not fetch live media,
crawl the public web, select real customer sources, or approve alerts.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
import json

from .adjudication import CandidateAdjudication, CandidateReviewLabel, candidate_adjudication_snapshot
from .baseline import DiscoveryBaselineRun
from .feed import FeedEntry, ReviewedFeedConnector
from .live_gate import LiveCrawlGateDecision, evaluate_live_crawl_gate
from .models import CandidateRecord, ConnectorPolicy, DiscoveryTarget, ReviewState, SourceReview
from .source_metrics import feed_source_metrics_snapshot

__all__ = ["DiscoveryBaselineRehearsalResult", "main", "run_no_notification_baseline_rehearsal"]


@dataclass(frozen=True, slots=True)
class DiscoveryBaselineRehearsalResult:
    """Summarize one local discovery no-notification rehearsal."""

    baseline: DiscoveryBaselineRun
    live_gate: LiveCrawlGateDecision


def run_no_notification_baseline_rehearsal() -> DiscoveryBaselineRehearsalResult:
    """Run a reviewed-feed baseline rehearsal without notifications."""

    now = _now()
    target = DiscoveryTarget("tenant-1", "song-1", "Night Drive", "public-fingerprint-1")
    policy = ConnectorPolicy("reviewed-feed", ("example.com",), max_results_per_job=3)
    review = SourceReview("reviewed-feed", "policy-owner", True, True, True, "ops@example.test", 14, now)
    entries = (
        FeedEntry("Night Drive official preview", "https://example.com/night-drive", "official preview", now),
        FeedEntry("Night Drive duplicate", "https://example.com/night-drive", "duplicate URL", now),
        FeedEntry("Night Drive live clip", "https://media.example.com/night-drive-live", "live clip", now),
        FeedEntry("Night Drive mirror outside approved host", "https://outside.test/night-drive", "outside host", now),
        FeedEntry("Other Song", "https://example.com/other", "unrelated title", now),
    )
    candidates = ReviewedFeedConnector(policy, review, entries).search(target)
    source_metrics = feed_source_metrics_snapshot(policy, target, entries)
    records = tuple(
        CandidateRecord(
            f"candidate-{index}",
            target.tenant_id,
            target.song_id,
            candidate.source_id,
            candidate.url,
            0.9 - index * 0.01,
            20.0,
            ReviewState.ACCEPTED,
            now,
            now + timedelta(days=14),
        )
        for index, candidate in enumerate(candidates, start=1)
    )
    adjudications = tuple(
        CandidateAdjudication(record.candidate_id, CandidateReviewLabel.TRUE_MATCH, "pilot-reviewer", "local baseline fixture", now)
        for record in records
    )
    baseline = DiscoveryBaselineRun(
        "baseline-local-rehearsal",
        "pilot-reviewer",
        now,
        now + timedelta(hours=2),
        (source_metrics,),
        candidate_adjudication_snapshot(records, adjudications),
    )
    live_gate = evaluate_live_crawl_gate(None, (baseline,), len(records), legal_policy_approved=False, recognition_engine_name="")
    return DiscoveryBaselineRehearsalResult(baseline, live_gate)


def main(argv: list[str] | None = None) -> int:
    """Run the local no-notification baseline rehearsal and print JSON."""

    parser = argparse.ArgumentParser(description="Run a local Saurus discovery no-notification baseline rehearsal.")
    parser.parse_args(argv)
    print(_json_result(run_no_notification_baseline_rehearsal()))
    return 0


def _json_result(result: DiscoveryBaselineRehearsalResult) -> str:
    """Serialize one rehearsal without public-page body or media content."""

    return json.dumps(
        {
            "run_id": result.baseline.run_id,
            "reviewer_id": result.baseline.reviewer_id,
            "client_notification_count": result.baseline.client_notification_count,
            "emitted_candidate_count": result.baseline.emitted_candidate_count,
            "policy_denial_count": result.baseline.policy_denial_count,
            "duplicate_count": result.baseline.duplicate_count,
            "adjudication": asdict(result.baseline.adjudication),
            "live_crawl_enabled": result.live_gate.enabled,
            "live_crawl_blockers": result.live_gate.blockers,
        },
        indent=2,
        sort_keys=True,
    )


def _now() -> datetime:
    """Return the current timezone-aware UTC time."""

    return datetime.now(timezone.utc)


if __name__ == "__main__":
    raise SystemExit(main())
