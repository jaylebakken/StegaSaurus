"""Evaluate launch gates for reviewed discovery connectors.

Discovery connectors should not move from a test fixture into monitoring just
because they return candidates. This module records a small gate decision over
policy review, URL-safety probes, bounded result behavior, and simple quality
expectations for approved target fixtures. It does not perform live crawling or
recipient attribution.
"""

from __future__ import annotations

from dataclasses import dataclass

from .connector import DiscoveryConnector
from .models import DiscoveryTarget
from .url_policy import evaluate_fetch_url


@dataclass(frozen=True, slots=True)
class ConnectorQualityCase:
    """Declare one expected connector outcome for a monitored target."""

    target: DiscoveryTarget
    minimum_results: int = 1

    def __post_init__(self) -> None:
        """Validate the expected positive result count."""

        if self.minimum_results < 0:
            raise ValueError("minimum_results must not be negative")


@dataclass(frozen=True, slots=True)
class ConnectorGateResult:
    """Summarize whether a connector passes preflight launch gates."""

    passed: bool
    policy_passed: bool
    security_passed: bool
    load_passed: bool
    quality_passed: bool
    reasons: tuple[str, ...]


def evaluate_connector_gate(
    connector: DiscoveryConnector,
    quality_cases: tuple[ConnectorQualityCase, ...],
    blocked_url_probes: tuple[str, ...],
) -> ConnectorGateResult:
    """Evaluate policy, security, load, and quality gates for one connector."""

    reasons: list[str] = []
    policy_passed = _policy_passed(connector, reasons)
    security_passed = _security_passed(connector, blocked_url_probes, reasons)
    load_passed = _load_passed(connector, quality_cases, reasons)
    quality_passed = _quality_passed(connector, quality_cases, reasons)
    passed = policy_passed and security_passed and load_passed and quality_passed
    return ConnectorGateResult(passed, policy_passed, security_passed, load_passed, quality_passed, tuple(reasons))


def _policy_passed(connector: DiscoveryConnector, reasons: list[str]) -> bool:
    """Return whether source review and connector policy are launchable."""

    review = connector.review
    passed = review.approved and review.robots_reviewed and review.terms_reviewed and review.retention_days >= 0
    if not passed:
        reasons.append("source review is incomplete")
    if connector.policy.max_results_per_job < 1 or connector.policy.per_host_concurrency < 1:
        reasons.append("connector budgets are invalid")
        return False
    return passed


def _security_passed(connector: DiscoveryConnector, blocked_url_probes: tuple[str, ...], reasons: list[str]) -> bool:
    """Return whether blocked URL probes are rejected by policy."""

    unsafe = tuple(url for url in blocked_url_probes if evaluate_fetch_url(url, connector.policy).allowed)
    if unsafe:
        reasons.append("blocked URL probe was allowed")
        return False
    return True


def _load_passed(connector: DiscoveryConnector, quality_cases: tuple[ConnectorQualityCase, ...], reasons: list[str]) -> bool:
    """Return whether connector output stays within result budgets."""

    overloaded = tuple(case.target.song_id for case in quality_cases if len(connector.search(case.target)) > connector.policy.max_results_per_job)
    if overloaded:
        reasons.append("connector emitted more results than its job budget")
        return False
    return True


def _quality_passed(connector: DiscoveryConnector, quality_cases: tuple[ConnectorQualityCase, ...], reasons: list[str]) -> bool:
    """Return whether connector meets declared fixture expectations."""

    misses = tuple(case.target.song_id for case in quality_cases if len(connector.search(case.target)) < case.minimum_results)
    if misses:
        reasons.append("connector missed expected quality cases")
        return False
    return True
