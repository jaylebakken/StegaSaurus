"""Persist desktop registry credentials through an OS-backed protector.

The desktop enrollment UI should not leave bearer tokens in project files,
receipts, logs, or plain text on disk. This module keeps that rule narrow and
testable: credentials are serialized as a small JSON document, encrypted by an
explicit byte protector, and stored under an application credential directory.
On Windows the default protector is DPAPI, which binds encryption to the
current user profile. Other platforms fall back to the in-memory store until a
reviewed native keychain adapter is added.
"""

from __future__ import annotations

from collections.abc import Callable
from ctypes import Structure, byref, cast, create_string_buffer, string_at, windll
from ctypes import wintypes
from dataclasses import asdict, dataclass
import hashlib
import json
import os
from pathlib import Path

from .credentials import CredentialStore, DeviceCredential, MemoryCredentialStore

ByteProtector = Callable[[bytes], bytes]


@dataclass(frozen=True, slots=True)
class ProtectedCredentialStoreInfo:
    """Describe the selected desktop credential storage backend."""

    backend: str
    path: Path | None
    os_backed: bool


class ProtectedFileCredentialStore:
    """Store encrypted desktop credentials in one app-owned directory."""

    def __init__(self, directory: Path, protect: ByteProtector, unprotect: ByteProtector) -> None:
        """Initialize the protected file store with explicit byte protectors."""

        self._directory = directory
        self._protect = protect
        self._unprotect = unprotect

    @property
    def directory(self) -> Path:
        """Return the directory that holds encrypted credential blobs."""

        return self._directory

    def save(self, credential: DeviceCredential) -> None:
        """Encrypt and persist one desktop device credential."""

        self._directory.mkdir(parents=True, exist_ok=True)
        payload = json.dumps(asdict(credential), sort_keys=True, separators=(",", ":")).encode("utf-8")
        encrypted = self._protect(payload)
        target = self._path(credential.registry_url, credential.tenant_id)
        temporary = target.with_suffix(".tmp")
        temporary.write_bytes(encrypted)
        temporary.replace(target)

    def load(self, registry_url: str, tenant_id: str) -> DeviceCredential:
        """Load and decrypt one desktop device credential."""

        path = self._path(registry_url, tenant_id)
        if not path.exists():
            raise ValueError("device credential is not enrolled")
        document = json.loads(self._unprotect(path.read_bytes()).decode("utf-8"))
        credential = DeviceCredential(
            str(document["registry_url"]),
            str(document["tenant_id"]),
            str(document["actor_id"]),
            str(document["bearer_token"]),
        )
        if credential.registry_url != registry_url or credential.tenant_id != tenant_id:
            raise ValueError("stored credential identity does not match request")
        return credential

    def delete(self, registry_url: str, tenant_id: str) -> None:
        """Delete one encrypted desktop credential if it exists."""

        self._path(registry_url, tenant_id).unlink(missing_ok=True)

    def _path(self, registry_url: str, tenant_id: str) -> Path:
        """Return the deterministic encrypted blob path for one credential."""

        digest = hashlib.sha256(f"{registry_url}\0{tenant_id}".encode("utf-8")).hexdigest()
        return self._directory / f"{digest}.saurus-credential"


def default_credential_store() -> tuple[CredentialStore, ProtectedCredentialStoreInfo]:
    """Return the best available desktop credential store for this OS."""

    if os.name == "nt":
        directory = default_credential_directory()
        return ProtectedFileCredentialStore(directory, windows_protect, windows_unprotect), ProtectedCredentialStoreInfo("windows-dpapi", directory, True)
    return MemoryCredentialStore(), ProtectedCredentialStoreInfo("memory-fallback", None, False)


def default_credential_directory() -> Path:
    """Return the app-owned directory for encrypted desktop credentials."""

    root = os.environ.get("LOCALAPPDATA")
    if root:
        return Path(root) / "Saurus" / "credentials"
    return Path.home() / ".saurus" / "credentials"


def windows_protect(data: bytes) -> bytes:
    """Protect bytes with the current Windows user profile through DPAPI."""

    return _crypt_protect(data, protect=True)


def windows_unprotect(data: bytes) -> bytes:
    """Unprotect bytes with the current Windows user profile through DPAPI."""

    return _crypt_protect(data, protect=False)


class _DataBlob(Structure):
    """Represent the Windows CRYPTOAPI_BLOB structure."""

    _fields_ = (("cbData", wintypes.DWORD), ("pbData", wintypes.LPVOID))


def _crypt_protect(data: bytes, *, protect: bool) -> bytes:
    """Call the selected DPAPI function and return copied output bytes."""

    if os.name != "nt":
        raise RuntimeError("Windows DPAPI is only available on Windows")
    buffer = create_string_buffer(data)
    input_blob = _DataBlob(len(data), cast(buffer, wintypes.LPVOID))
    output_blob = _DataBlob()
    function = windll.crypt32.CryptProtectData if protect else windll.crypt32.CryptUnprotectData
    ok = function(byref(input_blob), None, None, None, None, 0, byref(output_blob))
    if not ok:
        raise OSError("Windows DPAPI credential protection failed")
    try:
        return string_at(output_blob.pbData, output_blob.cbData)
    finally:
        windll.kernel32.LocalFree(output_blob.pbData)
