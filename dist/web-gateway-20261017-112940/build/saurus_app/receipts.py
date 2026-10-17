"""Read and write remote registry recovery receipts.

Remote receipts are deliberately smaller than local sidecars. They help the
desktop find the server-side song and export after a restart, but they do not
copy recipient notes, private block records, carrier maps, access tokens, or
watermark secrets onto disk.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
from pathlib import Path


REMOTE_RECEIPT_VERSION = 1
REMOTE_RECEIPT_BACKEND = "saurus-registry-api-v1"


def read_remote_receipt(registry_json: Path) -> dict[str, object]:
    """Load and validate one remote registry receipt document."""

    receipt = json.loads(registry_json.read_text(encoding="utf-8"))
    if receipt.get("version") != REMOTE_RECEIPT_VERSION or receipt.get("backend") != REMOTE_RECEIPT_BACKEND:
        raise ValueError("registry API receipt is not supported")
    return receipt


def write_remote_receipt(
    registry_json: Path,
    *,
    registry_url: str,
    tenant_id: str,
    song_id: object,
    export_id: str,
    record_digest: str,
    output_wav: Path,
) -> None:
    """Write the documented private-record-free remote recovery receipt."""

    registry_json.write_text(
        json.dumps(
            {
                "version": REMOTE_RECEIPT_VERSION,
                "backend": REMOTE_RECEIPT_BACKEND,
                "created_utc": datetime.now(timezone.utc).isoformat(),
                "registry_url": registry_url,
                "tenant_id": tenant_id,
                "song_id": song_id,
                "export_id": export_id,
                "record_digest": record_digest,
                "encoded_wav": str(output_wav),
            },
            indent=2,
        ),
        encoding="utf-8",
    )
