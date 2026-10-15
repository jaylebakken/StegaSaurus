"""Issue encode grants through an AWS-KMS-shaped data-key provider.

The desktop should keep source audio local while production custody keeps
tenant/root material out of the desktop binary. This module defines the managed
provider seam for that direction without importing an AWS SDK directly. A real
deployment injects a KMS client that behaves like `boto3.client("kms")`; tests
inject a fake client and verify the exact encryption context.

Flow:
    scope -> KMS GenerateDataKey(AES_256, encryption context)
          -> plaintext working key for the current encode
          -> ciphertext blob retained as the wrapped grant artifact
          -> JSON-safe audit projection via key_custody.encode_grant_audit_record
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
import hashlib
from typing import Protocol
from uuid import uuid4

from .key_custody import AWS_KMS_DATA_KEY_GRANT, EncodeGrant, EncodeGrantScope, encode_grant_context_digest


class KmsDataKeyClient(Protocol):
    """Describe the KMS client call needed by encode-grant issuance."""

    def generate_data_key(self, **kwargs: object) -> Mapping[str, object]:
        """Return a KMS data-key response with plaintext and ciphertext bytes."""


@dataclass(frozen=True, slots=True)
class KmsIssuedEncodeGrant:
    """Carry one managed grant plus the transient desktop working key."""

    grant: EncodeGrant
    working_key: bytes = field(repr=False)

    def __post_init__(self) -> None:
        """Validate transient working key material."""

        if len(self.working_key) != 32:
            raise ValueError("working_key must be a 32-byte AES-256 data key")


@dataclass(frozen=True, slots=True)
class AwsKmsEncodeGrantProvider:
    """Issue scoped encode grants with an injected AWS KMS data-key client."""

    key_id: str
    client: KmsDataKeyClient
    identifier_factory: Callable[[], str] = lambda: str(uuid4())

    def __post_init__(self) -> None:
        """Validate managed key identity."""

        if not isinstance(self.key_id, str) or not self.key_id.strip():
            raise ValueError("key_id must not be empty")

    def issue_encode_grant(self, scope: EncodeGrantScope) -> KmsIssuedEncodeGrant:
        """Issue one KMS-backed working grant for a scoped desktop encode."""

        context = _encryption_context(scope)
        response = self.client.generate_data_key(KeyId=self.key_id, KeySpec="AES_256", EncryptionContext=context)
        plaintext = _bytes_field(response, "Plaintext")
        ciphertext = _bytes_field(response, "CiphertextBlob")
        grant = EncodeGrant(
            self.identifier_factory(),
            str(response.get("KeyId", self.key_id)),
            AWS_KMS_DATA_KEY_GRANT,
            scope,
            ciphertext,
            _grant_tag(ciphertext, context["context_digest"]),
            context["context_digest"],
        )
        return KmsIssuedEncodeGrant(grant, plaintext)


def _encryption_context(scope: EncodeGrantScope) -> dict[str, str]:
    """Return the KMS encryption context bound to one encode grant."""

    return {
        "tenant_id": scope.tenant_id,
        "song_id": scope.song_id,
        "export_id": scope.export_id,
        "device_id": scope.device_id,
        "actor_id": scope.actor_id,
        "profile_version": scope.profile_version,
        "request_id": scope.request_id,
        "issued_utc": scope.issued_utc.isoformat(),
        "expires_utc": scope.expires_utc.isoformat(),
        "context_digest": encode_grant_context_digest(scope),
    }


def _bytes_field(response: Mapping[str, object], name: str) -> bytes:
    """Return one required bytes field from a KMS response."""

    value = response.get(name)
    if not isinstance(value, bytes) or not value:
        raise ValueError(f"KMS response field {name} must be non-empty bytes")
    return value


def _grant_tag(ciphertext: bytes, context_digest: str) -> bytes:
    """Return a non-secret integrity marker for the ciphertext grant artifact."""

    return hashlib.sha256(b"aws-kms-grant|" + context_digest.encode("ascii") + b"|" + ciphertext).digest()
