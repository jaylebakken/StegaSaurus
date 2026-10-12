"""Test the server-side registry contract below HTTP and durable SQL.

These tests freeze canonical private-record bytes, tenant isolation, random
handle collision retry, explicit export state transitions, and registry-only
lineage. They do not claim that the in-memory repository is deployment storage
or that registry success proves watermark robustness.
"""

from __future__ import annotations

from base64 import b64encode
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from itertools import count
import json
from pathlib import Path
import sqlite3
from threading import Event

import pytest

from saurus_registry import (
    CURRENT_HANDLE_BYTES,
    CURRENT_SCHEMA_VERSION,
    ApiRequest,
    ExportRecord,
    ExportState,
    HandleCapacityReview,
    HandleConflictError,
    HmacBearerAuthenticator,
    InMemoryRegistryRepository,
    LocalHmacStreamCipher,
    RegistryAccessProbe,
    RegistryAccessProbeKind,
    RegistryAccessReviewSnapshot,
    RegistryService,
    RegistryApi,
    RegistryApiMetricsSnapshot,
    RegistryApiObservation,
    RegistryLaunchDecisionRecord,
    RegistryLaunchThresholds,
    RegistryMetricsSnapshot,
    RegistryRetentionPolicy,
    RetentionAction,
    ScheduledRegistryOperation,
    SQLiteRegistryRepository,
    StoredAttributionRecord,
    TenantExportManifest,
    BackupRestoreRehearsalResult,
    build_tenant_export_manifest,
    build_watermark_report_payload,
    default_registry_operations,
    due_registry_operations,
    evaluate_registry_launch,
    expire_stale_reserved_exports,
    mark_registry_operation_run,
    observe_registry_api_response,
    rotate_sqlite_record_key,
    registry_api_metrics_snapshot,
    registry_metrics_snapshot,
    record_registry_launch_decision,
    registry_access_review_snapshot,
    rehearse_sqlite_backup_restore,
    review_handle_capacity,
    review_registry_retention,
    sign_verification_report,
    verify_signed_report,
)
from saurus_registry.serialization import (
    RECORD_SCHEMA_VERSION,
    deserialize_block_record,
    digest_payload,
    serialize_block_record,
)
from stegosaurus.audio.attribution import BlockAttributionRecord
from stegosaurus.audio.attribution_core.models import AttributionRecord
from stegosaurus.audio.transport import CarrierPlan


FIXTURE_PATH = Path(__file__).with_name("fixtures") / "attribution-record-v1.json"
NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)


def _record(handle: bytes) -> BlockAttributionRecord:
    """Build a compact structurally valid private block record."""

    plan = CarrierPlan(4, 6, (0, 1))
    private = AttributionRecord(handle, plan, ((0, 1), (2, 3), (4, 5), (6, 7)), 16000)
    return BlockAttributionRecord(handle, 480000, 16000, (private,), 480000)


def _service(handles: list[bytes] | None = None) -> tuple[RegistryService, InMemoryRegistryRepository]:
    """Create deterministic service seams and its observable repository."""

    identifiers = count(1)
    handle_values = iter(handles or [b"\x01\x02\x03\x04"])
    repository = InMemoryRegistryRepository()
    service = RegistryService(
        repository,
        clock=lambda: NOW,
        identifier_factory=lambda: f"id-{next(identifiers)}",
        handle_factory=lambda: next(handle_values),
    )
    return service, repository


def _tenant_and_song(service: RegistryService, name: str = "Northline") -> tuple[str, str]:
    """Register one deterministic tenant and source song."""

    tenant = service.register_tenant(name, "actor-1", f"request-{name}-tenant")
    song = service.register_song(
        tenant.tenant_id,
        "Night Drive",
        "sha256:source",
        16000,
        480000,
        "clean-localizer-v1",
        "actor-1",
        f"request-{name}-song",
    )
    return tenant.tenant_id, song.song_id


def _api_headers(tenant_id: str, request_id: str, *, mutating: bool) -> dict[str, str]:
    """Build deterministic API identity headers."""

    headers = {"X-Saurus-Tenant": tenant_id, "X-Saurus-Actor": "actor-1"}
    headers["Idempotency-Key" if mutating else "X-Request-ID"] = request_id
    return headers


def _json_response(response) -> dict:
    """Decode one JSON API response body."""

    return json.loads(response.body.decode("utf-8"))


def _api_body(**values) -> bytes:
    """Encode one JSON API request body."""

    return json.dumps(values, sort_keys=True).encode("utf-8")


def _sqlite_service(
    path: Path,
    handles: list[bytes] | None = None,
) -> tuple[RegistryService, SQLiteRegistryRepository]:
    """Create one deterministic registry service backed by a SQLite file."""

    identifiers = count(1)
    handle_values = iter(handles or [b"\x01\x02\x03\x04"])
    repository = SQLiteRegistryRepository(path)
    service = RegistryService(
        repository,
        clock=lambda: NOW,
        identifier_factory=lambda: f"id-{next(identifiers)}",
        handle_factory=lambda: next(handle_values),
    )
    return service, repository


def test_canonical_record_matches_golden_fixture() -> None:
    """Keep record serialization stable and reversible across adapters."""

    expected = FIXTURE_PATH.read_bytes().strip()
    payload = serialize_block_record(_record(b"\x01\x02\x03\x04"))

    assert payload == expected
    assert serialize_block_record(deserialize_block_record(payload)) == expected
    assert digest_payload(payload) == "2b309665b8f828d07789b55ea39856c59f6fd873187e3d1edabbc03ce8de6b75"


def test_registry_retries_tenant_handle_collision_and_allows_other_tenant() -> None:
    """Retry an atomic same-tenant collision without creating global handle coupling."""

    first = b"\x10\x00\x00\x01"
    second = b"\x10\x00\x00\x02"
    service, _ = _service([first, first, second, first])
    tenant_a, song_a = _tenant_and_song(service, "A")
    export_a1 = service.reserve_export(tenant_a, song_a, "A1", "actor-a", "request-a1")
    export_a2 = service.reserve_export(tenant_a, song_a, "A2", "actor-a", "request-a2")
    tenant_b, song_b = _tenant_and_song(service, "B")
    export_b = service.reserve_export(tenant_b, song_b, "B1", "actor-b", "request-b1")

    assert (export_a1.handle, export_a2.handle, export_b.handle) == (first, second, first)


def test_registry_handle_capacity_review_matches_threat_model_note() -> None:
    """Quantify four-byte collision pressure without changing codec claims."""

    review = review_handle_capacity(1_000_000)
    wider = review_handle_capacity(1_000_000, handle_bytes=CURRENT_HANDLE_BYTES + 1)

    assert isinstance(review, HandleCapacityReview)
    assert review.handle_bytes == 4
    assert review.namespace_size == 4_294_967_296
    assert review.fresh_collision_probability == pytest.approx(0.00023283064365386963)
    assert review.any_collision_probability > 0.999
    assert review.codec_compatible
    assert not review.migration_required
    assert review.recommendation == "keep atomic collision retry and monitor issuance attempts"
    assert wider.migration_required
    assert wider.recommendation == "requires codec-version and migration evidence before use"


def test_registry_handle_capacity_review_validates_inputs() -> None:
    """Reject capacity reviews that would hide invalid launch assumptions."""

    with pytest.raises(ValueError, match="projected_tenant_handles"):
        review_handle_capacity(-1)
    with pytest.raises(ValueError, match="handle_bytes"):
        review_handle_capacity(1, handle_bytes=0)
    with pytest.raises(ValueError, match="handle_bytes"):
        review_handle_capacity(1, handle_bytes=True)


def test_registry_finalizes_lineage_and_preserves_revoked_verification_record() -> None:
    """Activate parent and child records, then preserve historical verification after revocation."""

    parent_handle = b"\x20\x00\x00\x01"
    child_handle = b"\x20\x00\x00\x02"
    service, repository = _service([parent_handle, child_handle])
    tenant_id, song_id = _tenant_and_song(service)
    parent = service.reserve_export(tenant_id, song_id, "Parent", "actor-1", "request-parent")
    parent = service.finalize_export(
        tenant_id,
        parent.export_id,
        serialize_block_record(_record(parent_handle)),
        "actor-1",
        "request-parent-finalize",
    )
    child = service.reserve_export(
        tenant_id,
        song_id,
        "Child",
        "actor-1",
        "request-child",
        parent.export_id,
    )
    child = service.finalize_export(
        tenant_id,
        child.export_id,
        serialize_block_record(_record(child_handle)),
        "actor-1",
        "request-child-finalize",
    )

    assert parent.state is ExportState.ACTIVE
    assert tuple(item.export_id for item in service.lineage(tenant_id, child.export_id)) == (
        parent.export_id,
        child.export_id,
    )
    revoked = service.revoke_export(tenant_id, child.export_id, "actor-1", "request-revoke")
    assert revoked.state is ExportState.REVOKED
    assert service.verification_record(tenant_id, child.export_id).payload == serialize_block_record(_record(child_handle))
    assert [event.action for event in repository.events(tenant_id)][-1] == "export.revoked"


def test_registry_rejects_cross_tenant_access_and_mismatched_record() -> None:
    """Keep export reads private and reject a retained record for another handle."""

    service, _ = _service([b"\x30\x00\x00\x01"])
    tenant_a, song_a = _tenant_and_song(service, "A")
    tenant_b, _ = _tenant_and_song(service, "B")
    export = service.reserve_export(tenant_a, song_a, "A1", "actor-a", "request-a1")

    with pytest.raises(ValueError, match="not registered for tenant"):
        service.resolve_export(tenant_b, export.export_id)
    with pytest.raises(ValueError, match="does not match"):
        service.finalize_export(
            tenant_a,
            export.export_id,
            serialize_block_record(_record(b"\x30\x00\x00\x02")),
            "actor-a",
            "request-bad-record",
        )


def test_registry_failed_reservation_has_no_verification_record() -> None:
    """Retain a failed system event without inventing usable audio evidence."""

    service, _ = _service([b"\x40\x00\x00\x01"])
    tenant_id, song_id = _tenant_and_song(service)
    export = service.reserve_export(tenant_id, song_id, "Failed", "actor-1", "request-reserve")
    failed = service.fail_export(tenant_id, export.export_id, "clean gate failed", "actor-1", "request-fail")

    assert failed.state is ExportState.FAILED
    with pytest.raises(ValueError, match="does not have"):
        service.verification_record(tenant_id, export.export_id)


def test_registry_reconciliation_expires_only_stale_reserved_exports() -> None:
    """Fail stale reservations without touching active or fresh exports."""

    identifiers = count(1)
    clock_values = iter(
        (
            NOW,
            NOW,
            NOW,
            NOW,
            NOW,
            NOW,
            NOW,
            NOW,
            NOW,
            NOW,
            NOW + timedelta(hours=2),
            NOW + timedelta(hours=2),
        )
    )
    repository = InMemoryRegistryRepository()
    service = RegistryService(
        repository,
        clock=lambda: next(clock_values),
        identifier_factory=lambda: f"id-{next(identifiers)}",
        handle_factory=iter([b"\x41\x00\x00\x01", b"\x41\x00\x00\x02", b"\x41\x00\x00\x03"]).__next__,
    )
    tenant_id, song_id = _tenant_and_song(service)
    stale = service.reserve_export(tenant_id, song_id, "Stale", "actor-1", "request-stale")
    active = service.reserve_export(tenant_id, song_id, "Active", "actor-1", "request-active")
    active = service.finalize_export(
        tenant_id,
        active.export_id,
        serialize_block_record(_record(active.handle)),
        "actor-1",
        "request-active-finalize",
    )
    fresh = service.reserve_export(tenant_id, song_id, "Fresh", "actor-1", "request-fresh")
    later = NOW + timedelta(hours=1)

    result = expire_stale_reserved_exports(
        repository,
        tenant_id=tenant_id,
        song_id=song_id,
        older_than_utc=NOW + timedelta(hours=1),
        now_utc=later,
        actor_id="system",
        request_id="request-expiry",
        event_id_factory=lambda: "expiry-event-1",
    )

    assert result.export_ids == (stale.export_id,)
    assert repository.export(tenant_id, stale.export_id).state is ExportState.FAILED
    assert repository.export(tenant_id, active.export_id).state is ExportState.ACTIVE
    assert repository.export(tenant_id, fresh.export_id).state is ExportState.RESERVED
    assert repository.events(tenant_id)[-1].action == "export.reservation_expired"


def test_registry_operation_schedule_identifies_due_jobs() -> None:
    """Track scheduled registry operations without launching a background daemon."""

    start = NOW
    schedule = default_registry_operations(start)
    disabled = ScheduledRegistryOperation("disabled-job", timedelta(minutes=1), start, enabled=False)
    due = due_registry_operations(schedule + (disabled,), start + timedelta(minutes=20))
    advanced = mark_registry_operation_run(due[0], start + timedelta(minutes=20))

    assert [operation.name for operation in schedule] == [
        "expire-stale-reservations",
        "backup-restore-rehearsal",
        "record-key-rotation-rehearsal",
    ]
    assert [operation.name for operation in due] == ["expire-stale-reservations"]
    assert advanced.next_due_utc == start + timedelta(minutes=35)


def test_registry_operation_schedule_validates_inputs() -> None:
    """Reject schedules that would hide unsafe operational assumptions."""

    naive = datetime(2026, 10, 12, 12, 0)
    bad_interval = ScheduledRegistryOperation("bad", timedelta(0), NOW)

    with pytest.raises(ValueError, match="start_utc"):
        default_registry_operations(naive)
    with pytest.raises(ValueError, match="interval"):
        due_registry_operations((bad_interval,), NOW)
    with pytest.raises(ValueError, match="now_utc"):
        due_registry_operations((), naive)


def test_registry_tenant_export_manifest_uses_digests_not_private_payloads() -> None:
    """Build a tenant inventory without copying retained attribution records."""

    service, repository = _service([b"\x48\x00\x00\x01", b"\x48\x00\x00\x02"])
    tenant_id, song_id = _tenant_and_song(service)
    active = service.reserve_export(tenant_id, song_id, "Active", "actor-1", "request-active")
    payload = serialize_block_record(_record(active.handle))
    service.finalize_export(tenant_id, active.export_id, payload, "actor-1", "request-finalize")
    failed = service.reserve_export(tenant_id, song_id, "Failed", "actor-1", "request-failed")
    service.fail_export(tenant_id, failed.export_id, "clean gate failed", "actor-1", "request-failed-close")

    manifest = build_tenant_export_manifest(repository, tenant_id, (song_id,), NOW)

    assert isinstance(manifest, TenantExportManifest)
    assert manifest.tenant_id == tenant_id
    assert manifest.song_ids == (song_id,)
    assert manifest.event_count == len(repository.events(tenant_id))
    assert [export.state for export in manifest.exports] == [ExportState.ACTIVE, ExportState.FAILED]
    assert manifest.exports[0].record_digest == digest_payload(payload)
    assert manifest.exports[1].record_digest is None
    assert payload.hex() not in repr(manifest)


def test_registry_tenant_export_manifest_rejects_cross_tenant_song() -> None:
    """Require explicit tenant ownership for manifest song IDs."""

    service, repository = _service([b"\x49\x00\x00\x01"])
    tenant_a, _ = _tenant_and_song(service, "A")
    _, song_b = _tenant_and_song(service, "B")

    with pytest.raises(ValueError, match="song_id is not registered for tenant"):
        build_tenant_export_manifest(repository, tenant_a, (song_b,), NOW)


def test_registry_retention_review_flags_due_exports_without_deleting() -> None:
    """Evaluate retention thresholds as review signals, not destructive actions."""

    service, repository = _service([b"\x4a\x00\x00\x01", b"\x4a\x00\x00\x02"])
    tenant_id, song_id = _tenant_and_song(service)
    active = service.reserve_export(tenant_id, song_id, "Active", "actor-1", "request-active")
    service.finalize_export(tenant_id, active.export_id, serialize_block_record(_record(active.handle)), "actor-1", "request-finalize")
    failed = service.reserve_export(tenant_id, song_id, "Failed", "actor-1", "request-failed")
    service.fail_export(tenant_id, failed.export_id, "clean gate failed", "actor-1", "request-failed-close")
    policy = RegistryRetentionPolicy(active_retention_days=31, inactive_retention_days=1)

    decisions = review_registry_retention(repository, tenant_id, (song_id,), NOW + timedelta(days=2), policy)
    held = review_registry_retention(
        repository,
        tenant_id,
        (song_id,),
        NOW + timedelta(days=2),
        RegistryRetentionPolicy(active_retention_days=31, inactive_retention_days=1, legal_hold=True),
    )

    assert [decision.action for decision in decisions] == [RetentionAction.KEEP, RetentionAction.REVIEW]
    assert decisions[1].reason == "retention threshold reached"
    assert [decision.action for decision in held] == [RetentionAction.HOLD, RetentionAction.HOLD]
    assert repository.export(tenant_id, failed.export_id).state is ExportState.FAILED


def test_registry_retention_review_validates_policy_and_scope() -> None:
    """Reject retention reviews with unsafe thresholds or cross-tenant songs."""

    service, repository = _service([b"\x4b\x00\x00\x01"])
    tenant_a, _ = _tenant_and_song(service, "A")
    _, song_b = _tenant_and_song(service, "B")

    with pytest.raises(ValueError, match="active_retention_days"):
        RegistryRetentionPolicy(active_retention_days=-1, inactive_retention_days=1)
    with pytest.raises(ValueError, match="inactive_retention_days"):
        RegistryRetentionPolicy(active_retention_days=1, inactive_retention_days=True)
    with pytest.raises(ValueError, match="song_id is not registered for tenant"):
        review_registry_retention(repository, tenant_a, (song_b,), NOW, RegistryRetentionPolicy(1, 1))


def test_registry_metrics_snapshot_tracks_launch_gate_values() -> None:
    """Compute registry metrics from tenant exports and audit events."""

    service, repository = _service([b"\x4c\x00\x00\x01", b"\x4c\x00\x00\x01", b"\x4c\x00\x00\x02", b"\x4c\x00\x00\x03"])
    tenant_id, song_id = _tenant_and_song(service)
    active = service.reserve_export(tenant_id, song_id, "Active", "actor-1", "request-active")
    service.finalize_export(tenant_id, active.export_id, serialize_block_record(_record(active.handle)), "actor-1", "request-finalize")
    failed = service.reserve_export(tenant_id, song_id, "Failed", "actor-1", "request-failed")
    service.fail_export(tenant_id, failed.export_id, "clean gate failed", "actor-1", "request-failed-close")
    stale = service.reserve_export(tenant_id, song_id, "Stale", "actor-1", "request-stale")
    expire_stale_reserved_exports(
        repository,
        tenant_id=tenant_id,
        song_id=song_id,
        older_than_utc=NOW + timedelta(minutes=1),
        now_utc=NOW + timedelta(hours=1),
        actor_id="system",
        request_id="request-expiry",
        event_id_factory=lambda: "metrics-expiry",
    )

    snapshot = registry_metrics_snapshot(repository, tenant_id, (song_id,))

    assert isinstance(snapshot, RegistryMetricsSnapshot)
    assert repository.export(tenant_id, stale.export_id).state is ExportState.FAILED
    assert snapshot.export_count == 3
    assert (snapshot.active_count, snapshot.failed_count, snapshot.reserved_count) == (1, 2, 0)
    assert snapshot.finalize_rate == pytest.approx(1 / 3)
    assert snapshot.reconciliation_rate == pytest.approx(1 / 3)
    assert snapshot.audit_event_count == len(repository.events(tenant_id))
    assert snapshot.audit_identity_rate == 1.0
    assert snapshot.handle_collision_count == 1
    assert snapshot.issuance_attempt_count == 4
    assert snapshot.issuance_attempts_per_active_export == pytest.approx(4.0)


def test_registry_metrics_snapshot_validates_tenant_scope() -> None:
    """Reject metrics requests for songs outside the tenant boundary."""

    service, repository = _service([b"\x4d\x00\x00\x01"])
    tenant_a, _ = _tenant_and_song(service, "A")
    _, song_b = _tenant_and_song(service, "B")

    with pytest.raises(ValueError, match="song_id is not registered for tenant"):
        registry_metrics_snapshot(repository, tenant_a, (song_b,))
    with pytest.raises(ValueError, match="song_ids"):
        registry_metrics_snapshot(repository, tenant_a, ())


def test_registry_api_metrics_snapshot_tracks_latency_and_bundle_bounds() -> None:
    """Compute API latency and bundle-size launch metrics from observations."""

    service, repository = _service([b"\x4e\x00\x00\x01", b"\x4e\x00\x00\x02", b"\x4e\x00\x00\x03"])
    tenant_id, song_id = _tenant_and_song(service)
    first = service.reserve_export(tenant_id, song_id, "First", "actor-1", "request-first")
    second = service.reserve_export(tenant_id, song_id, "Second", "actor-1", "request-second")
    service.finalize_export(tenant_id, first.export_id, serialize_block_record(_record(first.handle)), "actor-1", "request-first-finalize")
    service.finalize_export(tenant_id, second.export_id, serialize_block_record(_record(second.handle)), "actor-1", "request-second-finalize")
    api = RegistryApi(service, repository, clock=lambda: NOW)

    song_response = api.handle(ApiRequest("GET", f"/v1/songs/{song_id}", _api_headers(tenant_id, "request-song-read", mutating=False)))
    bundle_response = api.handle(ApiRequest("GET", f"/v1/songs/{song_id}/verification-bundle?limit=1", _api_headers(tenant_id, "request-bundle-read", mutating=False)))
    missing_response = api.handle(ApiRequest("GET", "/v1/missing", _api_headers(tenant_id, "request-missing-read", mutating=False)))
    bundle_body = _json_response(bundle_response)
    observations = (
        observe_registry_api_response("GET /v1/songs/{song_id}", song_response, 12.0),
        observe_registry_api_response(
            "GET /v1/songs/{song_id}/verification-bundle",
            bundle_response,
            40.0,
            bundle_record_count=bundle_body["returned_count"],
            bundle_truncated=bundle_body["truncated"],
        ),
        observe_registry_api_response("GET /v1/missing", missing_response, 8.0),
    )

    snapshot = registry_api_metrics_snapshot(observations)

    assert isinstance(snapshot, RegistryApiMetricsSnapshot)
    assert bundle_body["returned_count"] == 1
    assert snapshot.observation_count == 3
    assert snapshot.p50_latency_ms == pytest.approx(12.0)
    assert snapshot.p95_latency_ms == pytest.approx(40.0)
    assert snapshot.max_response_bytes == len(bundle_response.body)
    assert snapshot.max_bundle_record_count == 1
    assert snapshot.truncated_bundle_count == 1
    assert snapshot.error_rate == pytest.approx(1 / 3)


def test_registry_api_metrics_snapshot_validates_observations() -> None:
    """Reject invalid API metric observations and make empty snapshots stable."""

    empty = registry_api_metrics_snapshot(())

    assert empty.observation_count == 0
    assert empty.p95_latency_ms == 0.0
    with pytest.raises(ValueError, match="route"):
        RegistryApiObservation("", 200, 1.0, 10)
    with pytest.raises(ValueError, match="status"):
        RegistryApiObservation("GET /v1/songs", 99, 1.0, 10)
    with pytest.raises(ValueError, match="latency_ms"):
        RegistryApiObservation("GET /v1/songs", 200, -1.0, 10)
    with pytest.raises(ValueError, match="bundle_record_count"):
        RegistryApiObservation("GET /v1/songs", 200, 1.0, 10, bundle_record_count=-1)


def test_registry_access_review_snapshot_summarizes_authorization_probes() -> None:
    """Measure unauthorized and cross-tenant access probes from API responses."""

    service, repository = _service([b"\x4f\x00\x00\x01"])
    tenant_a, song_a = _tenant_and_song(service, "A")
    tenant_b, _ = _tenant_and_song(service, "B")
    export = service.reserve_export(tenant_a, song_a, "A export", "actor-a", "request-a-reserve")
    service.finalize_export(tenant_a, export.export_id, serialize_block_record(_record(export.handle)), "actor-a", "request-a-finalize")
    authenticator = HmacBearerAuthenticator(b"access-secret", clock=lambda: NOW)
    read_token = authenticator.issue_token(tenant_a, "actor-token", ("registry.read",), NOW.replace(year=2027))
    api = RegistryApi(service, repository, authenticator=authenticator, clock=lambda: NOW)

    role_denied = api.handle(ApiRequest("GET", f"/v1/exports/{export.export_id}/verification-record", {"Authorization": read_token, "X-Request-ID": "request-role-denied"}))
    cross_tenant = RegistryApi(service, repository, clock=lambda: NOW).handle(ApiRequest("GET", f"/v1/exports/{export.export_id}", _api_headers(tenant_b, "request-cross-tenant", mutating=False)))
    probes = (
        RegistryAccessProbe("read token denied verification record", RegistryAccessProbeKind.ROLE_DENIED, 403, role_denied.status),
        RegistryAccessProbe("tenant b denied tenant a export", RegistryAccessProbeKind.CROSS_TENANT, 404, cross_tenant.status),
    )

    snapshot = registry_access_review_snapshot(probes)
    failing = registry_access_review_snapshot(probes + (RegistryAccessProbe("bad expectation", RegistryAccessProbeKind.UNAUTHORIZED, 403, 200),))

    assert isinstance(snapshot, RegistryAccessReviewSnapshot)
    assert snapshot.probe_count == 2
    assert snapshot.passed_count == 2
    assert snapshot.failed_count == 0
    assert snapshot.cross_tenant_probe_count == 1
    assert snapshot.pass_rate == 1.0
    assert failing.failed_probe_names == ("bad expectation",)
    with pytest.raises(ValueError, match="name"):
        RegistryAccessProbe("", RegistryAccessProbeKind.UNAUTHORIZED, 403, 403)
    with pytest.raises(ValueError, match="observed_status"):
        RegistryAccessProbe("bad status", RegistryAccessProbeKind.UNAUTHORIZED, 403, 99)


def test_registry_launch_decision_uses_declared_metrics() -> None:
    """Evaluate registry launch gates from measured snapshots and thresholds."""

    thresholds = RegistryLaunchThresholds(
        minimum_finalize_rate=0.9,
        maximum_reconciliation_rate=0.1,
        minimum_audit_identity_rate=1.0,
        minimum_access_probe_pass_rate=1.0,
        maximum_access_probe_failures=0,
        maximum_handle_collision_count=0,
        maximum_issuance_attempts_per_active_export=1.25,
        maximum_p95_latency_ms=100.0,
        maximum_api_error_rate=0.0,
        maximum_response_bytes=2_000,
        maximum_bundle_record_count=10,
        maximum_truncated_bundle_count=0,
        maximum_backup_restore_ms=500.0,
    )
    passing_metrics = RegistryMetricsSnapshot("tenant-1", 1, 10, 0, 9, 1, 0, 0.9, 0.0, 20, 1.0, 0, 10, 10 / 9)
    passing_access = RegistryAccessReviewSnapshot(2, 2, 0, 1, 1, 1.0, ())
    passing_api = RegistryApiMetricsSnapshot(3, 12.0, 40.0, 1_200, 5, 0, 0.0)
    passing_backup = BackupRestoreRehearsalResult(Path("backup.sqlite3"), Path("restored.sqlite3"), 50.0, 70.0, 120.0)
    failing_metrics = RegistryMetricsSnapshot("tenant-1", 1, 10, 0, 7, 3, 0, 0.7, 0.2, 20, 0.95, 2, 14, 2.0)
    failing_access = RegistryAccessReviewSnapshot(2, 1, 1, 1, 1, 0.5, ("tenant b denied tenant a export",))
    failing_api = RegistryApiMetricsSnapshot(3, 12.0, 180.0, 3_000, 12, 1, 0.2)
    failing_backup = BackupRestoreRehearsalResult(Path("backup.sqlite3"), Path("restored.sqlite3"), 200.0, 400.0, 600.0)

    accepted = evaluate_registry_launch(passing_metrics, passing_access, passing_api, passing_backup, thresholds)
    rejected = evaluate_registry_launch(failing_metrics, failing_access, failing_api, failing_backup, thresholds)
    record = record_registry_launch_decision(passing_metrics, passing_access, passing_api, passing_backup, thresholds, "ops-reviewer", NOW, "registry gates pass")

    assert accepted.go
    assert accepted.reasons == ()
    assert not rejected.go
    assert "finalize" in rejected.reasons[0]
    assert "access probe" in rejected.reasons[3]
    assert "handle collision" in rejected.reasons[5]
    assert "backup restore" in rejected.reasons[-1]
    assert isinstance(record, RegistryLaunchDecisionRecord)
    assert record.decision.go
    assert record.reviewer_id == "ops-reviewer"
    with pytest.raises(ValueError, match="minimum_finalize_rate"):
        RegistryLaunchThresholds(-0.1, 0.1, 1.0, 1.0, 0, 0, 1.25, 100.0, 0.0, 2_000, 10, 0, 500.0)
    with pytest.raises(ValueError, match="summary"):
        record_registry_launch_decision(passing_metrics, passing_access, passing_api, passing_backup, thresholds, "ops-reviewer", NOW, "")


def test_sqlite_registry_migrates_and_persists_records(tmp_path: Path) -> None:
    """Reopen a durable registry and retain active exports, records, and events."""

    database_path = tmp_path / "registry.sqlite3"
    service, repository = _sqlite_service(database_path, [b"\x50\x00\x00\x01"])
    tenant_id, song_id = _tenant_and_song(service)
    export = service.reserve_export(tenant_id, song_id, "Durable", "actor-1", "request-reserve")
    active = service.finalize_export(
        tenant_id,
        export.export_id,
        serialize_block_record(_record(export.handle)),
        "actor-1",
        "request-finalize",
    )
    reopened = SQLiteRegistryRepository(database_path)

    assert repository.schema_version() == CURRENT_SCHEMA_VERSION
    assert reopened.export(tenant_id, active.export_id) == active
    assert reopened.attribution_record(tenant_id, active.export_id).payload == serialize_block_record(_record(active.handle))
    assert [event.action for event in reopened.events(tenant_id)] == [
        "tenant.registered",
        "song.registered",
        "export.reserved",
        "export.finalized",
    ]


def test_sqlite_registry_encrypts_private_records_with_key_metadata(tmp_path: Path) -> None:
    """Store encrypted retained records at rest and require the matching cipher."""

    database_path = tmp_path / "registry.sqlite3"
    cipher = LocalHmacStreamCipher("test-key-1", b"k" * 32)
    repository = SQLiteRegistryRepository(database_path, cipher=cipher)
    service = RegistryService(repository, clock=lambda: NOW)
    tenant = service.register_tenant("Encrypted", "actor-1", "request-tenant")
    song = service.register_song(
        tenant.tenant_id,
        "Night Drive",
        "sha256:source",
        16000,
        480000,
        "v1",
        "actor-1",
        "request-song",
    )
    export = service.reserve_export(tenant.tenant_id, song.song_id, "Recipient", "actor-1", "request-reserve")
    payload = serialize_block_record(_record(export.handle))
    active = service.finalize_export(tenant.tenant_id, export.export_id, payload, "actor-1", "request-finalize")

    with sqlite3.connect(database_path) as connection:
        stored = connection.execute(
            "SELECT payload, key_id, encryption_algorithm, nonce, auth_tag FROM attribution_records WHERE export_id = ?",
            (active.export_id,),
        ).fetchone()
    reopened = SQLiteRegistryRepository(database_path, cipher=cipher)

    assert stored[0] != payload
    assert stored[1] == "test-key-1"
    assert stored[2] == "local-hmac-sha256-stream-v1"
    assert stored[3] and stored[4]
    assert reopened.attribution_record(tenant.tenant_id, active.export_id).payload == payload
    with pytest.raises(ValueError, match="requires a configured cipher"):
        SQLiteRegistryRepository(database_path).attribution_record(tenant.tenant_id, active.export_id)


def test_sqlite_backup_restore_and_key_rotation_rehearsal(tmp_path: Path) -> None:
    """Copy, restore, and re-envelope retained records without losing verification data."""

    database_path = tmp_path / "registry.sqlite3"
    backup_path = tmp_path / "backup.sqlite3"
    restored_path = tmp_path / "restored.sqlite3"
    old_cipher = LocalHmacStreamCipher("old-key", b"o" * 32)
    new_cipher = LocalHmacStreamCipher("new-key", b"n" * 32)
    repository = SQLiteRegistryRepository(database_path, cipher=old_cipher)
    service = RegistryService(repository, clock=lambda: NOW)
    tenant = service.register_tenant("Backup", "actor-1", "request-tenant")
    song = service.register_song(tenant.tenant_id, "Night Drive", "sha256:source", 16000, 480000, "v1", "actor-1", "request-song")
    export = service.reserve_export(tenant.tenant_id, song.song_id, "Recipient", "actor-1", "request-reserve")
    payload = serialize_block_record(_record(export.handle))
    active = service.finalize_export(tenant.tenant_id, export.export_id, payload, "actor-1", "request-finalize")

    rehearsal = rehearse_sqlite_backup_restore(
        database_path,
        backup_path,
        restored_path,
        clock=iter((1.0, 1.25, 1.75)).__next__,
    )
    restored = SQLiteRegistryRepository(restored_path, cipher=old_cipher)

    assert isinstance(rehearsal, BackupRestoreRehearsalResult)
    assert rehearsal.backup_elapsed_ms == pytest.approx(250)
    assert rehearsal.restore_elapsed_ms == pytest.approx(500)
    assert rehearsal.total_elapsed_ms == pytest.approx(750)
    assert restored.attribution_record(tenant.tenant_id, active.export_id).payload == payload
    result = rotate_sqlite_record_key(restored_path, old_cipher, new_cipher)
    assert result.rotated_count == 1
    assert result.original_key_ids == ("old-key",)
    assert result.new_key_id == "new-key"
    with pytest.raises(ValueError, match="does not match cipher"):
        SQLiteRegistryRepository(restored_path, cipher=old_cipher).attribution_record(tenant.tenant_id, active.export_id)
    rotated = SQLiteRegistryRepository(restored_path, cipher=new_cipher)
    assert rotated.attribution_record(tenant.tenant_id, active.export_id).payload == payload


def test_sqlite_registry_keeps_tenant_scope_after_reopen(tmp_path: Path) -> None:
    """Reject cross-tenant durable reads while allowing each tenant its own handle."""

    service, _ = _sqlite_service(tmp_path / "registry.sqlite3", [b"\x60\x00\x00\x01", b"\x60\x00\x00\x01"])
    tenant_a, song_a = _tenant_and_song(service, "A")
    export_a = service.reserve_export(tenant_a, song_a, "A1", "actor-a", "request-a1")
    tenant_b, song_b = _tenant_and_song(service, "B")
    export_b = service.reserve_export(tenant_b, song_b, "B1", "actor-b", "request-b1")
    reopened = SQLiteRegistryRepository(tmp_path / "registry.sqlite3")

    assert reopened.export(tenant_a, export_a.export_id) == export_a
    assert reopened.export(tenant_b, export_b.export_id) == export_b
    assert reopened.export(tenant_b, export_a.export_id) is None
    assert export_a.handle == export_b.handle


def test_sqlite_registry_gate_two_tenants_finalize_and_reject_cross_access(tmp_path: Path) -> None:
    """Prove two tenants can complete active exports without cross-access."""

    service, _ = _sqlite_service(
        tmp_path / "registry.sqlite3",
        [b"\x61\x00\x00\x01", b"\x61\x00\x00\x01"],
    )
    tenant_a, song_a = _tenant_and_song(service, "A")
    tenant_b, song_b = _tenant_and_song(service, "B")
    reserved_a = service.reserve_export(tenant_a, song_a, "A1", "actor-a", "request-a-reserve")
    reserved_b = service.reserve_export(tenant_b, song_b, "B1", "actor-b", "request-b-reserve")
    payload_a = serialize_block_record(_record(reserved_a.handle))
    payload_b = serialize_block_record(_record(reserved_b.handle))

    active_a = service.finalize_export(tenant_a, reserved_a.export_id, payload_a, "actor-a", "request-a-finalize")
    active_b = service.finalize_export(tenant_b, reserved_b.export_id, payload_b, "actor-b", "request-b-finalize")

    assert service.resolve_export(tenant_a, active_a.export_id).state is ExportState.ACTIVE
    assert service.resolve_export(tenant_b, active_b.export_id).state is ExportState.ACTIVE
    assert service.verification_record(tenant_a, active_a.export_id).payload == payload_a
    assert service.verification_record(tenant_b, active_b.export_id).payload == payload_b
    with pytest.raises(ValueError, match="not registered for tenant"):
        service.resolve_export(tenant_a, active_b.export_id)
    with pytest.raises(ValueError, match="not registered for tenant"):
        service.verification_record(tenant_b, active_a.export_id)


def test_sqlite_registry_concurrent_same_tenant_handle_reservation(tmp_path: Path) -> None:
    """Let SQLite enforce a one-winner same-tenant handle race transactionally."""

    database_path = tmp_path / "registry.sqlite3"
    service, repository = _sqlite_service(database_path)
    tenant_id, song_id = _tenant_and_song(service)

    def reserve(export_id: str) -> str:
        """Attempt one direct repository reservation from a separate connection."""

        export = ExportRecord(
            export_id,
            tenant_id,
            song_id,
            b"\x70\x00\x00\x01",
            export_id,
            None,
            ExportState.RESERVED,
            NOW,
            NOW,
        )
        SQLiteRegistryRepository(database_path).reserve_export(export)
        return export_id

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(reserve, "race-a"), executor.submit(reserve, "race-b")]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result())
            except HandleConflictError:
                outcomes.append("conflict")

    assert sorted(outcomes) in (["conflict", "race-a"], ["conflict", "race-b"])
    assert len(repository.exports_for_song(tenant_id, song_id)) == 1


def test_sqlite_registry_concurrent_finalization_has_one_winner(tmp_path: Path) -> None:
    """Let exactly one writer activate a reserved export and store its record."""

    database_path = tmp_path / "registry.sqlite3"
    service, repository = _sqlite_service(database_path, [b"\x80\x00\x00\x01"])
    tenant_id, song_id = _tenant_and_song(service)
    reserved = service.reserve_export(tenant_id, song_id, "Race", "actor-1", "request-race")
    active = replace(reserved, state=ExportState.ACTIVE)
    payload = serialize_block_record(_record(active.handle))
    record = StoredAttributionRecord(active.export_id, RECORD_SCHEMA_VERSION, payload, digest_payload(payload), NOW)

    def finalize() -> str:
        """Attempt one direct finalization from a separate connection."""

        SQLiteRegistryRepository(database_path).finalize_export(tenant_id, active, record)
        return "active"

    with ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(finalize), executor.submit(finalize)]
        outcomes = []
        for future in futures:
            try:
                outcomes.append(future.result())
            except ValueError:
                outcomes.append("rejected")

    assert sorted(outcomes) == ["active", "rejected"]
    assert repository.export(tenant_id, active.export_id).state is ExportState.ACTIVE
    assert repository.attribution_record(tenant_id, active.export_id).payload == payload


def test_registry_api_covers_minimal_encode_and_verification_routes() -> None:
    """Exercise the versioned API route surface used by a future desktop backend."""

    service, repository = _service([b"\x90\x00\x00\x01"])
    tenant = service.register_tenant("API Tenant", "actor-1", "request-tenant")
    api = RegistryApi(service, repository, clock=lambda: NOW)
    song_response = api.handle(
        ApiRequest(
            "POST",
            "/v1/songs",
            _api_headers(tenant.tenant_id, "request-song", mutating=True),
            _api_body(
                title="API Song",
                source_digest="sha256:api",
                sample_rate=16000,
                sample_count=480000,
                fingerprint_version="clean-localizer-v1",
            ),
        )
    )
    song_body = _json_response(song_response)
    reserve_response = api.handle(
        ApiRequest(
            "POST",
            f"/v1/songs/{song_body['song']['song_id']}/exports:reserve",
            _api_headers(tenant.tenant_id, "request-reserve", mutating=True),
            _api_body(recipient_label="Recipient"),
        )
    )
    reserve_body = _json_response(reserve_response)
    export_id = reserve_body["export"]["export_id"]
    payload = serialize_block_record(_record(bytes.fromhex(reserve_body["export"]["handle_hex"])))
    finalize_response = api.handle(
        ApiRequest(
            "POST",
            f"/v1/exports/{export_id}:finalize",
            _api_headers(tenant.tenant_id, "request-finalize", mutating=True),
            _api_body(payload_b64=b64encode(payload).decode("ascii")),
        )
    )
    record_response = api.handle(
        ApiRequest(
            "GET",
            f"/v1/exports/{export_id}/verification-record",
            _api_headers(tenant.tenant_id, "request-record", mutating=False),
        )
    )
    lineage_response = api.handle(
        ApiRequest(
            "GET",
            f"/v1/exports/{export_id}/lineage",
            _api_headers(tenant.tenant_id, "request-lineage", mutating=False),
        )
    )

    assert song_response.status == 201
    assert reserve_response.status == 201
    assert _json_response(finalize_response)["export"]["state"] == "active"
    assert _json_response(record_response)["record"]["payload_b64"] == b64encode(payload).decode("ascii")
    assert len(_json_response(lineage_response)["lineage"]) == 1


def test_registry_api_replays_idempotent_mutation_and_rejects_mismatch() -> None:
    """Replay a completed mutation while rejecting key reuse for different input."""

    service, repository = _service([b"\x91\x00\x00\x01", b"\x91\x00\x00\x02"])
    tenant_id, song_id = _tenant_and_song(service)
    api = RegistryApi(service, repository, clock=lambda: NOW)
    request = ApiRequest(
        "POST",
        f"/v1/songs/{song_id}/exports:reserve",
        _api_headers(tenant_id, "request-idempotent-reserve", mutating=True),
        _api_body(recipient_label="Recipient"),
    )
    mismatch = ApiRequest(
        "POST",
        f"/v1/songs/{song_id}/exports:reserve",
        _api_headers(tenant_id, "request-idempotent-reserve", mutating=True),
        _api_body(recipient_label="Different recipient"),
    )

    first = api.handle(request)
    replayed = api.handle(request)
    conflict = api.handle(mismatch)

    assert first.body == replayed.body
    assert len(repository.exports_for_song(tenant_id, song_id)) == 1
    assert [event.action for event in repository.events(tenant_id)].count("export.reserved") == 1
    assert (conflict.status, _json_response(conflict)["error"]["code"]) == (409, "conflict")


def test_registry_api_rejects_in_flight_idempotency_duplicate() -> None:
    """Reject a duplicate mutating request before its first response is stored."""

    entered = Event()
    release = Event()

    class BlockingReserveService(RegistryService):
        """Pause reserve dispatch while the API idempotency guard is held."""

        def reserve_export(
            self,
            tenant_id: str,
            song_id: str,
            recipient_label: str,
            actor_id: str,
            request_id: str,
            parent_export_id: str | None = None,
            requested_handle: bytes | None = None,
        ) -> ExportRecord:
            """Block one reservation until the test releases it."""

            entered.set()
            if not release.wait(2):
                raise TimeoutError("test did not release blocked reservation")
            return super().reserve_export(
                tenant_id,
                song_id,
                recipient_label,
                actor_id,
                request_id,
                parent_export_id,
                requested_handle,
            )

    repository = InMemoryRegistryRepository()
    service = BlockingReserveService(repository, clock=lambda: NOW, handle_factory=lambda: b"\x93\x00\x00\x01")
    tenant_id, song_id = _tenant_and_song(service)
    api = RegistryApi(service, repository, clock=lambda: NOW)
    request = ApiRequest(
        "POST",
        f"/v1/songs/{song_id}/exports:reserve",
        _api_headers(tenant_id, "request-inflight-reserve", mutating=True),
        _api_body(recipient_label="Recipient"),
    )

    with ThreadPoolExecutor(max_workers=1) as executor:
        first_future = executor.submit(api.handle, request)
        assert entered.wait(2)
        duplicate = api.handle(request)
        release.set()
        first = first_future.result(timeout=2)
    replayed = api.handle(request)

    assert first.status == 201
    assert duplicate.status == 409
    assert _json_response(duplicate)["error"]["message"] == "idempotency key is already in flight"
    assert replayed.body == first.body
    assert len(repository.exports_for_song(tenant_id, song_id)) == 1


def test_sqlite_registry_replays_idempotency_after_api_restart(tmp_path: Path) -> None:
    """Persist successful idempotency responses across router and service restarts."""

    database_path = tmp_path / "registry.sqlite3"
    service, repository = _sqlite_service(database_path, [b"\x92\x00\x00\x01", b"\x92\x00\x00\x02"])
    tenant_id, song_id = _tenant_and_song(service)
    api = RegistryApi(service, repository, clock=lambda: NOW)
    request = ApiRequest(
        "POST",
        f"/v1/songs/{song_id}/exports:reserve",
        _api_headers(tenant_id, "request-durable-replay", mutating=True),
        _api_body(recipient_label="Durable recipient"),
    )
    first = api.handle(request)
    reopened = SQLiteRegistryRepository(database_path)
    restarted = RegistryApi(RegistryService(reopened, clock=lambda: NOW), reopened, clock=lambda: NOW)

    replayed = restarted.handle(request)

    assert first.body == replayed.body
    assert len(reopened.exports_for_song(tenant_id, song_id)) == 1
    assert reopened.schema_version() == CURRENT_SCHEMA_VERSION


def test_registry_api_returns_structured_validation_errors() -> None:
    """Report missing headers, unknown routes, and invalid payloads as JSON errors."""

    service, repository = _service([b"\xa0\x00\x00\x01"])
    tenant_id, song_id = _tenant_and_song(service)
    export = service.reserve_export(tenant_id, song_id, "API Error", "actor-1", "request-reserve")
    api = RegistryApi(service, repository, clock=lambda: NOW)
    missing_id = api.handle(ApiRequest("POST", "/v1/songs", {"X-Saurus-Tenant": tenant_id, "X-Saurus-Actor": "actor-1"}, b"{}"))
    missing_route = api.handle(ApiRequest("GET", "/v1/not-real", _api_headers(tenant_id, "request-missing", mutating=False)))
    bad_payload = api.handle(
        ApiRequest(
            "POST",
            f"/v1/exports/{export.export_id}:finalize",
            _api_headers(tenant_id, "request-bad-payload", mutating=True),
            _api_body(payload_b64="not base64"),
        )
    )

    assert (missing_id.status, _json_response(missing_id)["error"]["code"]) == (400, "validation")
    assert (missing_route.status, _json_response(missing_route)["error"]["code"]) == (404, "not_found")
    assert (bad_payload.status, _json_response(bad_payload)["error"]["code"]) == (400, "validation")


def test_registry_api_authenticates_and_authorizes_bearer_tokens() -> None:
    """Require signed tenant-scoped tokens and route-specific registry roles."""

    service, repository = _service([b"\xb0\x00\x00\x01"])
    tenant = service.register_tenant("Auth Tenant", "actor-1", "request-tenant")
    authenticator = HmacBearerAuthenticator(b"auth-secret", clock=lambda: NOW)
    api = RegistryApi(service, repository, authenticator=authenticator, clock=lambda: NOW)
    write_token = authenticator.issue_token(
        tenant.tenant_id,
        "actor-token",
        ("registry.write",),
        NOW.replace(year=2027),
    )
    read_token = authenticator.issue_token(
        tenant.tenant_id,
        "actor-token",
        ("registry.read",),
        NOW.replace(year=2027),
    )
    expired_token = authenticator.issue_token(
        tenant.tenant_id,
        "actor-token",
        ("registry.write",),
        NOW.replace(year=2025),
    )

    good = api.handle(
        ApiRequest(
            "POST",
            "/v1/songs",
            {"Authorization": write_token, "Idempotency-Key": "request-song"},
            _api_body(
                title="Auth Song",
                source_digest="sha256:auth",
                sample_rate=16000,
                sample_count=480000,
                fingerprint_version="v1",
            ),
        )
    )
    missing_role = api.handle(
        ApiRequest(
            "POST",
            "/v1/songs",
            {"Authorization": read_token, "Idempotency-Key": "request-denied"},
            _api_body(
                title="Denied",
                source_digest="sha256:denied",
                sample_rate=16000,
                sample_count=480000,
                fingerprint_version="v1",
            ),
        )
    )
    expired = api.handle(
        ApiRequest(
            "POST",
            "/v1/songs",
            {"Authorization": expired_token, "Idempotency-Key": "request-expired"},
            _api_body(
                title="Expired",
                source_digest="sha256:expired",
                sample_rate=16000,
                sample_count=480000,
                fingerprint_version="v1",
            ),
        )
    )
    tenant_mismatch = api.handle(
        ApiRequest(
            "POST",
            "/v1/songs",
            {
                "Authorization": write_token,
                "X-Saurus-Tenant": "wrong-tenant",
                "Idempotency-Key": "request-mismatch",
            },
            _api_body(
                title="Mismatch",
                source_digest="sha256:mismatch",
                sample_rate=16000,
                sample_count=480000,
                fingerprint_version="v1",
            ),
        )
    )

    assert good.status == 201
    assert (missing_role.status, _json_response(missing_role)["error"]["code"]) == (403, "authorization")
    assert (expired.status, _json_response(expired)["error"]["message"]) == (403, "authorization token has expired")
    assert (tenant_mismatch.status, _json_response(tenant_mismatch)["error"]["code"]) == (403, "authorization")


def test_registry_api_returns_authorized_bounded_song_verification_bundle() -> None:
    """Return only active retained records for a known song under verify authorization."""

    service, repository = _service([b"\xc0\x00\x00\x01", b"\xc0\x00\x00\x02", b"\xc0\x00\x00\x03"])
    tenant_id, song_id = _tenant_and_song(service)
    first = service.reserve_export(tenant_id, song_id, "First", "actor-1", "request-first")
    second = service.reserve_export(tenant_id, song_id, "Second", "actor-1", "request-second")
    failed = service.reserve_export(tenant_id, song_id, "Failed", "actor-1", "request-failed")
    first_payload = serialize_block_record(_record(first.handle))
    second_payload = serialize_block_record(_record(second.handle))
    service.finalize_export(tenant_id, first.export_id, first_payload, "actor-1", "request-first-finalize")
    service.finalize_export(tenant_id, second.export_id, second_payload, "actor-1", "request-second-finalize")
    service.fail_export(tenant_id, failed.export_id, "clean gate failed", "actor-1", "request-failed-close")
    authenticator = HmacBearerAuthenticator(b"bundle-secret", clock=lambda: NOW)
    verify_token = authenticator.issue_token(tenant_id, "actor-token", ("registry.verify",), NOW.replace(year=2027))
    read_token = authenticator.issue_token(tenant_id, "actor-token", ("registry.read",), NOW.replace(year=2027))
    api = RegistryApi(service, repository, authenticator=authenticator, clock=lambda: NOW)

    allowed = api.handle(
        ApiRequest(
            "GET",
            f"/v1/songs/{song_id}/verification-bundle?limit=1",
            {"Authorization": verify_token, "X-Request-ID": "request-bundle"},
        )
    )
    denied = api.handle(
        ApiRequest(
            "GET",
            f"/v1/songs/{song_id}/verification-bundle?limit=1",
            {"Authorization": read_token, "X-Request-ID": "request-denied-bundle"},
        )
    )
    body = _json_response(allowed)

    assert allowed.status == 200
    assert body["returned_count"] == 1
    assert body["truncated"] is True
    assert body["records"][0]["payload_b64"] == b64encode(first_payload).decode("ascii")
    assert all(export["state"] == "active" for export in body["exports"])
    assert (denied.status, _json_response(denied)["error"]["code"]) == (403, "authorization")


def test_signed_verification_report_uses_safe_wording_and_detects_tampering() -> None:
    """Sign a wording-constrained report without turning labels into blame."""

    payload = build_watermark_report_payload(
        tenant_id="tenant-1",
        export_id="export-1",
        verification_event_id="event-1",
        profile_version="profile-v1",
        outcome="accepted",
        recipient_label="Mixer preview",
        issued_utc=NOW,
    )
    report = sign_verification_report(payload, "report-key-1", b"report-secret")
    tampered = build_watermark_report_payload(
        tenant_id="tenant-1",
        export_id="export-2",
        verification_event_id="event-1",
        profile_version="profile-v1",
        outcome="accepted",
        recipient_label="Mixer preview",
        issued_utc=NOW,
    )

    assert payload.evidence_class == "watermark match"
    assert "leaked" not in payload.result_statement.lower()
    assert "Mixer preview" in payload.user_label_statement
    assert verify_signed_report(report, b"report-secret")
    assert not verify_signed_report(type(report)(tampered, report.key_id, report.signature), b"report-secret")
    with pytest.raises(ValueError, match="must not accuse"):
        type(payload)(
            "tenant-1",
            "export-1",
            "event-1",
            "profile-v1",
            "accepted",
            "watermark match",
            "system fact",
            "The recipient leaked the song.",
            "label",
            NOW,
        )
