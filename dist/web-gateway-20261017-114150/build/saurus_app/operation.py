"""Name desktop encode operations for registry retry safety.

The remote registry uses idempotency keys to replay completed mutations after a
desktop crash or network drop. The desktop therefore needs a stable operation
name before it creates the song, reserves a handle, or finalizes the retained
record. This module derives that name from the user-selected files and visible
registry fields; it does not contain secrets or private attribution records.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from .backend import RegistryFields


def desktop_operation_id(
    tenant_id: str,
    source_wav: Path,
    output_wav: Path,
    registry_json: Path,
    fields: RegistryFields,
) -> str:
    """Return a stable operation identifier for one desktop encode attempt."""

    source_digest = hashlib.sha256(source_wav.read_bytes()).hexdigest()
    material = "\n".join(
        (
            tenant_id.strip(),
            str(source_wav.resolve()),
            str(output_wav.resolve()),
            str(registry_json.resolve()),
            source_digest,
            fields.project.strip(),
            fields.recipient.strip(),
            fields.notes.strip(),
        )
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()[:24]
