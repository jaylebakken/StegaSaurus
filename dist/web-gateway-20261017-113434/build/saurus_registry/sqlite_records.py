"""Store and restore encrypted attribution records for SQLite.

SQLite persists ciphertext plus key metadata when a cipher is configured. The
repository still returns plaintext `StoredAttributionRecord` values to the
application layer after successful envelope verification.
"""

from __future__ import annotations

import sqlite3

from .domain import StoredAttributionRecord
from .envelope import RecordCipher, RecordEnvelope
from .sqlite_rows import time, time_text


PLAINTEXT_ALGORITHM = "plaintext-local"
PLAINTEXT_KEY_ID = "local-development"


def insert_values(record: StoredAttributionRecord, cipher: RecordCipher | None) -> tuple[object, ...]:
    """Return SQL values for one plaintext record, encrypted when configured."""

    associated_data = _associated_data(record.export_id, record.payload_digest)
    if cipher is None:
        return (
            record.export_id,
            record.schema_version,
            record.payload,
            record.payload_digest,
            time_text(record.created_utc),
            record.key_id,
            record.encryption_algorithm,
            b"",
            b"",
        )
    envelope = cipher.encrypt(record.payload, associated_data)
    return (
        record.export_id,
        record.schema_version,
        envelope.ciphertext,
        record.payload_digest,
        time_text(record.created_utc),
        envelope.key_id,
        envelope.algorithm,
        envelope.nonce,
        envelope.tag,
    )


def stored_record(row: sqlite3.Row, cipher: RecordCipher | None) -> StoredAttributionRecord:
    """Return a decrypted attribution record from one SQLite row."""

    key_id = row["key_id"]
    algorithm = row["encryption_algorithm"]
    payload = bytes(row["payload"])
    if algorithm != PLAINTEXT_ALGORITHM:
        if cipher is None:
            raise ValueError("encrypted attribution record requires a configured cipher")
        envelope = RecordEnvelope(key_id, algorithm, bytes(row["nonce"]), payload, bytes(row["auth_tag"]))
        payload = cipher.decrypt(envelope, _associated_data(row["export_id"], row["payload_digest"]))
    return StoredAttributionRecord(
        row["export_id"],
        int(row["schema_version"]),
        payload,
        row["payload_digest"],
        time(row["created_utc"]),
        key_id,
        algorithm,
    )


def _associated_data(export_id: str, payload_digest: str) -> bytes:
    """Bind ciphertext to stable record identity and plaintext digest."""

    return f"{export_id}:{payload_digest}".encode("utf-8")
