"""Build digest-only tenant export manifests.

Tenant export procedures need an inventory that support and customers can
review without copying private retained attribution payloads into a broad
document. This module creates a manifest for an explicitly authorized list of
songs: tenant identity, song IDs, export states, handle digests, retained-record
digests, and audit event count.

It is not a deletion engine, a full legal export, or a replacement for managed
backup restore. Production export procedures still need owner approval,
retention policy, secure delivery, and region-specific review.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib

from .domain import ExportState
from .repository import RegistryRepository


@dataclass(frozen=True, slots=True)
class TenantExportExport:
    """Describe one export in a tenant manifest without private payload bytes."""

    export_id: str
    song_id: str
    state: ExportState
    handle_digest: str
    record_digest: str | None


@dataclass(frozen=True, slots=True)
class TenantExportManifest:
    """Summarize one tenant-scoped registry inventory."""

    tenant_id: str
    generated_utc: datetime
    song_ids: tuple[str, ...]
    exports: tuple[TenantExportExport, ...]
    event_count: int


def build_tenant_export_manifest(
    repository: RegistryRepository,
    tenant_id: str,
    song_ids: tuple[str, ...],
    generated_utc: datetime,
) -> TenantExportManifest:
    """Return a digest-only manifest for an authorized tenant song list."""

    _require_text(tenant_id, "tenant_id")
    _require_aware(generated_utc, "generated_utc")
    if repository.tenant(tenant_id) is None:
        raise ValueError("tenant_id is not registered")
    if not song_ids:
        raise ValueError("song_ids must not be empty")
    exports: list[TenantExportExport] = []
    for song_id in song_ids:
        _require_text(song_id, "song_id")
        if repository.song(tenant_id, song_id) is None:
            raise ValueError("song_id is not registered for tenant")
        for export in repository.exports_for_song(tenant_id, song_id):
            record = repository.attribution_record(tenant_id, export.export_id)
            exports.append(
                TenantExportExport(
                    export.export_id,
                    export.song_id,
                    export.state,
                    hashlib.sha256(export.handle).hexdigest(),
                    record.payload_digest if record is not None else None,
                )
            )
    return TenantExportManifest(
        tenant_id,
        generated_utc,
        tuple(song_ids),
        tuple(sorted(exports, key=lambda item: (item.song_id, item.export_id))),
        len(repository.events(tenant_id)),
    )


def _require_text(value: str, name: str) -> None:
    """Require a non-empty text value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _require_aware(value: datetime, name: str) -> None:
    """Require a timezone-aware timestamp."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
