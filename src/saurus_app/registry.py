"""Encode and decode Saurus files with a small local registry sidecar.

This module keeps the new desktop app deliberately simple.  It wraps the
existing repeated-block attribution codec and serializes the retained private
record to JSON:

    source.wav + user registry fields
      -> encode handle across complete blocks
      -> write encoded.wav and encoded.saurus.json

    suspicious.wav + encoded.saurus.json
      -> restore retained block records
      -> verify the claimed handle
      -> return accepted / abstained diagnostics

The JSON sidecar is required because the current attribution design verifies a
claimed retained record.  It is not blind handle discovery and it is not a
production registry, key store, or robustness guarantee.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path

from stegosaurus.audio.attribution import BlockAttributionCodec, BlockAttributionRecord, RepeatedBlockWaterfallPolicy
from stegosaurus.audio.attribution_core.models import AttributionRecord
from stegosaurus.audio.pilot import read_pcm16_wav, write_pcm16_wav
from stegosaurus.audio.transport import CarrierPlan


MASTER_SECRET = b"saurus-guided-desktop-app-v1"
REGISTRY_VERSION = 1


@dataclass(frozen=True, slots=True)
class RegistryFields:
    """Represent the human registry context appended during encoding."""

    project: str
    recipient: str
    notes: str


@dataclass(frozen=True, slots=True)
class EncodeResult:
    """Summarize one guided encode job."""

    output_wav: Path
    registry_json: Path
    handle_hex: str
    block_count: int
    minimum_snr_db: float


@dataclass(frozen=True, slots=True)
class DecodeResult:
    """Summarize one guided decode job."""

    accepted: bool
    stage: str
    reason: str
    handle_hex: str
    recipient: str
    project: str
    block_votes: int
    block_count: int
    pooled_rs_cost: int


def encode_file(
    source_wav: Path,
    output_wav: Path,
    registry_json: Path,
    fields: RegistryFields,
    maximum_attempts: int = 32,
) -> EncodeResult:
    """Encode one PCM16 WAV and write its private local registry JSON."""

    _validate_text(fields.project, "project")
    _validate_text(fields.recipient, "recipient")
    if isinstance(maximum_attempts, bool) or maximum_attempts < 1:
        raise ValueError("maximum_attempts must be a positive integer")
    source = read_pcm16_wav(source_wav)
    codec = BlockAttributionCodec(MASTER_SECRET)
    policy = RepeatedBlockWaterfallPolicy()
    for attempt in range(maximum_attempts):
        handle = _issue_handle(fields, source_wav, attempt)
        embedding = codec.embed(source, handle)
        if policy.decide(codec.verify(embedding.audio, embedding.record)).accepted:
            break
    else:
        raise RuntimeError("could not issue a cleanly verifiable registry handle")
    write_pcm16_wav(output_wav, embedding.audio)
    registry_json.write_text(
        json.dumps(_registry_document(source_wav, output_wav, fields, embedding.record), indent=2),
        encoding="utf-8",
    )
    return EncodeResult(
        output_wav,
        registry_json,
        handle.hex().upper(),
        len(embedding.record.block_records),
        min(embedding.block_signal_to_noise_db),
    )


def decode_file(received_wav: Path, registry_json: Path) -> DecodeResult:
    """Verify one received WAV against the retained registry sidecar."""

    document = json.loads(registry_json.read_text(encoding="utf-8"))
    if document.get("version") != REGISTRY_VERSION:
        raise ValueError("registry JSON version is not supported")
    record = _block_record_from_json(document["block_record"])
    audio = read_pcm16_wav(received_wav)
    verification = BlockAttributionCodec(MASTER_SECRET).verify(audio, record)
    decision = RepeatedBlockWaterfallPolicy().decide(verification)
    registry = document["registry"]
    return DecodeResult(
        decision.accepted,
        decision.stage.value,
        decision.reason,
        record.handle.hex().upper(),
        str(registry["recipient"]),
        str(registry["project"]),
        decision.block_votes,
        decision.block_count,
        decision.pooled_rs_cost,
    )


def default_output_paths(source_wav: Path) -> tuple[Path, Path]:
    """Return friendly default output paths beside the selected source WAV."""

    output_wav = source_wav.with_name(f"{source_wav.stem}-saurus.wav")
    return output_wav, output_wav.with_suffix(".saurus.json")


def _registry_document(
    source_wav: Path,
    output_wav: Path,
    fields: RegistryFields,
    record: BlockAttributionRecord,
) -> dict[str, object]:
    """Build the JSON document that travels with the encoded WAV."""

    return {
        "version": REGISTRY_VERSION,
        "created_utc": datetime.now(timezone.utc).isoformat(),
        "source_wav": str(source_wav),
        "encoded_wav": str(output_wav),
        "registry": {
            "project": fields.project.strip(),
            "recipient": fields.recipient.strip(),
            "notes": fields.notes.strip(),
        },
        "block_record": _block_record_to_json(record),
    }


def _block_record_to_json(record: BlockAttributionRecord) -> dict[str, object]:
    """Convert the retained repeated-block record to JSON-compatible values."""

    return {
        "handle": record.handle.hex(),
        "block_sample_count": record.block_sample_count,
        "sample_rate": record.sample_rate,
        "total_sample_count": record.total_sample_count,
        "block_records": [_attribution_record_to_json(item) for item in record.block_records],
    }


def _block_record_from_json(data: dict[str, object]) -> BlockAttributionRecord:
    """Restore a retained repeated-block record from JSON-compatible values."""

    return BlockAttributionRecord(
        bytes.fromhex(str(data["handle"])),
        int(data["block_sample_count"]),
        int(data["sample_rate"]),
        tuple(_attribution_record_from_json(item) for item in data["block_records"]),  # type: ignore[arg-type]
        int(data["total_sample_count"]),
    )


def _attribution_record_to_json(record: AttributionRecord) -> dict[str, object]:
    """Convert one retained block map to JSON-compatible values."""

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


def _attribution_record_from_json(data: dict[str, object]) -> AttributionRecord:
    """Restore one retained block map from JSON-compatible values."""

    plan_data = data["carrier_plan"]  # type: ignore[assignment]
    plan = CarrierPlan(
        int(plan_data["payload_length"]),
        int(plan_data["codeword_length"]),
        tuple(int(bit) for bit in plan_data["carrier_bits"]),
    )
    return AttributionRecord(
        bytes.fromhex(str(data["handle"])),
        plan,
        tuple(tuple(int(index) for index in replica) for replica in data["replica_frame_indices"]),  # type: ignore[arg-type]
        int(data["sample_rate"]),
    )


def _issue_handle(fields: RegistryFields, source_wav: Path, attempt: int) -> bytes:
    """Derive a compact local handle from registry text and the current timestamp."""

    material = "|".join(
        (
            fields.project.strip(),
            fields.recipient.strip(),
            fields.notes.strip(),
            str(source_wav),
            str(attempt),
            datetime.now(timezone.utc).isoformat(),
        )
    )
    return hashlib.sha256(material.encode("utf-8")).digest()[:4]


def _validate_text(value: str, name: str) -> None:
    """Require visible registry text for fields the user must understand."""

    if not value.strip():
        raise ValueError(f"{name} must not be empty")
