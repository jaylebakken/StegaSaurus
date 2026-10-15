"""Record production-shaped backup/restore and key-rotation drill evidence.

Local SQLite rehearsals prove the registry can copy, restore, and re-envelope
records in the application test harness. Production readiness needs a stricter
record: the drill must name the deployed or production-shaped database shape,
capture backup/restore or rotation evidence, and require old-export
verification before the gate can pass.

This module records that evidence only. It does not perform the backup, restore,
KMS rotation, or verification workflow.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

__all__ = [
    "BackupRestoreDrillRecord",
    "KeyRotationDrillRecord",
    "record_backup_restore_drill",
    "record_key_rotation_drill",
]


@dataclass(frozen=True, slots=True)
class BackupRestoreDrillRecord:
    """Summarize one production-shaped backup and restore drill."""

    environment: str
    database_shape: str
    backup_reference: str
    restored_reference: str
    total_elapsed_ms: float
    reviewer_id: str
    drilled_utc: datetime
    production_ready: bool
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate backup/restore drill provenance and timing."""

        for value, name in (
            (self.environment, "environment"),
            (self.database_shape, "database_shape"),
            (self.backup_reference, "backup_reference"),
            (self.restored_reference, "restored_reference"),
            (self.reviewer_id, "reviewer_id"),
        ):
            _require_text(value, name)
        if self.total_elapsed_ms < 0:
            raise ValueError("total_elapsed_ms must not be negative")
        _require_aware(self.drilled_utc, "drilled_utc")
        if self.production_ready and self.blockers:
            raise ValueError("production_ready cannot be true while blockers exist")


@dataclass(frozen=True, slots=True)
class KeyRotationDrillRecord:
    """Summarize one retained-record key rotation and old-export verification drill."""

    environment: str
    database_shape: str
    old_key_reference: str
    new_key_reference: str
    rotated_record_count: int
    verified_old_export_count: int
    reviewer_id: str
    drilled_utc: datetime
    production_ready: bool
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate key-rotation drill provenance and counters."""

        for value, name in (
            (self.environment, "environment"),
            (self.database_shape, "database_shape"),
            (self.old_key_reference, "old_key_reference"),
            (self.new_key_reference, "new_key_reference"),
            (self.reviewer_id, "reviewer_id"),
        ):
            _require_text(value, name)
        for value, name in (
            (self.rotated_record_count, "rotated_record_count"),
            (self.verified_old_export_count, "verified_old_export_count"),
        ):
            if value < 0:
                raise ValueError(f"{name} must not be negative")
        _require_aware(self.drilled_utc, "drilled_utc")
        if self.production_ready and self.blockers:
            raise ValueError("production_ready cannot be true while blockers exist")


def record_backup_restore_drill(
    environment: str,
    database_shape: str,
    backup_reference: str,
    restored_reference: str,
    total_elapsed_ms: float,
    reviewer_id: str,
    drilled_utc: datetime,
) -> BackupRestoreDrillRecord:
    """Create a backup/restore drill record and compute production blockers."""

    blockers: list[str] = []
    if not _production_shaped(database_shape):
        blockers.append("database shape must be managed PostgreSQL or production-shaped")
    if total_elapsed_ms <= 0:
        blockers.append("backup/restore elapsed time must be measured")
    return BackupRestoreDrillRecord(
        environment,
        database_shape,
        backup_reference,
        restored_reference,
        total_elapsed_ms,
        reviewer_id,
        drilled_utc,
        not blockers,
        tuple(blockers),
    )


def record_key_rotation_drill(
    environment: str,
    database_shape: str,
    old_key_reference: str,
    new_key_reference: str,
    rotated_record_count: int,
    verified_old_export_count: int,
    reviewer_id: str,
    drilled_utc: datetime,
) -> KeyRotationDrillRecord:
    """Create a key-rotation drill record and compute production blockers."""

    blockers: list[str] = []
    if not _production_shaped(database_shape):
        blockers.append("database shape must be managed PostgreSQL or production-shaped")
    if rotated_record_count <= 0:
        blockers.append("rotation must include at least one retained record")
    if verified_old_export_count <= 0:
        blockers.append("rotation must verify at least one old export")
    return KeyRotationDrillRecord(
        environment,
        database_shape,
        old_key_reference,
        new_key_reference,
        rotated_record_count,
        verified_old_export_count,
        reviewer_id,
        drilled_utc,
        not blockers,
        tuple(blockers),
    )


def _production_shaped(database_shape: str) -> bool:
    """Return whether a database shape is suitable production-drill evidence."""

    normalized = database_shape.strip().lower()
    return "postgres" in normalized or "production-shaped" in normalized


def _require_text(value: str, name: str) -> None:
    """Require one visible text value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _require_aware(value: datetime, name: str) -> None:
    """Require one timezone-aware timestamp."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
