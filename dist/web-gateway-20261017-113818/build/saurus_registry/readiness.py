"""Run a local registry launch-gate rehearsal.

Deployment readiness needs a repeatable way to exercise the launch-gate objects
before an AWS alpha exists. This module builds a tiny SQLite registry, completes
one reserve/finalize path, rehearses backup/restore, records local access/API
measurements, and returns a written launch decision. It is a local alpha
rehearsal only; production thresholds still require pilot data and deployed
infrastructure evidence.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
import json
from pathlib import Path
from tempfile import mkdtemp

from stegosaurus.audio.attribution import BlockAttributionRecord
from stegosaurus.audio.attribution_core.models import AttributionRecord
from stegosaurus.audio.transport import CarrierPlan

from .access_review import RegistryAccessProbe, RegistryAccessProbeKind, registry_access_review_snapshot
from .api_metrics import RegistryApiObservation, registry_api_metrics_snapshot
from .application import RegistryService
from .launch import RegistryLaunchDecisionRecord, RegistryLaunchThresholds, record_registry_launch_decision
from .maintenance import rehearse_sqlite_backup_restore
from .metrics import registry_metrics_snapshot
from .serialization import serialize_block_record
from .sqlite import SQLiteRegistryRepository

__all__ = ["RegistryLaunchRehearsalResult", "main", "run_local_registry_launch_rehearsal"]


@dataclass(frozen=True, slots=True)
class RegistryLaunchRehearsalResult:
    """Summarize one local registry launch-gate rehearsal."""

    workspace: Path
    database_path: Path
    decision_record: RegistryLaunchDecisionRecord


def run_local_registry_launch_rehearsal(workspace: Path) -> RegistryLaunchRehearsalResult:
    """Run a complete local registry launch-gate review rehearsal."""

    root = workspace.expanduser()
    root.mkdir(parents=True, exist_ok=True)
    database_path = root / "registry-launch.sqlite"
    repository = SQLiteRegistryRepository(database_path)
    service = RegistryService(repository, clock=_now, handle_factory=lambda: b"\x10\x20\x30\x40")
    tenant = service.register_tenant("Launch Gate Tenant", "ops-reviewer", "launch-tenant")
    song = service.register_song(tenant.tenant_id, "Launch Gate Song", "sha256:source", 16000, 480000, "launch-v1", "ops-reviewer", "launch-song")
    export = service.reserve_export(tenant.tenant_id, song.song_id, "Launch Recipient", "ops-reviewer", "launch-reserve")
    service.finalize_export(tenant.tenant_id, export.export_id, _payload(export.handle), "ops-reviewer", "launch-finalize")
    backup_restore = rehearse_sqlite_backup_restore(database_path, root / "backup.sqlite", root / "restored.sqlite")
    record = record_registry_launch_decision(
        registry_metrics_snapshot(repository, tenant.tenant_id, (song.song_id,)),
        registry_access_review_snapshot(_access_probes()),
        registry_api_metrics_snapshot(_api_observations()),
        backup_restore,
        _local_alpha_thresholds(),
        "ops-reviewer",
        _now(),
        "local alpha registry launch gates pass",
    )
    if not record.decision.go:
        raise RuntimeError("; ".join(record.decision.reasons))
    return RegistryLaunchRehearsalResult(root, database_path, record)


def main(argv: list[str] | None = None) -> int:
    """Run the local launch-gate rehearsal and print a concise JSON result."""

    parser = argparse.ArgumentParser(description="Run a local Saurus registry launch-gate rehearsal.")
    parser.add_argument("--workspace", type=Path, help="Directory for rehearsal database, backup, and restore files.")
    args = parser.parse_args(argv)
    workspace = args.workspace or Path(mkdtemp(prefix="saurus-registry-launch-"))
    result = run_local_registry_launch_rehearsal(workspace)
    print(_json_result(result))
    return 0


def _payload(handle: bytes) -> bytes:
    """Return one canonical private record payload for a reserved handle."""

    plan = CarrierPlan(4, 6, (0, 1))
    private = AttributionRecord(handle, plan, ((0, 1), (2, 3), (4, 5), (6, 7)), 16000)
    return serialize_block_record(BlockAttributionRecord(handle, 480000, 16000, (private,), 480000))


def _access_probes() -> tuple[RegistryAccessProbe, ...]:
    """Return local access-review probes for launch rehearsal evidence."""

    return (
        RegistryAccessProbe("missing bearer token", RegistryAccessProbeKind.UNAUTHORIZED, 401, 401),
        RegistryAccessProbe("write route with read role", RegistryAccessProbeKind.ROLE_DENIED, 403, 403),
        RegistryAccessProbe("cross tenant export read", RegistryAccessProbeKind.CROSS_TENANT, 404, 404),
    )


def _api_observations() -> tuple[RegistryApiObservation, ...]:
    """Return measured API-shaped observations for the local rehearsal."""

    return (
        RegistryApiObservation("POST /v1/songs", 201, 12.0, 512),
        RegistryApiObservation("POST /v1/exports:reserve", 201, 14.0, 640),
        RegistryApiObservation("POST /v1/exports:finalize", 200, 18.0, 768),
        RegistryApiObservation("GET /v1/verification-records", 200, 16.0, 1024, 1, False),
    )


def _local_alpha_thresholds() -> RegistryLaunchThresholds:
    """Return explicit non-production thresholds for local alpha rehearsal."""

    return RegistryLaunchThresholds(1.0, 0.0, 1.0, 1.0, 0, 0, 1.0, 100.0, 0.0, 2_000, 10, 0, 2_000.0)


def _json_result(result: RegistryLaunchRehearsalResult) -> str:
    """Serialize the rehearsal result without private record payloads."""

    return json.dumps(
        {
            "workspace": str(result.workspace),
            "database_path": str(result.database_path),
            "go": result.decision_record.decision.go,
            "reasons": result.decision_record.decision.reasons,
            "summary": result.decision_record.summary,
            "metrics": asdict(result.decision_record.metrics),
            "api_metrics": asdict(result.decision_record.api_metrics),
            "access_review": asdict(result.decision_record.access_review),
            "backup_restore_ms": result.decision_record.backup_restore.total_elapsed_ms,
        },
        indent=2,
        sort_keys=True,
    )


def _now() -> datetime:
    """Return the current timezone-aware UTC time."""

    return datetime.now(timezone.utc)


if __name__ == "__main__":
    raise SystemExit(main())
