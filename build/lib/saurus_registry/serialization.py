"""Serialize private repeated-block records into canonical versioned JSON.

Canonical bytes make registry digests stable across desktop, API, database, and
backup boundaries. This schema preserves the current local sidecar's private
block-record fields while adding an explicit record-schema envelope. It does not
contain recipient labels, paths, notes, or source audio.
"""

from __future__ import annotations

import hashlib
import json
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from stegosaurus.audio.attribution import BlockAttributionRecord
    from stegosaurus.audio.attribution_core.models import AttributionRecord


RECORD_SCHEMA_VERSION = 1


def serialize_block_record(record: BlockAttributionRecord) -> bytes:
    """Return deterministic UTF-8 JSON bytes for one private block record."""

    document = {"schema_version": RECORD_SCHEMA_VERSION, "block_record": block_record_to_document(record)}
    return json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=True).encode("utf-8")


def deserialize_block_record(payload: bytes) -> BlockAttributionRecord:
    """Validate and restore one canonical private block record payload."""

    if not isinstance(payload, bytes) or not payload:
        raise ValueError("payload must be nonempty bytes")
    document = json.loads(payload.decode("utf-8"))
    if not isinstance(document, dict) or document.get("schema_version") != RECORD_SCHEMA_VERSION:
        raise ValueError("attribution record schema version is not supported")
    data = document.get("block_record")
    if not isinstance(data, dict):
        raise ValueError("block_record must be an object")
    return block_record_from_document(data)


def digest_payload(payload: bytes) -> str:
    """Return a lowercase SHA-256 digest for canonical payload bytes."""

    if not isinstance(payload, bytes) or not payload:
        raise ValueError("payload must be nonempty bytes")
    return hashlib.sha256(payload).hexdigest()


def block_record_to_document(record: BlockAttributionRecord) -> dict[str, object]:
    """Convert one repeated-block record to JSON-compatible values."""

    return {
        "handle": record.handle.hex(),
        "block_sample_count": record.block_sample_count,
        "sample_rate": record.sample_rate,
        "total_sample_count": record.total_sample_count,
        "block_records": [_attribution_record_to_document(item) for item in record.block_records],
    }


def block_record_from_document(data: dict[str, Any]) -> BlockAttributionRecord:
    """Restore one repeated-block record from validated JSON-compatible values."""

    from stegosaurus.audio.attribution import BlockAttributionRecord

    block_records = _required_list(data, "block_records")
    return BlockAttributionRecord(
        bytes.fromhex(_required_text(data, "handle")),
        _required_int(data, "block_sample_count"),
        _required_int(data, "sample_rate"),
        tuple(_attribution_record_from_document(_required_object(item)) for item in block_records),
        _required_int(data, "total_sample_count"),
    )


def _attribution_record_to_document(record: AttributionRecord) -> dict[str, object]:
    """Convert one private carrier map to JSON-compatible values."""

    return {
        "handle": record.handle.hex(),
        "carrier_plan": {
            "payload_length": record.carrier_plan.payload_length,
            "codeword_length": record.carrier_plan.codeword_length,
            "carrier_bits": list(record.carrier_plan.carrier_bits),
        },
        "replica_frame_indices": [list(replica) for replica in record.replica_frame_indices],
        "sample_rate": record.sample_rate,
    }


def _attribution_record_from_document(data: dict[str, Any]) -> AttributionRecord:
    """Restore one private carrier map from JSON-compatible values."""

    from stegosaurus.audio.attribution_core.models import AttributionRecord
    from stegosaurus.audio.transport import CarrierPlan

    plan_data = _required_object(data.get("carrier_plan"))
    bits = _required_list(plan_data, "carrier_bits")
    replicas = _required_list(data, "replica_frame_indices")
    plan = CarrierPlan(
        _required_int(plan_data, "payload_length"),
        _required_int(plan_data, "codeword_length"),
        tuple(int(bit) for bit in bits),
    )
    return AttributionRecord(
        bytes.fromhex(_required_text(data, "handle")),
        plan,
        tuple(tuple(int(index) for index in _required_list_value(replica)) for replica in replicas),
        _required_int(data, "sample_rate"),
    )


def _required_object(value: object) -> dict[str, Any]:
    """Return a mapping value or reject malformed JSON."""

    if not isinstance(value, dict):
        raise ValueError("expected an object")
    return value


def _required_text(data: dict[str, Any], key: str) -> str:
    """Return one nonempty string field."""

    value = data.get(key)
    if not isinstance(value, str) or not value:
        raise ValueError(f"{key} must be a nonempty string")
    return value


def _required_int(data: dict[str, Any], key: str) -> int:
    """Return one integer field without accepting booleans."""

    value = data.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{key} must be an integer")
    return value


def _required_list(data: dict[str, Any], key: str) -> list[object]:
    """Return one list field."""

    return _required_list_value(data.get(key))


def _required_list_value(value: object) -> list[object]:
    """Return a list value or reject malformed JSON."""

    if not isinstance(value, list):
        raise ValueError("expected a list")
    return value
