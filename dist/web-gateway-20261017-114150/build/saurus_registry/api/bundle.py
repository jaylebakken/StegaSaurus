"""Build bounded verification bundles for known-song desktop checks.

This helper is intentionally narrow: an authorized verifier asks for one known
song, receives only active or revoked export records, and the result is capped
by an explicit limit. It is not blind handle discovery, public lookup, or a
general registry dump.
"""

from __future__ import annotations

from typing import Any

from ..application import RegistryService
from ..domain import ExportState
from ..repository import RegistryRepository
from .auth import RequestContext
from .json_codec import export_document, record_document, song_document


MAXIMUM_BUNDLE_LIMIT = 50


def song_verification_bundle(
    service: RegistryService,
    repository: RegistryRepository,
    context: RequestContext,
    song_id: str,
    limit: int,
) -> dict[str, Any]:
    """Return a bounded authorized bundle of retained records for one song."""

    if limit < 1 or limit > MAXIMUM_BUNDLE_LIMIT:
        raise ValueError(f"limit must be between 1 and {MAXIMUM_BUNDLE_LIMIT}")
    song = repository.song(context.tenant_id, song_id)
    if song is None:
        raise ValueError("song_id is not registered for tenant")
    eligible = tuple(
        export
        for export in repository.exports_for_song(context.tenant_id, song_id)
        if export.state in {ExportState.ACTIVE, ExportState.REVOKED}
    )
    selected = eligible[:limit]
    return {
        "song": song_document(song),
        "limit": limit,
        "returned_count": len(selected),
        "truncated": len(eligible) > limit,
        "exports": [export_document(export) for export in selected],
        "records": [record_document(service.verification_record(context.tenant_id, export.export_id)) for export in selected],
    }
