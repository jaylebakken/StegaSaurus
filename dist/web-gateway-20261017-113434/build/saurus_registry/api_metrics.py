"""Summarize registry API latency and bundle-size observations.

Launch gates need measured API behavior, but the registry should not bake a
specific metrics backend into the router. This module accepts small observations
from a caller or test harness and derives P50/P95 latency, response size, error
rate, and verification-bundle bounds. It does not define production SLOs.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil
from statistics import median

from .api import ApiResponse


@dataclass(frozen=True, slots=True)
class RegistryApiObservation:
    """Record one measured registry API response."""

    route: str
    status: int
    latency_ms: float
    response_bytes: int
    bundle_record_count: int = 0
    bundle_truncated: bool = False

    def __post_init__(self) -> None:
        """Validate measured API observation values."""

        _require_text(self.route, "route")
        if self.status < 100 or self.status > 599:
            raise ValueError("status must be an HTTP status code")
        if self.latency_ms < 0:
            raise ValueError("latency_ms must not be negative")
        if self.response_bytes < 0:
            raise ValueError("response_bytes must not be negative")
        if self.bundle_record_count < 0:
            raise ValueError("bundle_record_count must not be negative")


@dataclass(frozen=True, slots=True)
class RegistryApiMetricsSnapshot:
    """Summarize measured registry API behavior for launch review."""

    observation_count: int
    p50_latency_ms: float
    p95_latency_ms: float
    max_response_bytes: int
    max_bundle_record_count: int
    truncated_bundle_count: int
    error_rate: float


def observe_registry_api_response(
    route: str,
    response: ApiResponse,
    latency_ms: float,
    *,
    bundle_record_count: int = 0,
    bundle_truncated: bool = False,
) -> RegistryApiObservation:
    """Build one API observation from an HTTP-shaped response."""

    return RegistryApiObservation(route, response.status, latency_ms, len(response.body), bundle_record_count, bundle_truncated)


def registry_api_metrics_snapshot(observations: tuple[RegistryApiObservation, ...]) -> RegistryApiMetricsSnapshot:
    """Return aggregate latency, response-size, and bundle-bound metrics."""

    if not observations:
        return RegistryApiMetricsSnapshot(0, 0.0, 0.0, 0, 0, 0, 0.0)
    latencies = tuple(sorted(observation.latency_ms for observation in observations))
    errors = sum(1 for observation in observations if observation.status >= 400)
    return RegistryApiMetricsSnapshot(
        len(observations),
        float(median(latencies)),
        _nearest_rank(latencies, 0.95),
        max(observation.response_bytes for observation in observations),
        max(observation.bundle_record_count for observation in observations),
        sum(1 for observation in observations if observation.bundle_truncated),
        errors / len(observations),
    )


def _nearest_rank(sorted_values: tuple[float, ...], percentile: float) -> float:
    """Return a nearest-rank percentile for a non-empty sorted sample."""

    index = max(0, ceil(percentile * len(sorted_values)) - 1)
    return sorted_values[index]


def _require_text(value: str, name: str) -> None:
    """Require a non-empty text value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")
