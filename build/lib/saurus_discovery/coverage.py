"""Publish discovery source coverage status without promising completeness.

Public-web discovery should show what is monitored and what is not. This module
summarizes the reviewed source catalog and connector control state into a small
coverage snapshot: how many sources are registered, approved, ready, disabled,
or currently erroring. It does not crawl and it does not claim exhaustive web
coverage.
"""

from __future__ import annotations

from dataclasses import dataclass

from .sources import SourceCatalog, SourceCatalogEntry


@dataclass(frozen=True, slots=True)
class SourceCoverageSnapshot:
    """Summarize monitored public-source coverage and health."""

    registered_source_count: int
    approved_source_count: int
    ready_source_count: int
    disabled_source_count: int
    erroring_source_count: int
    total_run_count: int
    total_candidate_count: int
    total_failure_count: int
    source_statuses: tuple[str, ...]


def source_coverage_snapshot(catalog: SourceCatalog) -> SourceCoverageSnapshot:
    """Return a local coverage snapshot for registered discovery sources."""

    entries = catalog.entries()
    approved = tuple(entry for entry in entries if entry.review.approved)
    ready = tuple(entry for entry in entries if entry.expansion_ready)
    disabled = tuple(entry for entry in entries if not entry.control.enabled)
    erroring = tuple(entry for entry in entries if entry.control.last_error)
    return SourceCoverageSnapshot(
        registered_source_count=len(entries),
        approved_source_count=len(approved),
        ready_source_count=len(ready),
        disabled_source_count=len(disabled),
        erroring_source_count=len(erroring),
        total_run_count=sum(entry.control.run_count for entry in entries),
        total_candidate_count=sum(entry.control.candidate_count for entry in entries),
        total_failure_count=sum(entry.control.failure_count for entry in entries),
        source_statuses=tuple(_status(entry) for entry in entries),
    )


def _status(entry: SourceCatalogEntry) -> str:
    """Return one compact source status label."""

    if not entry.review.approved:
        return f"{entry.source_id}:unapproved"
    if not entry.control.enabled:
        return f"{entry.source_id}:disabled"
    if entry.control.last_error:
        return f"{entry.source_id}:error"
    if entry.expansion_ready:
        return f"{entry.source_id}:ready"
    return f"{entry.source_id}:review-incomplete"
