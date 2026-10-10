"""Provide a local authenticated registry for opaque v1 attribution handles.

The registry intentionally stays small and in-memory so the audio prototype can
exercise issuance, collision handling, and authenticated provenance without
pretending to be durable infrastructure. A deployment must replace this store
with persistent access-controlled storage and retain each ``AttributionRecord``
beside the issued handle.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import secrets

from .models import AttributionRecord


@dataclass(frozen=True, slots=True)
class RegistryEntry:
    """Bind one opaque handle to local provenance bytes and an authentication tag."""

    handle: bytes
    provenance: bytes
    authentication_tag: bytes


class InMemoryAttributionRegistry:
    """Issue collision-checked four-byte handles and authenticate retained local provenance."""

    def __init__(self, registry_secret: bytes) -> None:
        """Initialize an empty registry from explicit bytes-like authentication material."""

        if not isinstance(registry_secret, (bytes, bytearray, memoryview)):
            raise TypeError("registry_secret must be bytes-like")
        self._secret = bytes(registry_secret)
        if not self._secret:
            raise ValueError("registry_secret must not be empty")
        self._entries: dict[bytes, RegistryEntry] = {}
        self._records: dict[bytes, AttributionRecord] = {}

    def issue(self, provenance: bytes) -> RegistryEntry:
        """Issue a unique four-byte handle and retain authenticated provenance in this local registry."""

        if not isinstance(provenance, (bytes, bytearray, memoryview)):
            raise TypeError("provenance must be bytes-like")
        normalized_provenance = bytes(provenance)
        if not normalized_provenance:
            raise ValueError("provenance must not be empty")
        for _ in range(128):
            handle = secrets.token_bytes(4)
            if handle in self._entries:
                continue
            return self.register(handle, normalized_provenance)
        raise RuntimeError("could not issue a unique four-byte registry handle")

    def register(self, handle: bytes, provenance: bytes) -> RegistryEntry:
        """Register one caller-supplied four-byte handle for an exploratory local attribution claim."""

        if not isinstance(handle, (bytes, bytearray, memoryview)):
            raise TypeError("handle must be bytes-like")
        if not isinstance(provenance, (bytes, bytearray, memoryview)):
            raise TypeError("provenance must be bytes-like")
        normalized_handle = bytes(handle)
        normalized_provenance = bytes(provenance)
        if len(normalized_handle) != 4:
            raise ValueError("registry handles must contain exactly four bytes")
        if not normalized_provenance:
            raise ValueError("provenance must not be empty")
        existing = self._entries.get(normalized_handle)
        if existing is not None:
            if existing.provenance != normalized_provenance:
                raise ValueError("registry handle is already bound to different provenance")
            return existing
        entry = RegistryEntry(
            normalized_handle,
            normalized_provenance,
            self._tag(normalized_handle, normalized_provenance),
        )
        self._entries[normalized_handle] = entry
        return entry

    def resolve(self, handle: bytes) -> RegistryEntry | None:
        """Return an authenticated entry for one claimed handle or ``None`` when it is unknown or invalid."""

        if not isinstance(handle, (bytes, bytearray, memoryview)):
            raise TypeError("handle must be bytes-like")
        normalized_handle = bytes(handle)
        entry = self._entries.get(normalized_handle)
        if entry is None or not hmac.compare_digest(entry.authentication_tag, self._tag(entry.handle, entry.provenance)):
            return None
        return entry

    def retain_record(self, record: AttributionRecord) -> None:
        """Retain the private carrier-frame map for an already issued local registry handle."""

        if not isinstance(record, AttributionRecord):
            raise TypeError("record must be an AttributionRecord")
        if self.resolve(record.handle) is None:
            raise ValueError("cannot retain an attribution record for an unknown or invalid handle")
        self._records[record.handle] = record

    def discard(self, handle: bytes) -> None:
        """Remove an uncommitted issued handle and any retained record after a failed calibration attempt."""

        if not isinstance(handle, (bytes, bytearray, memoryview)):
            raise TypeError("handle must be bytes-like")
        normalized_handle = bytes(handle)
        self._entries.pop(normalized_handle, None)
        self._records.pop(normalized_handle, None)

    def record_for(self, handle: bytes) -> AttributionRecord | None:
        """Return the retained private verification record for one authenticated claimed handle."""

        entry = self.resolve(handle)
        return None if entry is None else self._records.get(entry.handle)

    def _tag(self, handle: bytes, provenance: bytes) -> bytes:
        """Create the domain-separated local authentication tag for one retained entry."""

        return hmac.new(self._secret, b"stegosaurus-registry-v1|" + handle + provenance, hashlib.sha256).digest()
