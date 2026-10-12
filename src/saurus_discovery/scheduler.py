"""Schedule reviewed discovery jobs with explicit budgets and a kill switch.

The scheduler is an in-process contract for Phase 3. It records job state and
enforces a global disable control before connectors are asked to search public
sources. It does not perform network fetches or media decoding.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from enum import Enum

from .connector import DiscoveryConnector
from .controls import ConnectorControlPlane
from .models import DiscoveryTarget, PageCandidate


class JobState(str, Enum):
    """Name the explicit lifecycle states of one discovery job."""

    QUEUED = "queued"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    KILLED = "killed"


@dataclass(frozen=True, slots=True)
class DiscoveryJob:
    """Record one scheduled connector search."""

    job_id: str
    target: DiscoveryTarget
    connector_id: str
    state: JobState
    created_utc: datetime
    attempts: int = 0
    result_count: int = 0
    error: str = ""


class DiscoveryScheduler:
    """Run connector searches behind review, budget, and kill-switch checks."""

    def __init__(self, control_plane: ConnectorControlPlane | None = None) -> None:
        """Initialize an empty enabled scheduler."""

        self._jobs: dict[str, DiscoveryJob] = {}
        self._enabled = True
        self._control_plane = control_plane

    def disable(self) -> None:
        """Turn on the global discovery kill switch."""

        self._enabled = False

    def enable(self) -> None:
        """Turn off the global discovery kill switch."""

        self._enabled = True

    def enqueue(self, job_id: str, target: DiscoveryTarget, connector: DiscoveryConnector, now: datetime) -> DiscoveryJob:
        """Add one reviewed connector job to the queue."""

        if not connector.review.approved or not connector.review.robots_reviewed or not connector.review.terms_reviewed:
            raise ValueError("connector source review is not approved")
        if job_id in self._jobs:
            raise ValueError("job_id is already queued")
        job = DiscoveryJob(job_id, target, connector.policy.source_id, JobState.QUEUED, now)
        self._jobs[job_id] = job
        return job

    def run_next(self, connector: DiscoveryConnector) -> tuple[DiscoveryJob, tuple[PageCandidate, ...]]:
        """Run the oldest queued job for one connector within its result budget."""

        job = next((item for item in self._jobs.values() if item.connector_id == connector.policy.source_id and item.state is JobState.QUEUED), None)
        if job is None:
            raise ValueError("no queued job for connector")
        if not self._enabled:
            killed = replace(job, state=JobState.KILLED, error="global discovery kill switch is enabled")
            self._jobs[job.job_id] = killed
            return killed, ()
        if self._control_plane is not None and not self._control_plane.is_enabled(connector.policy.source_id):
            reason = self._control_plane.snapshot(connector.policy.source_id).disabled_reason
            killed = replace(job, state=JobState.KILLED, error=f"connector is disabled: {reason}")
            self._jobs[job.job_id] = killed
            return killed, ()
        running = replace(job, state=JobState.RUNNING, attempts=job.attempts + 1)
        self._jobs[job.job_id] = running
        try:
            candidates = connector.search(job.target)[: connector.policy.max_results_per_job]
        except Exception as error:
            failed = replace(running, state=JobState.FAILED, error=str(error))
            self._jobs[job.job_id] = failed
            if self._control_plane is not None:
                self._control_plane.record_run(connector.policy.source_id, 0, str(error))
            return failed, ()
        complete = replace(running, state=JobState.COMPLETE, result_count=len(candidates))
        self._jobs[job.job_id] = complete
        if self._control_plane is not None:
            self._control_plane.record_run(connector.policy.source_id, len(candidates))
        return complete, tuple(candidates)

    def job(self, job_id: str) -> DiscoveryJob | None:
        """Return one scheduled job by identity."""

        return self._jobs.get(job_id)
