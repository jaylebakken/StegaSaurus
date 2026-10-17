"""Rehearse registry backup, restore, and retained-record key rotation.

These helpers are intentionally small and SQLite-specific. They let application
tests prove that a durable registry can be copied, restored, and re-enveloped
without changing export identity or retained record digests. Production runbooks
still need scheduling, access controls, retention, and managed key custody.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
import sqlite3
from time import perf_counter

from .envelope import RecordCipher
from . import sqlite_records


@dataclass(frozen=True, slots=True)
class KeyRotationResult:
    """Summarize one retained-record re-encryption rehearsal."""

    rotated_count: int
    original_key_ids: tuple[str, ...]
    new_key_id: str


@dataclass(frozen=True, slots=True)
class BackupRestoreRehearsalResult:
    """Summarize one measured backup and restore rehearsal."""

    backup_path: Path
    restored_path: Path
    backup_elapsed_ms: float
    restore_elapsed_ms: float
    total_elapsed_ms: float


def backup_sqlite_database(source_path: str | Path, backup_path: str | Path) -> None:
    """Copy one SQLite registry database into a new backup file."""

    source = Path(source_path)
    backup = Path(backup_path)
    if not source.is_file():
        raise ValueError("source database does not exist")
    if backup.exists():
        raise ValueError("backup database already exists")
    backup.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(f"file:{source}?mode=ro", uri=True) as source_connection:
        with sqlite3.connect(backup) as backup_connection:
            source_connection.backup(backup_connection)


def restore_sqlite_database(backup_path: str | Path, target_path: str | Path, *, overwrite: bool = False) -> None:
    """Restore one SQLite backup into a target database file."""

    backup = Path(backup_path)
    target = Path(target_path)
    if not backup.is_file():
        raise ValueError("backup database does not exist")
    if target.exists() and not overwrite:
        raise ValueError("target database already exists")
    target.parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(f"file:{backup}?mode=ro", uri=True) as backup_connection:
        with sqlite3.connect(target) as target_connection:
            backup_connection.backup(target_connection)


def rehearse_sqlite_backup_restore(
    source_path: str | Path,
    backup_path: str | Path,
    restored_path: str | Path,
    *,
    clock: Callable[[], float] = perf_counter,
) -> BackupRestoreRehearsalResult:
    """Run backup and restore once while recording elapsed milliseconds."""

    started = clock()
    backup_sqlite_database(source_path, backup_path)
    after_backup = clock()
    restore_sqlite_database(backup_path, restored_path)
    completed = clock()
    backup_elapsed = max(0.0, (after_backup - started) * 1000)
    restore_elapsed = max(0.0, (completed - after_backup) * 1000)
    return BackupRestoreRehearsalResult(
        Path(backup_path),
        Path(restored_path),
        backup_elapsed,
        restore_elapsed,
        backup_elapsed + restore_elapsed,
    )


def rotate_sqlite_record_key(
    database_path: str | Path,
    old_cipher: RecordCipher | None,
    new_cipher: RecordCipher,
) -> KeyRotationResult:
    """Re-encrypt every retained record from an old cipher to a new cipher."""

    path = Path(database_path)
    if not path.is_file():
        raise ValueError("database does not exist")
    with sqlite3.connect(path, isolation_level=None) as connection:
        connection.row_factory = sqlite3.Row
        rows = connection.execute("SELECT * FROM attribution_records ORDER BY export_id").fetchall()
        original_key_ids = tuple(sorted({row["key_id"] for row in rows}))
        new_key_id = ""
        connection.execute("BEGIN IMMEDIATE")
        try:
            for row in rows:
                record = sqlite_records.stored_record(row, old_cipher)
                values = sqlite_records.insert_values(record, new_cipher)
                new_key_id = str(values[5])
                connection.execute(
                    """
                    UPDATE attribution_records
                    SET schema_version = ?, payload = ?, payload_digest = ?, created_utc = ?,
                        key_id = ?, encryption_algorithm = ?, nonce = ?, auth_tag = ?
                    WHERE export_id = ?
                    """,
                    values[1:] + (values[0],),
                )
            connection.commit()
        except Exception:
            connection.rollback()
            raise
    return KeyRotationResult(len(rows), original_key_ids, new_key_id)
