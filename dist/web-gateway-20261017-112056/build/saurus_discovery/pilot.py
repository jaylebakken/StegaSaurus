"""Evaluate discovery pilot metrics before any launch decision.

The public-web discovery pilot should not graduate on anecdotes. This module
records the small set of measured counters from the plan and evaluates them
against explicit thresholds. It does not crawl, notify clients, or produce
legal conclusions.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime


@dataclass(frozen=True, slots=True)
class DiscoveryPilotMetrics:
    """Record measured discovery pilot counters and costs."""

    monitored_song_count: int
    reviewed_candidate_count: int
    true_match_count: int
    false_match_count: int
    duplicate_count: int
    unusable_count: int
    missed_known_match_count: int
    median_discovery_latency_hours: float
    median_review_minutes: float
    bytes_fetched: int
    retained_evidence_bytes: int
    useful_candidate_count: int
    source_error_count: int
    policy_denial_count: int
    opt_out_completion_hours: float
    song_match_only_count: int
    attribution_eligible_count: int

    def __post_init__(self) -> None:
        """Validate non-negative measured counters."""

        for value, name in (
            (self.monitored_song_count, "monitored_song_count"),
            (self.reviewed_candidate_count, "reviewed_candidate_count"),
            (self.true_match_count, "true_match_count"),
            (self.false_match_count, "false_match_count"),
            (self.duplicate_count, "duplicate_count"),
            (self.unusable_count, "unusable_count"),
            (self.missed_known_match_count, "missed_known_match_count"),
            (self.bytes_fetched, "bytes_fetched"),
            (self.retained_evidence_bytes, "retained_evidence_bytes"),
            (self.useful_candidate_count, "useful_candidate_count"),
            (self.source_error_count, "source_error_count"),
            (self.policy_denial_count, "policy_denial_count"),
            (self.song_match_only_count, "song_match_only_count"),
            (self.attribution_eligible_count, "attribution_eligible_count"),
        ):
            if value < 0:
                raise ValueError(f"{name} must not be negative")
        for value, name in (
            (self.median_discovery_latency_hours, "median_discovery_latency_hours"),
            (self.median_review_minutes, "median_review_minutes"),
            (self.opt_out_completion_hours, "opt_out_completion_hours"),
        ):
            if value < 0:
                raise ValueError(f"{name} must not be negative")

    @property
    def precision(self) -> float:
        """Return reviewed candidate precision."""

        decided = self.true_match_count + self.false_match_count
        return 1.0 if decided == 0 else self.true_match_count / decided

    @property
    def miss_rate(self) -> float:
        """Return missed known match rate."""

        known = self.true_match_count + self.missed_known_match_count
        return 0.0 if known == 0 else self.missed_known_match_count / known

    @property
    def false_alerts_per_song(self) -> float:
        """Return false matches normalized by monitored song count."""

        return 0.0 if self.monitored_song_count == 0 else self.false_match_count / self.monitored_song_count


@dataclass(frozen=True, slots=True)
class DiscoveryPilotThresholds:
    """Declare numeric launch gates for a controlled pilot."""

    minimum_precision: float
    maximum_miss_rate: float
    maximum_false_alerts_per_song: float
    maximum_median_latency_hours: float
    maximum_median_review_minutes: float
    maximum_source_errors: int
    maximum_opt_out_completion_hours: float

    def __post_init__(self) -> None:
        """Validate launch thresholds before evaluation."""

        if not 0.0 <= self.minimum_precision <= 1.0 or not 0.0 <= self.maximum_miss_rate <= 1.0:
            raise ValueError("precision and miss-rate thresholds must be ratios")
        if self.maximum_false_alerts_per_song < 0 or self.maximum_median_latency_hours < 0:
            raise ValueError("false-alert and latency thresholds must not be negative")
        if self.maximum_median_review_minutes < 0 or self.maximum_source_errors < 0:
            raise ValueError("review and source-error thresholds must not be negative")
        if self.maximum_opt_out_completion_hours < 0:
            raise ValueError("opt-out threshold must not be negative")


@dataclass(frozen=True, slots=True)
class DiscoveryPilotDecision:
    """Summarize whether pilot metrics meet explicit go/no-go thresholds."""

    go: bool
    reasons: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class DiscoveryPilotDecisionRecord:
    """Record one written pilot decision with measured evidence."""

    reviewer_id: str
    decided_utc: datetime
    summary: str
    metrics: DiscoveryPilotMetrics
    thresholds: DiscoveryPilotThresholds
    decision: DiscoveryPilotDecision

    def __post_init__(self) -> None:
        """Validate decision provenance and written rationale."""

        _require_text(self.reviewer_id, "reviewer_id")
        _require_text(self.summary, "summary")
        if self.decided_utc.tzinfo is None or self.decided_utc.utcoffset() is None:
            raise ValueError("decided_utc must be timezone-aware")


def evaluate_discovery_pilot(metrics: DiscoveryPilotMetrics, thresholds: DiscoveryPilotThresholds) -> DiscoveryPilotDecision:
    """Evaluate measured pilot metrics against launch gates."""

    reasons: list[str] = []
    if metrics.precision < thresholds.minimum_precision:
        reasons.append("precision is below threshold")
    if metrics.miss_rate > thresholds.maximum_miss_rate:
        reasons.append("miss rate is above threshold")
    if metrics.false_alerts_per_song > thresholds.maximum_false_alerts_per_song:
        reasons.append("false alerts per song is above threshold")
    if metrics.median_discovery_latency_hours > thresholds.maximum_median_latency_hours:
        reasons.append("median discovery latency is above threshold")
    if metrics.median_review_minutes > thresholds.maximum_median_review_minutes:
        reasons.append("median review time is above threshold")
    if metrics.source_error_count > thresholds.maximum_source_errors:
        reasons.append("source error count is above threshold")
    if metrics.opt_out_completion_hours > thresholds.maximum_opt_out_completion_hours:
        reasons.append("opt-out completion time is above threshold")
    return DiscoveryPilotDecision(not reasons, tuple(reasons))


def record_discovery_pilot_decision(
    metrics: DiscoveryPilotMetrics,
    thresholds: DiscoveryPilotThresholds,
    reviewer_id: str,
    decided_utc: datetime,
    summary: str,
) -> DiscoveryPilotDecisionRecord:
    """Create a written pilot decision record from measured gates."""

    return DiscoveryPilotDecisionRecord(
        reviewer_id,
        decided_utc,
        summary,
        metrics,
        thresholds,
        evaluate_discovery_pilot(metrics, thresholds),
    )


def _require_text(value: str, name: str) -> None:
    """Require one non-empty text value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")
