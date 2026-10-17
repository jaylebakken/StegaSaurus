"""Summarize registry authorization and tenant-isolation probes.

Launch review should not treat access-control tests as scattered assertions.
This module records small probe results such as unauthorized requests,
role-denied routes, and cross-tenant reads, then summarizes whether those probes
passed. It does not perform network calls or replace external security review.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum


class RegistryAccessProbeKind(str, Enum):
    """Name the kind of registry access-control probe."""

    UNAUTHORIZED = "unauthorized"
    ROLE_DENIED = "role denied"
    CROSS_TENANT = "cross tenant"


@dataclass(frozen=True, slots=True)
class RegistryAccessProbe:
    """Record one observed access-control test result."""

    name: str
    kind: RegistryAccessProbeKind
    expected_status: int
    observed_status: int

    def __post_init__(self) -> None:
        """Validate one probe observation."""

        _require_text(self.name, "name")
        _require_status(self.expected_status, "expected_status")
        _require_status(self.observed_status, "observed_status")

    @property
    def passed(self) -> bool:
        """Return whether the observed status matched the expected status."""

        return self.observed_status == self.expected_status


@dataclass(frozen=True, slots=True)
class RegistryAccessReviewSnapshot:
    """Summarize authorization and tenant-isolation probe results."""

    probe_count: int
    passed_count: int
    failed_count: int
    unauthorized_probe_count: int
    cross_tenant_probe_count: int
    pass_rate: float
    failed_probe_names: tuple[str, ...]


def registry_access_review_snapshot(probes: tuple[RegistryAccessProbe, ...]) -> RegistryAccessReviewSnapshot:
    """Return a local access-review summary from explicit probes."""

    passed = tuple(probe for probe in probes if probe.passed)
    failed = tuple(probe for probe in probes if not probe.passed)
    return RegistryAccessReviewSnapshot(
        len(probes),
        len(passed),
        len(failed),
        sum(1 for probe in probes if probe.kind is RegistryAccessProbeKind.UNAUTHORIZED),
        sum(1 for probe in probes if probe.kind is RegistryAccessProbeKind.CROSS_TENANT),
        1.0 if not probes else len(passed) / len(probes),
        tuple(probe.name for probe in failed),
    )


def _require_text(value: str, name: str) -> None:
    """Require one visible string value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _require_status(value: int, name: str) -> None:
    """Require one HTTP status-code-like integer."""

    if isinstance(value, bool) or value < 100 or value > 599:
        raise ValueError(f"{name} must be an HTTP status code")
