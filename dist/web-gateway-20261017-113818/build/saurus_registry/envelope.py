"""Encrypt retained registry records behind explicit envelope metadata.

Production should use a reviewed AEAD primitive with managed key custody. This
module provides the registry-facing envelope contract plus a small deterministic
stdlib implementation for local tests and development, so storage code handles
key identifiers, nonces, tags, and ciphertext instead of plain private records.
"""

from __future__ import annotations

from dataclasses import dataclass
import hashlib
import hmac
import secrets
from typing import Protocol


LOCAL_HMAC_STREAM = "local-hmac-sha256-stream-v1"


@dataclass(frozen=True, slots=True)
class RecordEnvelope:
    """Carry encrypted payload bytes and their key metadata."""

    key_id: str
    algorithm: str
    nonce: bytes
    ciphertext: bytes
    tag: bytes

    def __post_init__(self) -> None:
        """Validate one nonempty envelope."""

        if not self.key_id.strip() or not self.algorithm.strip():
            raise ValueError("key_id and algorithm must not be empty")
        if not self.ciphertext:
            raise ValueError("ciphertext must not be empty")


class RecordCipher(Protocol):
    """Encrypt and decrypt retained attribution payload bytes."""

    def encrypt(self, plaintext: bytes, associated_data: bytes) -> RecordEnvelope:
        """Return one encrypted envelope for plaintext bytes."""

    def decrypt(self, envelope: RecordEnvelope, associated_data: bytes) -> bytes:
        """Return verified plaintext bytes from one envelope."""


@dataclass(frozen=True, slots=True)
class LocalHmacStreamCipher:
    """Provide local-development authenticated envelope encryption."""

    key_id: str
    secret: bytes

    def __post_init__(self) -> None:
        """Require visible key metadata and high-entropy-looking secret bytes."""

        if not self.key_id.strip():
            raise ValueError("key_id must not be empty")
        if len(self.secret) < 32:
            raise ValueError("secret must contain at least 32 bytes")

    def encrypt(self, plaintext: bytes, associated_data: bytes) -> RecordEnvelope:
        """Encrypt bytes with a nonce-derived HMAC stream and authentication tag."""

        if not plaintext:
            raise ValueError("plaintext must not be empty")
        nonce = secrets.token_bytes(16)
        ciphertext = _xor(plaintext, _stream(self.secret, nonce, len(plaintext)))
        tag = _tag(self.secret, associated_data, self.key_id, nonce, ciphertext)
        return RecordEnvelope(self.key_id, LOCAL_HMAC_STREAM, nonce, ciphertext, tag)

    def decrypt(self, envelope: RecordEnvelope, associated_data: bytes) -> bytes:
        """Verify metadata and tag, then decrypt bytes."""

        if envelope.key_id != self.key_id or envelope.algorithm != LOCAL_HMAC_STREAM:
            raise ValueError("record envelope key metadata does not match cipher")
        expected = _tag(self.secret, associated_data, envelope.key_id, envelope.nonce, envelope.ciphertext)
        if not hmac.compare_digest(expected, envelope.tag):
            raise ValueError("record envelope authentication failed")
        return _xor(envelope.ciphertext, _stream(self.secret, envelope.nonce, len(envelope.ciphertext)))


def _stream(secret: bytes, nonce: bytes, length: int) -> bytes:
    """Expand one nonce into a deterministic HMAC keystream."""

    output = bytearray()
    counter = 0
    while len(output) < length:
        output.extend(hmac.new(secret, b"stream" + nonce + counter.to_bytes(8, "big"), hashlib.sha256).digest())
        counter += 1
    return bytes(output[:length])


def _tag(secret: bytes, associated_data: bytes, key_id: str, nonce: bytes, ciphertext: bytes) -> bytes:
    """Authenticate metadata, associated data, nonce, and ciphertext."""

    material = b"|".join((b"tag", key_id.encode("utf-8"), associated_data, nonce, ciphertext))
    return hmac.new(secret, material, hashlib.sha256).digest()


def _xor(left: bytes, right: bytes) -> bytes:
    """Return bytewise XOR for equal-length inputs."""

    return bytes(a ^ b for a, b in zip(left, right, strict=True))
