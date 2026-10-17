"""Persist desktop encode work that may need recovery.

Remote registry encodes have two durable systems involved: the desktop writes
audio and a small receipt, while the registry reserves and finalizes server
state. A user should never have to guess whether a network drop left work to
retry. This module stores a small local operation log that contains only file
paths, operation IDs, status, and user-visible recovery reasons.

The log is not the source of registry truth and it does not store retained
attribution records, bearer tokens, recipient notes beyond the visible project
and recipient labels, watermark secrets, or private carrier details.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from enum import Enum
import json
from pathlib import Path

from .backend import RegistryFields
from .operation import desktop_operation_id


PENDING_LOG_VERSION = 1


class PendingEncodeStatus(str, Enum):
    """Name the desktop-visible lifecycle for interrupted encode work."""

    PENDING = "pending"
    RETRYABLE = "retryable"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class PendingEncodeRecord:
    """Describe one desktop encode operation without private registry records."""

    operation_id: str
    tenant_id: str
    source_wav: Path
    output_wav: Path
    registry_json: Path
    project: str
    recipient: str
    status: PendingEncodeStatus
    reason: str
    updated_utc: datetime


class PendingEncodeLog:
    """Read and write a local JSON pending-encode operation log."""

    def __init__(self, path: Path) -> None:
        """Create a log bound to one local JSON document path."""

        self.path = path

    def list_records(self) -> tuple[PendingEncodeRecord, ...]:
        """Return every known pending-log record in stable operation order."""

        return tuple(sorted(self._read_records(), key=lambda record: record.operation_id))

    def load(self, operation_id: str) -> PendingEncodeRecord:
        """Return one operation record or raise ``KeyError`` when absent."""

        for record in self._read_records():
            if record.operation_id == operation_id:
                return record
        raise KeyError(operation_id)

    def pending(self) -> tuple[PendingEncodeRecord, ...]:
        """Return records that should still be visible in recovery UI."""

        visible = {PendingEncodeStatus.PENDING, PendingEncodeStatus.RETRYABLE}
        return tuple(record for record in self.list_records() if record.status in visible)

    def upsert(self, record: PendingEncodeRecord) -> PendingEncodeRecord:
        """Insert or replace one operation record and return the stored value."""

        _validate_record(record)
        records = {existing.operation_id: existing for existing in self._read_records()}
        records[record.operation_id] = record
        self._write_records(tuple(records.values()))
        return record

    def mark(
        self,
        operation_id: str,
        status: PendingEncodeStatus,
        reason: str,
        updated_utc: datetime | None = None,
    ) -> PendingEncodeRecord:
        """Update status and reason for one existing operation record."""

        current = self.load(operation_id)
        updated = replace(
            current,
            status=_coerce_status(status),
            reason=reason.strip(),
            updated_utc=updated_utc or datetime.now(timezone.utc),
        )
        return self.upsert(updated)

    def _read_records(self) -> tuple[PendingEncodeRecord, ...]:
        """Load all records from disk, treating a missing log as empty."""

        if not self.path.exists():
            return ()
        document = json.loads(self.path.read_text(encoding="utf-8"))
        if document.get("version") != PENDING_LOG_VERSION:
            raise ValueError("pending encode log version is not supported")
        records = document.get("records")
        if not isinstance(records, list):
            raise ValueError("pending encode log records must be a list")
        return tuple(_record_from_json(record) for record in records)

    def _write_records(self, records: tuple[PendingEncodeRecord, ...]) -> None:
        """Write all records to disk as a deterministic JSON document."""

        self.path.parent.mkdir(parents=True, exist_ok=True)
        document = {
            "version": PENDING_LOG_VERSION,
            "records": [_record_to_json(record) for record in sorted(records, key=lambda item: item.operation_id)],
        }
        self.path.write_text(json.dumps(document, indent=2), encoding="utf-8")


def pending_record_for_encode(
    tenant_id: str,
    source_wav: Path,
    output_wav: Path,
    registry_json: Path,
    fields: RegistryFields,
    updated_utc: datetime | None = None,
) -> PendingEncodeRecord:
    """Create the initial local operation-log record for a remote encode."""

    operation_id = desktop_operation_id(tenant_id, source_wav, output_wav, registry_json, fields)
    return PendingEncodeRecord(
        operation_id=operation_id,
        tenant_id=tenant_id.strip(),
        source_wav=source_wav,
        output_wav=output_wav,
        registry_json=registry_json,
        project=fields.project.strip(),
        recipient=fields.recipient.strip(),
        status=PendingEncodeStatus.PENDING,
        reason="Waiting for registry finalization.",
        updated_utc=updated_utc or datetime.now(timezone.utc),
    )


def _validate_record(record: PendingEncodeRecord) -> None:
    """Validate a record before it is persisted."""

    if not record.operation_id.strip():
        raise ValueError("operation_id must not be empty")
    if not record.tenant_id.strip():
        raise ValueError("tenant_id must not be empty")
    if not record.project.strip():
        raise ValueError("project must not be empty")
    if not record.recipient.strip():
        raise ValueError("recipient must not be empty")
    _coerce_status(record.status)
    if record.updated_utc.tzinfo is None:
        raise ValueError("updated_utc must be timezone-aware")


def _record_to_json(record: PendingEncodeRecord) -> dict[str, str]:
    """Serialize one pending encode record to JSON-safe values."""

    _validate_record(record)
    return {
        "operation_id": record.operation_id,
        "tenant_id": record.tenant_id,
        "source_wav": str(record.source_wav),
        "output_wav": str(record.output_wav),
        "registry_json": str(record.registry_json),
        "project": record.project,
        "recipient": record.recipient,
        "status": _coerce_status(record.status).value,
        "reason": record.reason,
        "updated_utc": record.updated_utc.astimezone(timezone.utc).isoformat(),
    }


def _record_from_json(value: object) -> PendingEncodeRecord:
    """Deserialize and validate one pending encode record."""

    if not isinstance(value, dict):
        raise ValueError("pending encode record must be an object")
    record = PendingEncodeRecord(
        operation_id=_required_text(value, "operation_id"),
        tenant_id=_required_text(value, "tenant_id"),
        source_wav=Path(_required_text(value, "source_wav")),
        output_wav=Path(_required_text(value, "output_wav")),
        registry_json=Path(_required_text(value, "registry_json")),
        project=_required_text(value, "project"),
        recipient=_required_text(value, "recipient"),
        status=_coerce_status(_required_text(value, "status")),
        reason=str(value.get("reason", "")),
        updated_utc=datetime.fromisoformat(_required_text(value, "updated_utc")),
    )
    _validate_record(record)
    return record


def _required_text(value: dict[str, object], key: str) -> str:
    """Read one non-empty text field from a JSON object."""

    field = value.get(key)
    if not isinstance(field, str) or not field.strip():
        raise ValueError(f"{key} must be a non-empty string")
    return field


def _coerce_status(value: PendingEncodeStatus | str) -> PendingEncodeStatus:
    """Return a pending encode status or raise a clear validation error."""

    try:
        return PendingEncodeStatus(value)
    except ValueError as error:
        raise ValueError("pending encode status is not supported") from error
