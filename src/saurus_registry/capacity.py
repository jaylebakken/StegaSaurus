"""Estimate registry handle capacity before changing payload width.

Saurus currently embeds a four-byte handle in audio and stores the durable
identity as a registry UUID. The handle is therefore a compact pointer into
tenant-scoped registry state, not a globally safe identifier. This module keeps
capacity review explicit: it estimates collision pressure for a handle space
and records whether a proposed width is compatible with the current codec
contract.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import exp


CURRENT_HANDLE_BYTES = 4


@dataclass(frozen=True, slots=True)
class HandleCapacityReview:
    """Summarize collision pressure and compatibility for one handle width."""

    handle_bytes: int
    projected_tenant_handles: int
    namespace_size: int
    fresh_collision_probability: float
    any_collision_probability: float
    codec_compatible: bool
    migration_required: bool
    recommendation: str


def review_handle_capacity(projected_tenant_handles: int, handle_bytes: int = CURRENT_HANDLE_BYTES) -> HandleCapacityReview:
    """Return a deterministic capacity review for a tenant handle namespace."""

    if isinstance(projected_tenant_handles, bool) or projected_tenant_handles < 0:
        raise ValueError("projected_tenant_handles must be a non-negative integer")
    if isinstance(handle_bytes, bool) or handle_bytes < 1:
        raise ValueError("handle_bytes must be a positive integer")
    namespace_size = 1 << (handle_bytes * 8)
    fresh_collision_probability = projected_tenant_handles / namespace_size
    any_collision_probability = _birthday_probability(projected_tenant_handles, namespace_size)
    codec_compatible = handle_bytes == CURRENT_HANDLE_BYTES
    migration_required = not codec_compatible
    return HandleCapacityReview(
        handle_bytes,
        projected_tenant_handles,
        namespace_size,
        fresh_collision_probability,
        any_collision_probability,
        codec_compatible,
        migration_required,
        _recommendation(fresh_collision_probability, any_collision_probability, codec_compatible),
    )


def _birthday_probability(draws: int, namespace_size: int) -> float:
    """Estimate probability that at least one collision has appeared."""

    if draws < 2:
        return 0.0
    exponent = -(draws * (draws - 1)) / (2 * namespace_size)
    return 1 - exp(exponent)


def _recommendation(fresh_collision_probability: float, any_collision_probability: float, codec_compatible: bool) -> str:
    """Turn capacity signals into conservative launch guidance."""

    if not codec_compatible:
        return "requires codec-version and migration evidence before use"
    if fresh_collision_probability >= 0.01:
        return "review payload width before tenant growth"
    if any_collision_probability >= 0.5:
        return "keep atomic collision retry and monitor issuance attempts"
    return "current width acceptable with tenant-scoped uniqueness and telemetry"
