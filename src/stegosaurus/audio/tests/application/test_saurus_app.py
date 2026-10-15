"""Test the guided Saurus desktop app engine without opening Tkinter.

The desktop surface is intentionally thin.  These checks cover the part that
matters for application behavior: a user-selected WAV plus registry fields
produces an encoded WAV and private JSON sidecar, then decode mode verifies the
encoded WAV against that retained sidecar.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os

import pytest

from saurus_app.credentials import DesktopCredentialManager, DeviceCredential, MemoryCredentialStore
from saurus_app.local_registry import LocalRegistryConfig, local_registry_backend, local_registry_health
from saurus_app.pending import PendingEncodeLog, PendingEncodeStatus, pending_record_for_encode
from saurus_app.packaging import build_desktop_zipapp
from saurus_app.privacy import scan_text_artifacts
from saurus_app.protected_credentials import ProtectedFileCredentialStore, default_credential_store
from saurus_app.recovery import encode_with_pending_log, pending_summary
from saurus_app.release import launch_check
from saurus_app.registry import RegistryFields, decode_claims, decode_claims_measured, decode_file, default_output_paths, encode_file, inspect_registry_file
from saurus_app.remote_registry import ApiRegistryBackend
from saurus_app.security import review_desktop_secret_posture
from saurus_app.smoke import run_alpha_contract_smoke, run_local_registry_smoke
from saurus_registry import ExportState, HmacBearerAuthenticator, InMemoryRegistryRepository, RegistryApi, RegistryService
from stegosaurus.audio.demo_samples import music_like_sample
from stegosaurus.audio.pilot import write_pcm16_wav


class _DropFinalizeResponseBackend(ApiRegistryBackend):
    """Simulate a network loss after the server accepts finalize once."""

    def _request(self, method: str, path: str, headers: dict[str, str], body: dict[str, object] | None) -> dict[str, object]:
        """Drop the first finalize response after the API has processed it."""

        response = super()._request(method, path, headers, body)
        if method == "POST" and path.endswith(":finalize"):
            raise RuntimeError("simulated network loss after finalize")
        return response


def test_guided_saurus_encode_decode_round_trip(tmp_path) -> None:
    """Encode a clean fixture and verify it with the generated registry sidecar."""

    source_path = tmp_path / "source.wav"
    write_pcm16_wav(source_path, music_like_sample(30))
    output_wav, registry_json = default_output_paths(source_path)

    encoded = encode_file(
        source_path,
        output_wav,
        registry_json,
        RegistryFields("release candidate", "northline promo", "first controlled export"),
    )
    decoded = decode_file(encoded.output_wav, encoded.registry_json)

    assert encoded.output_wav.exists()
    assert encoded.registry_json.exists()
    assert encoded.block_count == 1
    assert decoded.accepted
    assert decoded.recipient == "northline promo"
    assert decoded.project == "release candidate"


def test_desktop_secret_posture_marks_local_demo_secret_as_not_production_ready() -> None:
    """Keep the shared desktop watermark secret out of production posture."""

    posture = review_desktop_secret_posture()

    assert posture.scope == "local-demo-only"
    assert not posture.has_shared_production_secret
    assert not posture.production_ready


def test_guided_saurus_remote_backend_round_trip_uses_recovery_receipt(tmp_path) -> None:
    """Reserve a server handle, finalize remotely, and avoid private receipt records."""

    source_path = tmp_path / "source.wav"
    write_pcm16_wav(source_path, music_like_sample(30))
    output_wav, registry_json = default_output_paths(source_path)
    repository = InMemoryRegistryRepository()
    service = RegistryService(repository)
    tenant = service.register_tenant("Desktop Tenant", "actor-1", "request-tenant")
    backend = ApiRegistryBackend(RegistryApi(service, repository), tenant.tenant_id, "actor-1")

    encoded = encode_file(
        source_path,
        output_wav,
        registry_json,
        RegistryFields("remote release", "northline api", "server issued handle"),
        backend=backend,
    )
    receipt = json.loads(registry_json.read_text(encoding="utf-8"))
    decoded = decode_file(encoded.output_wav, encoded.registry_json, backend=backend)
    event_id = backend.report_verification_result(encoded.registry_json, decoded)

    assert receipt["backend"] == "saurus-registry-api-v1"
    assert "block_record" not in receipt
    assert event_id
    assert repository.events(tenant.tenant_id)[-1].action == "verification.reported"
    assert decoded.accepted
    assert decoded.recipient == "northline api"
    assert decoded.project == "remote release"


def test_guided_saurus_local_registry_backend_persists_desktop_workflow(tmp_path) -> None:
    """Use the desktop's local SQLite registry connection across restarts."""

    source_path = tmp_path / "source.wav"
    database_path = tmp_path / "desktop-registry.sqlite"
    write_pcm16_wav(source_path, music_like_sample(30))
    output_wav, registry_json = default_output_paths(source_path)
    config = LocalRegistryConfig(database_path)
    backend = local_registry_backend(config)

    encoded = encode_file(
        source_path,
        output_wav,
        registry_json,
        RegistryFields("local registry release", "alpha recipient", "registry-backed desktop"),
        backend=backend,
    )
    restarted_backend = local_registry_backend(config)
    decoded = decode_file(encoded.output_wav, encoded.registry_json, backend=restarted_backend)
    event_id = restarted_backend.report_verification_result(encoded.registry_json, decoded)
    summary = inspect_registry_file(encoded.registry_json, backend=restarted_backend)

    assert database_path.exists()
    assert decoded.accepted
    assert decoded.recipient == "alpha recipient"
    assert event_id
    assert summary.project == "local registry release"
    assert summary.recipient == "alpha recipient"
    assert summary.handle_hex == encoded.handle_hex


def test_guided_saurus_local_registry_health_summarizes_operator_state(tmp_path) -> None:
    """Summarize local registry health without opening the desktop UI."""

    source_path = tmp_path / "source.wav"
    database_path = tmp_path / "desktop-registry.sqlite"
    write_pcm16_wav(source_path, music_like_sample(30))
    output_wav, registry_json = default_output_paths(source_path)
    config = LocalRegistryConfig(database_path)

    missing = local_registry_health(config)
    backend = local_registry_backend(config)
    encode_file(
        source_path,
        output_wav,
        registry_json,
        RegistryFields("health release", "health recipient", ""),
        backend=backend,
    )
    health = local_registry_health(config)

    assert not missing.exists
    assert health.exists
    assert health.tenant_registered
    assert health.schema_version is not None
    assert health.database_bytes > 0
    assert health.song_count == 1
    assert health.active_count == 1
    assert health.export_count >= health.active_count
    assert health.failed_count == health.export_count - health.active_count
    assert health.audit_event_count >= 3


def test_guided_saurus_registry_encode_updates_visible_pending_log(tmp_path) -> None:
    """Mark registry-backed encodes completed or retryable for recovery UI."""

    source_path = tmp_path / "source.wav"
    database_path = tmp_path / "desktop-registry.sqlite"
    write_pcm16_wav(source_path, music_like_sample(30))
    output_wav, registry_json = default_output_paths(source_path)
    backend = local_registry_backend(LocalRegistryConfig(database_path))
    log = PendingEncodeLog(tmp_path / "pending.json")
    fields = RegistryFields("pending release", "pending recipient", "private note excluded")

    encoded = encode_with_pending_log(source_path, output_wav, registry_json, fields, backend, log)
    completed = log.list_records()[0]

    assert encoded.output_wav.exists()
    assert completed.status is PendingEncodeStatus.COMPLETED
    assert log.pending() == ()
    assert pending_summary(log) == "No pending registry-backed encodes need recovery."

    broken_backend = local_registry_backend(LocalRegistryConfig(database_path))
    broken_output = tmp_path / "missing" / "broken.wav"
    broken_receipt = tmp_path / "missing" / "broken.saurus.json"
    with pytest.raises(FileNotFoundError):
        encode_with_pending_log(source_path, broken_output, broken_receipt, fields, broken_backend, log)
    summary = pending_summary(log)

    assert "retryable" in summary
    assert "pending release / pending recipient" in summary
    assert "private note" not in summary


def test_guided_saurus_local_registry_smoke_script(tmp_path) -> None:
    """Exercise the scripted desktop release-check workflow."""

    result = run_local_registry_smoke(tmp_path / "smoke")

    assert result.source_wav.exists()
    assert result.encoded_wav.exists()
    assert result.registry_receipt.exists()
    assert result.registry_database.exists()
    assert result.project == "desktop smoke release"
    assert result.recipient == "alpha smoke recipient"
    assert len(result.handle_hex) == 8


def test_guided_saurus_alpha_contract_smoke_enrolls_device_and_reports_event(tmp_path) -> None:
    """Exercise the pre-AWS alpha credential registry contract."""

    result = run_alpha_contract_smoke(tmp_path / "alpha-smoke")
    receipt_text = result.registry_receipt.read_text(encoding="utf-8")
    scan = scan_text_artifacts(
        {"receipt": receipt_text, "event": result.verification_event_id},
        {"bearer_token": "Bearer ", "private_note": "token must not appear"},
    )

    assert result.encoded_wav.exists()
    assert result.registry_receipt.exists()
    assert result.project == "alpha contract smoke"
    assert result.recipient == "alpha credential recipient"
    assert result.verification_event_id
    assert scan.passed


def test_guided_saurus_desktop_launch_check_builds_hidden_workspace() -> None:
    """Verify the release launch path without showing the desktop window."""

    result = launch_check()

    assert result.ok
    assert result.title == "Saurus | Audio Workspace"
    assert result.tab_count == 3
    assert result.credential_status == "NO DEVICE"


def test_guided_saurus_desktop_zipapp_package_launches(tmp_path: Path) -> None:
    """Build a lightweight desktop package and run its launch check."""

    result = build_desktop_zipapp(tmp_path / "saurus-desktop.pyz")

    assert result.output_path.exists()
    assert result.size_bytes > 0
    assert result.launch_check_passed
    assert result.release_channel == "alpha"
    assert "saurus_app" in result.package_names


def test_guided_saurus_desktop_blocks_production_package_with_demo_secret(tmp_path: Path) -> None:
    """Prevent production package labels while local-demo watermark secrets remain."""

    with pytest.raises(ValueError, match="KMS-backed watermark grants"):
        build_desktop_zipapp(tmp_path / "saurus-production.pyz", launch_check=False, release_channel="production")


def test_guided_saurus_privacy_scan_finds_forbidden_text() -> None:
    """Detect accidental private snippets in text artifacts."""

    result = scan_text_artifacts(
        {"status": "Device enrolled without displaying a token"},
        {"token": "secret-token", "safe_empty": ""},
    )
    failed = scan_text_artifacts({"receipt": "secret-token"}, {"token": "secret-token"})

    assert result.passed
    assert not failed.passed
    assert failed.findings[0].label == "receipt"
    assert failed.findings[0].forbidden_name == "token"


def test_guided_saurus_remote_backend_uses_enrolled_bearer_credential(tmp_path) -> None:
    """Use an enrolled bearer token instead of development identity headers."""

    source_path = tmp_path / "source.wav"
    write_pcm16_wav(source_path, music_like_sample(30))
    output_wav, registry_json = default_output_paths(source_path)
    repository = InMemoryRegistryRepository()
    service = RegistryService(repository)
    tenant = service.register_tenant("Desktop Tenant", "actor-1", "request-tenant")
    authenticator = HmacBearerAuthenticator(b"desktop-auth-secret")
    token = authenticator.issue_token(
        tenant.tenant_id,
        "device-1",
        ("registry.write", "registry.read", "registry.verify"),
    )
    manager = DesktopCredentialManager(MemoryCredentialStore())
    credential = manager.enroll(DeviceCredential("https://registry.saurus.example", tenant.tenant_id, "device-1", token))
    backend = ApiRegistryBackend(
        RegistryApi(service, repository, authenticator=authenticator),
        credential.tenant_id,
        credential.actor_id,
        registry_url=credential.registry_url,
        authorization_token=credential.bearer_token,
    )

    encoded = encode_file(
        source_path,
        output_wav,
        registry_json,
        RegistryFields("remote release", "bearer recipient", "stored outside receipt"),
        backend=backend,
    )
    decoded = decode_file(encoded.output_wav, encoded.registry_json, backend=backend)
    receipt_text = registry_json.read_text(encoding="utf-8")

    assert decoded.accepted
    assert decoded.recipient == "bearer recipient"
    assert credential.bearer_token not in receipt_text
    assert repository.events(tenant.tenant_id)[-1].actor_id == "device-1"


def test_protected_file_credential_store_keeps_token_out_of_plaintext(tmp_path) -> None:
    """Persist desktop credentials only through an explicit byte protector."""

    store = ProtectedFileCredentialStore(
        tmp_path / "credentials",
        lambda value: b"sealed:" + value[::-1],
        lambda value: value.removeprefix(b"sealed:")[::-1],
    )
    credential = DeviceCredential("https://registry.saurus.example", "tenant-1", "device-1", "secret-token")

    store.save(credential)
    loaded = store.load("https://registry.saurus.example", "tenant-1")
    blob = next((tmp_path / "credentials").glob("*.saurus-credential"))

    assert loaded == credential
    assert b"secret-token" not in blob.read_bytes()
    assert "https://registry.saurus.example" not in blob.read_text(encoding="latin-1")

    store.delete("https://registry.saurus.example", "tenant-1")

    with pytest.raises(ValueError, match="not enrolled"):
        store.load("https://registry.saurus.example", "tenant-1")


def test_default_credential_store_uses_os_protection_when_available() -> None:
    """Prefer the OS-backed credential adapter on supported desktop platforms."""

    _store, info = default_credential_store()

    assert info.os_backed == (os.name == "nt")
    assert info.backend in {"windows-dpapi", "memory-fallback"}


def test_guided_saurus_remote_receipt_contains_only_recovery_routing_fields(tmp_path) -> None:
    """Write a remote receipt with the documented recovery field contract."""

    source_path = tmp_path / "source.wav"
    write_pcm16_wav(source_path, music_like_sample(30))
    output_wav, registry_json = default_output_paths(source_path)
    repository = InMemoryRegistryRepository()
    service = RegistryService(repository)
    tenant = service.register_tenant("Desktop Tenant", "actor-1", "request-tenant")
    backend = ApiRegistryBackend(
        RegistryApi(service, repository),
        tenant.tenant_id,
        "actor-1",
        registry_url="https://registry.saurus.example",
    )

    encode_file(
        source_path,
        output_wav,
        registry_json,
        RegistryFields("remote release", "northline api", "private notes stay server-side"),
        backend=backend,
    )
    receipt = json.loads(registry_json.read_text(encoding="utf-8"))

    assert set(receipt) == {
        "version",
        "backend",
        "created_utc",
        "registry_url",
        "tenant_id",
        "song_id",
        "export_id",
        "record_digest",
        "encoded_wav",
    }
    assert receipt["registry_url"] == "https://registry.saurus.example"
    assert "northline api" not in registry_json.read_text(encoding="utf-8")
    assert "private notes" not in registry_json.read_text(encoding="utf-8")
    assert "block_record" not in receipt


def test_guided_saurus_remote_retry_after_restart_does_not_duplicate_active_export(tmp_path) -> None:
    """Replay the same desktop encode after restart without a second active export."""

    source_path = tmp_path / "source.wav"
    write_pcm16_wav(source_path, music_like_sample(30))
    output_wav, registry_json = default_output_paths(source_path)
    repository = InMemoryRegistryRepository()
    service = RegistryService(repository)
    tenant = service.register_tenant("Desktop Tenant", "actor-1", "request-tenant")
    fields = RegistryFields("remote release", "restart recipient", "same operation")
    first_backend = ApiRegistryBackend(RegistryApi(service, repository), tenant.tenant_id, "actor-1")

    first = encode_file(source_path, output_wav, registry_json, fields, backend=first_backend)
    before_retry = repository.exports_for_song(tenant.tenant_id, str(first_backend.song_id))
    restarted_backend = ApiRegistryBackend(RegistryApi(service, repository), tenant.tenant_id, "actor-1")
    second = encode_file(source_path, output_wav, registry_json, fields, backend=restarted_backend)
    after_retry = repository.exports_for_song(tenant.tenant_id, str(restarted_backend.song_id))
    active_exports = [export for export in after_retry if export.state is ExportState.ACTIVE]

    assert first.handle_hex == second.handle_hex
    assert after_retry == before_retry
    assert len(active_exports) == 1


def test_guided_saurus_remote_retry_after_finalize_response_loss_writes_receipt(tmp_path) -> None:
    """Recover when the server finalized but the desktop lost the response."""

    source_path = tmp_path / "source.wav"
    write_pcm16_wav(source_path, music_like_sample(30))
    output_wav, registry_json = default_output_paths(source_path)
    repository = InMemoryRegistryRepository()
    service = RegistryService(repository)
    tenant = service.register_tenant("Desktop Tenant", "actor-1", "request-tenant")
    fields = RegistryFields("remote release", "dropped response", "retry finalize replay")
    dropping_backend = _DropFinalizeResponseBackend(RegistryApi(service, repository), tenant.tenant_id, "actor-1")

    try:
        encode_file(source_path, output_wav, registry_json, fields, backend=dropping_backend)
    except RuntimeError as error:
        assert "simulated network loss" in str(error)
    else:
        raise AssertionError("network loss simulation did not interrupt encode")
    before_retry = repository.exports_for_song(tenant.tenant_id, str(dropping_backend.song_id))
    restarted_backend = ApiRegistryBackend(RegistryApi(service, repository), tenant.tenant_id, "actor-1")

    recovered = encode_file(source_path, output_wav, registry_json, fields, backend=restarted_backend)
    after_retry = repository.exports_for_song(tenant.tenant_id, str(restarted_backend.song_id))
    active_exports = [export for export in after_retry if export.state is ExportState.ACTIVE]
    receipt = json.loads(registry_json.read_text(encoding="utf-8"))

    assert after_retry == before_retry
    assert len(active_exports) == 1
    assert recovered.handle_hex == active_exports[0].handle.hex().upper()
    assert receipt["export_id"] == active_exports[0].export_id
    assert "block_record" not in receipt


def test_guided_saurus_remote_backend_marks_unusable_reservation_failed(tmp_path) -> None:
    """Close a server reservation when desktop encoding cannot finalize it."""

    source_path = tmp_path / "source.wav"
    audio = music_like_sample(30)
    write_pcm16_wav(source_path, audio)
    repository = InMemoryRegistryRepository()
    service = RegistryService(repository)
    tenant = service.register_tenant("Desktop Tenant", "actor-1", "request-tenant")
    backend = ApiRegistryBackend(RegistryApi(service, repository), tenant.tenant_id, "actor-1")
    fields = RegistryFields("remote release", "northline api", "server issued handle")

    reservation = backend.reserve(source_path, audio, fields, 0)
    backend.fail(reservation, "clean gate failed")
    export = repository.export(tenant.tenant_id, str(reservation.token["export_id"]))

    assert export.state is ExportState.FAILED


def test_guided_saurus_remote_backend_loads_bounded_song_bundle_for_local_decode(tmp_path) -> None:
    """Fetch a known-song bundle and verify a suspicious WAV against its claims locally."""

    source_path = tmp_path / "source.wav"
    write_pcm16_wav(source_path, music_like_sample(30))
    repository = InMemoryRegistryRepository()
    service = RegistryService(repository)
    tenant = service.register_tenant("Desktop Tenant", "actor-1", "request-tenant")
    backend = ApiRegistryBackend(RegistryApi(service, repository), tenant.tenant_id, "actor-1")
    first_wav = tmp_path / "first.wav"
    first_json = tmp_path / "first.saurus.json"
    second_wav = tmp_path / "second.wav"
    second_json = tmp_path / "second.saurus.json"

    first = encode_file(
        source_path,
        first_wav,
        first_json,
        RegistryFields("remote release", "recipient one", ""),
        backend=backend,
    )
    encode_file(
        source_path,
        second_wav,
        second_json,
        RegistryFields("remote release", "recipient two", ""),
        backend=backend,
    )
    claims = backend.load_song_claims(str(backend.song_id), limit=2)
    results = decode_claims(first.output_wav, claims)

    assert len(claims) == 2
    assert [result.handle_hex for result in results if result.accepted] == [first.handle_hex]


def test_guided_saurus_local_fanout_decode_honors_claim_budget(tmp_path) -> None:
    """Limit and measure local known-song verification work."""

    source_path = tmp_path / "source.wav"
    write_pcm16_wav(source_path, music_like_sample(30))
    repository = InMemoryRegistryRepository()
    service = RegistryService(repository)
    tenant = service.register_tenant("Desktop Tenant", "actor-1", "request-tenant")
    backend = ApiRegistryBackend(RegistryApi(service, repository), tenant.tenant_id, "actor-1")
    first_wav = tmp_path / "first.wav"
    first_json = tmp_path / "first.saurus.json"
    second_wav = tmp_path / "second.wav"
    second_json = tmp_path / "second.saurus.json"
    first = encode_file(source_path, first_wav, first_json, RegistryFields("remote release", "recipient one", ""), backend=backend)
    encode_file(source_path, second_wav, second_json, RegistryFields("remote release", "recipient two", ""), backend=backend)

    claims = backend.load_song_claims(str(backend.song_id), limit=2)
    results = decode_claims(first.output_wav, claims, maximum_claims=1)
    measured = decode_claims_measured(
        first.output_wav,
        claims,
        maximum_claims=1,
        warning_threshold_ms=10,
        clock=iter((1.0, 1.02)).__next__,
    )

    assert len(claims) == 2
    assert len(results) == 1
    assert results[0].accepted
    assert results[0].handle_hex == first.handle_hex
    assert measured.checked_claims == 1
    assert measured.elapsed_ms == pytest.approx(20)
    assert measured.exceeded_time_budget
    assert measured.results[0].handle_hex == first.handle_hex
    with pytest.raises(ValueError, match="maximum_claims"):
        decode_claims(first.output_wav, claims, maximum_claims=0)
    with pytest.raises(ValueError, match="warning_threshold_ms"):
        decode_claims_measured(first.output_wav, claims, warning_threshold_ms=-1)


def test_guided_saurus_remote_backend_imports_local_sidecar_as_recovery_receipt(tmp_path) -> None:
    """Migrate a private local sidecar into the registry without changing its handle."""

    source_path = tmp_path / "source.wav"
    audio = music_like_sample(30)
    write_pcm16_wav(source_path, audio)
    local_wav = tmp_path / "local.wav"
    local_json = tmp_path / "local.saurus.json"
    imported_json = tmp_path / "imported.saurus.json"
    local = encode_file(
        source_path,
        local_wav,
        local_json,
        RegistryFields("legacy release", "legacy recipient", "private sidecar"),
    )
    repository = InMemoryRegistryRepository()
    service = RegistryService(repository)
    tenant = service.register_tenant("Desktop Tenant", "actor-1", "request-tenant")
    backend = ApiRegistryBackend(RegistryApi(service, repository), tenant.tenant_id, "actor-1")

    export_id = backend.import_local_sidecar(source_path, local.output_wav, local.registry_json, imported_json, audio)
    receipt = json.loads(imported_json.read_text(encoding="utf-8"))
    export = repository.export(tenant.tenant_id, export_id)
    decoded = decode_file(local.output_wav, imported_json, backend=backend)

    assert export.handle.hex().upper() == local.handle_hex
    assert export.state is ExportState.ACTIVE
    assert "block_record" not in receipt
    assert decoded.accepted
    assert decoded.recipient == "legacy recipient"


def test_guided_saurus_remote_backend_exports_receipt_to_private_local_sidecar(tmp_path) -> None:
    """Write a private local sidecar from a remote receipt for disaster recovery."""

    source_path = tmp_path / "source.wav"
    write_pcm16_wav(source_path, music_like_sample(30))
    repository = InMemoryRegistryRepository()
    service = RegistryService(repository)
    tenant = service.register_tenant("Desktop Tenant", "actor-1", "request-tenant")
    backend = ApiRegistryBackend(RegistryApi(service, repository), tenant.tenant_id, "actor-1")
    remote_wav = tmp_path / "remote.wav"
    remote_json = tmp_path / "remote.saurus.json"
    local_json = tmp_path / "exported-local.saurus.json"
    encoded = encode_file(
        source_path,
        remote_wav,
        remote_json,
        RegistryFields("remote release", "offline recipient", ""),
        backend=backend,
    )

    backend.export_local_sidecar(source_path, remote_json, local_json)
    document = json.loads(local_json.read_text(encoding="utf-8"))
    decoded = decode_file(encoded.output_wav, local_json)

    assert "block_record" in document
    assert decoded.accepted
    assert decoded.recipient == "offline recipient"


def test_guided_saurus_pending_encode_log_surfaces_retryable_work(tmp_path) -> None:
    """Persist desktop encode state that recovery UI can safely display."""

    source_path = tmp_path / "source.wav"
    write_pcm16_wav(source_path, music_like_sample(30))
    output_wav, registry_json = default_output_paths(source_path)
    fields = RegistryFields("remote release", "pending recipient", "kept server-side")
    log = PendingEncodeLog(tmp_path / "pending-encodes.json")
    initial = pending_record_for_encode(
        "tenant-1",
        source_path,
        output_wav,
        registry_json,
        fields,
        datetime(2026, 10, 12, tzinfo=timezone.utc),
    )

    log.upsert(initial)
    reloaded = PendingEncodeLog(tmp_path / "pending-encodes.json")
    retryable = reloaded.mark(
        initial.operation_id,
        PendingEncodeStatus.RETRYABLE,
        "Network dropped after registry reservation.",
        datetime(2026, 10, 12, 0, 1, tzinfo=timezone.utc),
    )
    completed = reloaded.mark(
        initial.operation_id,
        PendingEncodeStatus.COMPLETED,
        "Recovery receipt written.",
        datetime(2026, 10, 12, 0, 2, tzinfo=timezone.utc),
    )
    document = json.loads((tmp_path / "pending-encodes.json").read_text(encoding="utf-8"))

    assert retryable.operation_id == initial.operation_id
    assert PendingEncodeLog(tmp_path / "pending-encodes.json").pending() == ()
    assert completed.status is PendingEncodeStatus.COMPLETED
    assert document["records"][0]["recipient"] == "pending recipient"
    assert "kept server-side" not in json.dumps(document)
