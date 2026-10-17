"""Connect registry-backed desktop encodes to visible recovery state.

Remote or local-registry encodes can fail between reservation, local audio
writing, finalization, and receipt creation. This helper keeps the UI-facing
pending log in sync around that workflow. It records paths, project/recipient
labels, operation IDs, status, and reasons only; it does not store retained
records, carrier maps, bearer tokens, notes, or watermark keys.
"""

from __future__ import annotations

from pathlib import Path

from .backend import RegistryFields
from .pending import PendingEncodeLog, PendingEncodeStatus, pending_record_for_encode
from .registry import EncodeResult, encode_file
from .remote_registry import ApiRegistryBackend

__all__ = ["default_pending_log_path", "encode_with_pending_log", "pending_summary"]


def default_pending_log_path() -> Path:
    """Return the desktop alpha pending-encode log path."""

    return Path.home() / ".saurus" / "pending-encodes.json"


def encode_with_pending_log(
    source_wav: Path,
    output_wav: Path,
    registry_json: Path,
    fields: RegistryFields,
    backend: ApiRegistryBackend | None,
    pending_log: PendingEncodeLog,
) -> EncodeResult:
    """Encode once while recording registry-backed recovery state."""

    if backend is None:
        return encode_file(source_wav, output_wav, registry_json, fields)
    record = pending_record_for_encode(backend.tenant_id, source_wav, output_wav, registry_json, fields)
    pending_log.upsert(record)
    try:
        result = encode_file(source_wav, output_wav, registry_json, fields, backend=backend)
    except Exception as error:
        pending_log.mark(record.operation_id, PendingEncodeStatus.RETRYABLE, f"Encode interrupted: {error}")
        raise
    pending_log.mark(record.operation_id, PendingEncodeStatus.COMPLETED, "Recovery receipt written.")
    return result


def pending_summary(pending_log: PendingEncodeLog) -> str:
    """Return concise user-facing text for pending registry work."""

    records = pending_log.pending()
    if not records:
        return "No pending registry-backed encodes need recovery."
    lines = ["Pending registry-backed encodes:"]
    for record in records:
        lines.append(
            f"{record.status.value}: {record.project} / {record.recipient} "
            f"-> {record.output_wav.name}; {record.reason}"
        )
    return "\n".join(lines)
