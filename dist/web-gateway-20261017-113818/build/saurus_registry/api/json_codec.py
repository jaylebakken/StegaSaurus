"""Serialize registry domain records for the versioned JSON API.

The API returns registry facts such as IDs, states, handles, and timestamps. It
does not reinterpret recipient labels as proof, and retained private records
travel only as explicit base64 payloads for authorized verification workflows.
"""

from __future__ import annotations

from base64 import b64encode
from datetime import datetime
from typing import Any

from ..domain import ExportRecord, SongRecord, StoredAttributionRecord


def song_document(song: SongRecord) -> dict[str, Any]:
    """Return a stable JSON document for one song."""

    return {
        "song_id": song.song_id,
        "tenant_id": song.tenant_id,
        "title": song.title,
        "source_digest": song.source_digest,
        "sample_rate": song.sample_rate,
        "sample_count": song.sample_count,
        "fingerprint_version": song.fingerprint_version,
        "created_utc": time_text(song.created_utc),
    }


def export_document(export: ExportRecord) -> dict[str, Any]:
    """Return a stable JSON document for one export."""

    return {
        "export_id": export.export_id,
        "tenant_id": export.tenant_id,
        "song_id": export.song_id,
        "handle_hex": export.handle.hex(),
        "recipient_label": export.recipient_label,
        "parent_export_id": export.parent_export_id,
        "state": export.state.value,
        "created_utc": time_text(export.created_utc),
        "updated_utc": time_text(export.updated_utc),
    }


def record_document(record: StoredAttributionRecord) -> dict[str, Any]:
    """Return a stable JSON document for one retained private record."""

    return {
        "export_id": record.export_id,
        "schema_version": record.schema_version,
        "payload_b64": b64encode(record.payload).decode("ascii"),
        "payload_digest": record.payload_digest,
        "key_id": record.key_id,
        "encryption_algorithm": record.encryption_algorithm,
        "created_utc": time_text(record.created_utc),
    }


def time_text(value: datetime) -> str:
    """Serialize an aware timestamp for API responses."""

    return value.isoformat()
