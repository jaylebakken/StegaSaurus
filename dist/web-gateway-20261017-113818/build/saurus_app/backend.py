"""Define desktop registry backends below the guided encode/decode workflow.

The desktop audio path needs a tiny seam between local waveform encoding and
registry storage. Backends reserve the four-byte handle, finalize the retained
record or receipt after clean self-verification, and reload a selected claim for
decode mode. The default backend preserves the original private JSON sidecar.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Protocol

from saurus_registry.serialization import block_record_from_document, block_record_to_document
from stegosaurus.audio.attribution import BlockAttributionRecord
from stegosaurus.audio.pilot import PcmAudio


REGISTRY_VERSION = 1


@dataclass(frozen=True, slots=True)
class RegistryFields:
    """Represent the human registry context appended during encoding."""

    project: str
    recipient: str
    notes: str


@dataclass(frozen=True, slots=True)
class RegistryReservation:
    """Carry one backend-issued audio handle and opaque finalize token."""

    handle: bytes
    token: dict[str, object]


@dataclass(frozen=True, slots=True)
class RegistryClaim:
    """Carry the retained record and display context for one decode claim."""

    fields: RegistryFields
    record: BlockAttributionRecord


class RegistryBackend(Protocol):
    """Reserve handles, finalize retained records, and load selected claims."""

    def begin_encode(
        self,
        source_wav: Path,
        output_wav: Path,
        registry_json: Path,
        fields: RegistryFields,
    ) -> None:
        """Prepare backend-scoped retry identity before reservation."""

    def reserve(
        self,
        source_wav: Path,
        source_audio: PcmAudio,
        fields: RegistryFields,
        attempt: int,
    ) -> RegistryReservation:
        """Return one handle that the local encoder must embed."""

    def finalize(
        self,
        source_wav: Path,
        output_wav: Path,
        registry_json: Path,
        fields: RegistryFields,
        record: BlockAttributionRecord,
        reservation: RegistryReservation,
    ) -> None:
        """Persist the retained record or recovery receipt after clean verification."""

    def fail(self, reservation: RegistryReservation, reason: str) -> None:
        """Mark a reserved handle unusable before finalization."""

    def load_claim(self, registry_json: Path) -> RegistryClaim:
        """Load one user-selected retained verification claim."""


class LocalSidecarRegistryBackend:
    """Keep the original private JSON sidecar behavior behind a backend seam."""

    def begin_encode(
        self,
        source_wav: Path,
        output_wav: Path,
        registry_json: Path,
        fields: RegistryFields,
    ) -> None:
        """Ignore retry identity because local sidecars have no remote mutations."""

    def reserve(
        self,
        source_wav: Path,
        source_audio: PcmAudio,
        fields: RegistryFields,
        attempt: int,
    ) -> RegistryReservation:
        """Derive the local prototype handle used by the existing workflow."""

        return RegistryReservation(_issue_handle(fields, source_wav, attempt), {})

    def finalize(
        self,
        source_wav: Path,
        output_wav: Path,
        registry_json: Path,
        fields: RegistryFields,
        record: BlockAttributionRecord,
        reservation: RegistryReservation,
    ) -> None:
        """Write the private local sidecar including the retained block record."""

        document = _registry_document(source_wav, output_wav, fields, record)
        registry_json.write_text(json.dumps(document, indent=2), encoding="utf-8")

    def fail(self, reservation: RegistryReservation, reason: str) -> None:
        """Ignore failed local reservations because no durable registry exists yet."""

    def load_claim(self, registry_json: Path) -> RegistryClaim:
        """Restore one retained local sidecar claim."""

        document = json.loads(registry_json.read_text(encoding="utf-8"))
        if document.get("version") != REGISTRY_VERSION:
            raise ValueError("registry JSON version is not supported")
        registry = document["registry"]
        fields = RegistryFields(str(registry["project"]), str(registry["recipient"]), str(registry.get("notes", "")))
        return RegistryClaim(fields, block_record_from_document(document["block_record"]))


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
        "block_record": block_record_to_document(record),
    }


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
