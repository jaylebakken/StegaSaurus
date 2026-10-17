"""Orchestrate the concise Saurus registry state machine.

Application methods are process maps over a tenant-scoped repository: register
source identity, reserve a random four-byte handle, finalize after local clean
verification, and preserve failed or revoked history without processing PCM.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import replace
from datetime import datetime, timezone
import hashlib
import json
import secrets
from uuid import uuid4

from .domain import ExportRecord, ExportState, RegistryEvent, SongRecord, StoredAttributionRecord, TenantRecord
from .repository import HandleConflictError, RegistryRepository
from .serialization import RECORD_SCHEMA_VERSION, deserialize_block_record, digest_payload


MAXIMUM_HANDLE_ATTEMPTS = 128


class RegistryService:
    """Apply tenant, state-transition, record-integrity, and audit policy."""

    def __init__(
        self,
        repository: RegistryRepository,
        *,
        clock: Callable[[], datetime] | None = None,
        identifier_factory: Callable[[], str] | None = None,
        handle_factory: Callable[[], bytes] | None = None,
    ) -> None:
        """Initialize orchestration with explicit deterministic seams for tests."""
        self._repository = repository
        self._clock = clock or (lambda: datetime.now(timezone.utc))
        self._identifier_factory = identifier_factory or (lambda: str(uuid4()))
        self._handle_factory = handle_factory or (lambda: secrets.token_bytes(4))

    def register_tenant(self, name: str, actor_id: str, request_id: str) -> TenantRecord:
        """Create one tenant boundary and record its system event."""
        now = self._now()
        tenant = TenantRecord(self._identifier_factory(), name.strip(), now)
        self._repository.add_tenant(tenant)
        self._audit(tenant.tenant_id, actor_id, "tenant.registered", tenant.tenant_id, request_id, {"name": tenant.name})
        return tenant

    def register_song(
        self,
        tenant_id: str,
        title: str,
        source_digest: str,
        sample_rate: int,
        sample_count: int,
        fingerprint_version: str,
        actor_id: str,
        request_id: str,
    ) -> SongRecord:
        """Register one source identity and deterministic audio geometry."""
        self._require_tenant(tenant_id)
        song = SongRecord(
            self._identifier_factory(),
            tenant_id,
            title.strip(),
            source_digest.strip(),
            sample_rate,
            sample_count,
            fingerprint_version.strip(),
            self._now(),
        )
        self._repository.add_song(song)
        self._audit(tenant_id, actor_id, "song.registered", song.song_id, request_id, {"source_digest": source_digest})
        return song

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
        """Reserve a tenant-unique random handle for one recipient export."""
        if self._repository.song(tenant_id, song_id) is None:
            raise ValueError("song_id is not registered for tenant")
        if parent_export_id is not None:
            parent = self._require_export(tenant_id, parent_export_id)
            if parent.song_id != song_id:
                raise ValueError("parent export must belong to the same song")
            if parent.state is not ExportState.ACTIVE:
                raise ValueError("parent export must be active")
        now = self._now()
        for handle in self._handle_candidates(requested_handle):
            if not isinstance(handle, bytes) or len(handle) != 4:
                raise ValueError("registry handles must contain exactly four bytes")
            export = ExportRecord(
                self._identifier_factory(),
                tenant_id,
                song_id,
                handle,
                recipient_label.strip(),
                parent_export_id,
                ExportState.RESERVED,
                now,
                now,
            )
            try:
                self._repository.reserve_export(export)
            except HandleConflictError:
                if requested_handle is not None:
                    raise
                self._audit(tenant_id, actor_id, "export.handle_collision", song_id, request_id, {"handle": handle.hex()})
                continue
            self._audit(tenant_id, actor_id, "export.reserved", export.export_id, request_id, {"handle": handle.hex()})
            return export
        raise RuntimeError("could not reserve a unique tenant handle")

    def finalize_export(
        self,
        tenant_id: str,
        export_id: str,
        payload: bytes,
        actor_id: str,
        request_id: str,
    ) -> ExportRecord:
        """Store a canonical private record and activate its reserved export."""
        export = self._require_export(tenant_id, export_id)
        if export.state is not ExportState.RESERVED:
            raise ValueError("only a reserved export can be finalized")
        audio_record = deserialize_block_record(payload)
        if audio_record.handle != export.handle:
            raise ValueError("attribution record handle does not match reserved export")
        now = self._now()
        record = StoredAttributionRecord(export_id, RECORD_SCHEMA_VERSION, payload, digest_payload(payload), now)
        active = replace(export, state=ExportState.ACTIVE, updated_utc=now)
        self._repository.finalize_export(tenant_id, active, record)
        self._audit(tenant_id, actor_id, "export.finalized", export_id, request_id, {"record_digest": record.payload_digest})
        return active

    def fail_export(
        self,
        tenant_id: str,
        export_id: str,
        reason: str,
        actor_id: str,
        request_id: str,
    ) -> ExportRecord:
        """Close an unusable reservation while retaining its audit history."""
        export = self._require_export(tenant_id, export_id)
        if export.state is not ExportState.RESERVED:
            raise ValueError("only a reserved export can fail")
        failed = replace(export, state=ExportState.FAILED, updated_utc=self._now())
        self._repository.update_export(failed)
        self._audit(tenant_id, actor_id, "export.failed", export_id, request_id, {"reason": reason.strip()})
        return failed

    def revoke_export(self, tenant_id: str, export_id: str, actor_id: str, request_id: str) -> ExportRecord:
        """Revoke an active export without deleting its record or history."""
        export = self._require_export(tenant_id, export_id)
        if export.state is not ExportState.ACTIVE:
            raise ValueError("only an active export can be revoked")
        revoked = replace(export, state=ExportState.REVOKED, updated_utc=self._now())
        self._repository.update_export(revoked)
        self._audit(tenant_id, actor_id, "export.revoked", export_id, request_id, {})
        return revoked

    def resolve_export(self, tenant_id: str, export_id: str) -> ExportRecord:
        """Resolve one exact tenant-owned export or reject cross-tenant access."""
        return self._require_export(tenant_id, export_id)

    def verification_record(self, tenant_id: str, export_id: str) -> StoredAttributionRecord:
        """Return a retained record only for active or historically revoked exports."""
        export = self._require_export(tenant_id, export_id)
        if export.state not in {ExportState.ACTIVE, ExportState.REVOKED}:
            raise ValueError("export does not have an available verification record")
        record = self._repository.attribution_record(tenant_id, export_id)
        if record is None:
            raise RuntimeError("active export is missing its attribution record")
        return record

    def lineage(self, tenant_id: str, export_id: str) -> tuple[ExportRecord, ...]:
        """Return registry ancestry from root to selected export with cycle defense."""
        lineage = []
        seen: set[str] = set()
        current = self._require_export(tenant_id, export_id)
        song_id = current.song_id
        while True:
            if current.export_id in seen:
                raise RuntimeError("registry lineage contains a cycle")
            if current.song_id != song_id:
                raise RuntimeError("registry lineage crosses songs")
            seen.add(current.export_id)
            lineage.append(current)
            if current.parent_export_id is None:
                return tuple(reversed(lineage))
            current = self._require_export(tenant_id, current.parent_export_id)

    def _require_tenant(self, tenant_id: str) -> TenantRecord:
        """Resolve one tenant or reject an unknown identity."""
        tenant = self._repository.tenant(tenant_id)
        if tenant is None:
            raise ValueError("tenant_id is not registered")
        return tenant

    def _require_export(self, tenant_id: str, export_id: str) -> ExportRecord:
        """Resolve one tenant-owned export without cross-tenant fallback."""
        export = self._repository.export(tenant_id, export_id)
        if export is None:
            raise ValueError("export_id is not registered for tenant")
        return export

    def _now(self) -> datetime:
        """Return a timezone-aware application timestamp."""
        now = self._clock()
        if now.tzinfo is None or now.utcoffset() is None:
            raise ValueError("clock must return a timezone-aware datetime")
        return now

    def _handle_candidates(self, requested_handle: bytes | None):
        """Yield either one requested handle or random issuance attempts."""
        if requested_handle is not None:
            yield requested_handle
            return
        for _ in range(MAXIMUM_HANDLE_ATTEMPTS):
            yield self._handle_factory()

    def _audit(
        self,
        tenant_id: str,
        actor_id: str,
        action: str,
        object_id: str,
        request_id: str,
        detail: dict[str, str],
    ) -> None:
        """Append a digest-only event without copying sensitive labels into audit."""
        canonical = json.dumps(detail, sort_keys=True, separators=(",", ":")).encode("utf-8")
        event = RegistryEvent(self._identifier_factory(), tenant_id, actor_id, action, object_id, request_id, self._now(), hashlib.sha256(canonical).hexdigest())
        self._repository.append_event(event)
