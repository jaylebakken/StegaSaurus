"""Model server-owned key custody with local encode grants.

Production Saurus should keep tenant/root watermark material under managed KMS
control while preserving the product promise that source audio stays on the
desktop. This module defines the early registry contract for that shape: a
server-owned keyring issues a short-lived, scope-bound working key grant that a
specific device can unwrap locally. The local implementation uses HMAC and XOR
for deterministic tests only; it is not a production KMS or AEAD substitute.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import hmac
import json
from uuid import uuid4


LOCAL_KMS_WRAP = "local-kms-hmac-wrap-v1"
AWS_KMS_DATA_KEY_GRANT = "aws-kms-data-key-grant-v1"
ENCODE_GRANT_ALGORITHMS = (LOCAL_KMS_WRAP, AWS_KMS_DATA_KEY_GRANT)


@dataclass(frozen=True, slots=True)
class EncodeGrantScope:
    """Bind one working key grant to a single encode operation."""

    tenant_id: str
    song_id: str
    export_id: str
    device_id: str
    actor_id: str
    profile_version: str
    issued_utc: datetime
    expires_utc: datetime
    request_id: str = "local-request-unrecorded"

    def __post_init__(self) -> None:
        """Validate scope identity and bounded lifetime."""

        _require_named_texts(self, ("tenant_id", "song_id", "export_id", "device_id", "actor_id", "profile_version", "request_id"))
        _require_aware(self.issued_utc, "issued_utc")
        _require_aware(self.expires_utc, "expires_utc")
        if self.expires_utc <= self.issued_utc:
            raise ValueError("expires_utc must be after issued_utc")


@dataclass(frozen=True, slots=True)
class EncodeGrant:
    """Carry a wrapped desktop working key and its audited scope."""

    grant_id: str
    root_key_id: str
    algorithm: str
    scope: EncodeGrantScope
    wrapped_working_key: bytes
    wrap_tag: bytes
    context_digest: str

    def __post_init__(self) -> None:
        """Validate grant metadata without exposing plaintext key bytes."""

        _require_text(self.grant_id, "grant_id")
        _require_text(self.root_key_id, "root_key_id")
        _require_text(self.algorithm, "algorithm")
        _require_text(self.context_digest, "context_digest")
        if self.algorithm not in ENCODE_GRANT_ALGORITHMS:
            raise ValueError("encode grant algorithm is not supported")
        if not self.wrapped_working_key or not self.wrap_tag:
            raise ValueError("wrapped_working_key and wrap_tag must not be empty")


@dataclass(frozen=True, slots=True)
class EncodeGrantAuditRecord:
    """Record grant issuance metadata without retaining working key material."""

    grant_id: str
    root_key_id: str
    algorithm: str
    tenant_id: str
    song_id: str
    export_id: str
    device_id: str
    actor_id: str
    profile_version: str
    request_id: str
    issued_utc: str
    expires_utc: str
    context_digest: str

    def __post_init__(self) -> None:
        """Validate the JSON-safe audit projection."""

        _require_named_texts(self, ("grant_id", "root_key_id", "algorithm", "tenant_id", "song_id", "export_id", "device_id", "actor_id", "profile_version", "request_id", "issued_utc", "expires_utc", "context_digest"))


@dataclass(frozen=True, slots=True)
class LocalKmsKeyring:
    """Issue local test grants from a server-owned root secret."""

    root_key_id: str
    root_secret: bytes
    identifier_factory: Callable[[], str] = lambda: str(uuid4())
    clock: Callable[[], datetime] = lambda: datetime.now(timezone.utc)

    def __post_init__(self) -> None:
        """Validate root key metadata for the local implementation."""

        _require_text(self.root_key_id, "root_key_id")
        if len(self.root_secret) < 32:
            raise ValueError("root_secret must contain at least 32 bytes")

    def issue_encode_grant(self, scope: EncodeGrantScope, device_secret: bytes) -> EncodeGrant:
        """Return one wrapped working key for a scoped desktop encode."""

        _require_device_secret(device_secret)
        grant_id = self.identifier_factory()
        working_key = self._derive_working_key(scope)
        wrapped = _xor(working_key, _wrap_stream(device_secret, grant_id, scope, len(working_key)))
        return EncodeGrant(grant_id, self.root_key_id, LOCAL_KMS_WRAP, scope, wrapped, _wrap_tag(device_secret, grant_id, scope, wrapped), _context_digest(scope))

    def unwrap_encode_grant(self, grant: EncodeGrant, device_secret: bytes, now_utc: datetime | None = None) -> bytes:
        """Return the scoped working key if the grant is valid and unexpired."""

        _require_device_secret(device_secret)
        if grant.root_key_id != self.root_key_id:
            raise ValueError("grant root_key_id does not match keyring")
        if grant.context_digest != _context_digest(grant.scope):
            raise ValueError("grant context digest does not match scope")
        now = now_utc or self.clock()
        _require_aware(now, "now_utc")
        if now >= grant.scope.expires_utc:
            raise ValueError("encode grant is expired")
        expected_tag = _wrap_tag(device_secret, grant.grant_id, grant.scope, grant.wrapped_working_key)
        if not hmac.compare_digest(expected_tag, grant.wrap_tag):
            raise ValueError("encode grant device authentication failed")
        return _xor(grant.wrapped_working_key, _wrap_stream(device_secret, grant.grant_id, grant.scope, len(grant.wrapped_working_key)))

    def _derive_working_key(self, scope: EncodeGrantScope) -> bytes:
        """Derive a deterministic working key from server-owned root material."""

        return hmac.new(self.root_secret, b"working-key|" + _scope_bytes(scope), hashlib.sha256).digest()


def encode_grant_audit_record(grant: EncodeGrant) -> EncodeGrantAuditRecord:
    """Return a durable audit projection for one issued encode grant."""

    return EncodeGrantAuditRecord(
        grant_id=grant.grant_id,
        root_key_id=grant.root_key_id,
        algorithm=grant.algorithm,
        tenant_id=grant.scope.tenant_id,
        song_id=grant.scope.song_id,
        export_id=grant.scope.export_id,
        device_id=grant.scope.device_id,
        actor_id=grant.scope.actor_id,
        profile_version=grant.scope.profile_version,
        request_id=grant.scope.request_id,
        issued_utc=grant.scope.issued_utc.isoformat(),
        expires_utc=grant.scope.expires_utc.isoformat(),
        context_digest=grant.context_digest,
    )


def encode_grant_context_digest(scope: EncodeGrantScope) -> str:
    """Return the audited context digest for one encode grant scope."""

    return _context_digest(scope)


def _scope_bytes(scope: EncodeGrantScope) -> bytes:
    """Return canonical scope bytes for derivation and audit digests."""

    document = {
        "actor_id": scope.actor_id,
        "device_id": scope.device_id,
        "expires_utc": scope.expires_utc.isoformat(),
        "export_id": scope.export_id,
        "issued_utc": scope.issued_utc.isoformat(),
        "profile_version": scope.profile_version,
        "request_id": scope.request_id,
        "song_id": scope.song_id,
        "tenant_id": scope.tenant_id,
    }
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _context_digest(scope: EncodeGrantScope) -> str:
    """Return a stable digest of the grant scope for audit records."""

    return hashlib.sha256(_scope_bytes(scope)).hexdigest()


def _wrap_stream(device_secret: bytes, grant_id: str, scope: EncodeGrantScope, length: int) -> bytes:
    """Expand a device secret into local wrapping bytes."""

    seed = grant_id.encode("utf-8") + b"|" + _scope_bytes(scope)
    stream = hmac.new(device_secret, b"wrap|" + seed, hashlib.sha256).digest()
    while len(stream) < length:
        stream += hmac.new(device_secret, stream, hashlib.sha256).digest()
    return stream[:length]


def _wrap_tag(device_secret: bytes, grant_id: str, scope: EncodeGrantScope, wrapped_key: bytes) -> bytes:
    """Authenticate the local device wrapping context."""

    return hmac.new(device_secret, b"tag|" + grant_id.encode("utf-8") + b"|" + _scope_bytes(scope) + wrapped_key, hashlib.sha256).digest()


def _xor(left: bytes, right: bytes) -> bytes:
    """Return bytewise XOR for equal-length byte strings."""

    return bytes(a ^ b for a, b in zip(left, right, strict=True))


def _require_text(value: str, name: str) -> None:
    """Require one visible text value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _require_named_texts(source: object, names: tuple[str, ...]) -> None:
    """Require visible text values from named attributes."""

    for name in names:
        _require_text(getattr(source, name), name)


def _require_aware(value: datetime, name: str) -> None:
    """Require one timezone-aware timestamp."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")


def _require_device_secret(value: bytes) -> None:
    """Require local device wrapping material."""

    if len(value) < 32:
        raise ValueError("device_secret must contain at least 32 bytes")
