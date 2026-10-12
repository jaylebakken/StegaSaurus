"""Expose the server-side Saurus registry application contract.

The package defines tenant-scoped domain records, a repository boundary,
canonical private-record serialization, durable local storage, and a thin
versioned API adapter. It does not perform blind handle discovery or audio
processing.
"""

from .api import ApiRequest, ApiResponse, HmacBearerAuthenticator, IdempotencyConflictError, RegistryApi, RegistryAuthenticator, RequestContext, registry_handler
from .api_metrics import RegistryApiMetricsSnapshot, RegistryApiObservation, observe_registry_api_response, registry_api_metrics_snapshot
from .access_review import RegistryAccessProbe, RegistryAccessProbeKind, RegistryAccessReviewSnapshot, registry_access_review_snapshot
from .application import RegistryService
from .capacity import CURRENT_HANDLE_BYTES, HandleCapacityReview, review_handle_capacity
from .domain import ExportRecord, ExportState, IdempotencyRecord, RegistryEvent, SongRecord, StoredAttributionRecord, TenantRecord
from .envelope import LocalHmacStreamCipher, RecordCipher, RecordEnvelope
from .launch import RegistryLaunchDecision, RegistryLaunchDecisionRecord, RegistryLaunchThresholds, evaluate_registry_launch, record_registry_launch_decision
from .maintenance import BackupRestoreRehearsalResult, KeyRotationResult, backup_sqlite_database, rehearse_sqlite_backup_restore, restore_sqlite_database, rotate_sqlite_record_key
from .memory import InMemoryRegistryRepository
from .metrics import RegistryMetricsSnapshot, registry_metrics_snapshot
from .migrations import CURRENT_SCHEMA_VERSION
from .reconciliation import ReservationExpiryResult, expire_stale_reserved_exports
from .repository import HandleConflictError, RegistryRepository
from .reports import (
    SignedVerificationReport,
    VerificationReportPayload,
    build_watermark_report_payload,
    canonical_report_bytes,
    sign_verification_report,
    verify_signed_report,
)
from .retention import RegistryRetentionDecision, RegistryRetentionPolicy, RetentionAction, review_registry_retention
from .schedule import ScheduledRegistryOperation, default_registry_operations, due_registry_operations, mark_registry_operation_run
from .serialization import deserialize_block_record, digest_payload, serialize_block_record
from .sqlite import SQLiteRegistryRepository
from .tenant_export import TenantExportExport, TenantExportManifest, build_tenant_export_manifest

__all__ = [
    "ApiRequest",
    "ApiResponse",
    "BackupRestoreRehearsalResult",
    "CURRENT_SCHEMA_VERSION",
    "CURRENT_HANDLE_BYTES",
    "ExportRecord",
    "ExportState",
    "HandleConflictError",
    "HandleCapacityReview",
    "HmacBearerAuthenticator",
    "IdempotencyConflictError",
    "IdempotencyRecord",
    "InMemoryRegistryRepository",
    "KeyRotationResult",
    "LocalHmacStreamCipher",
    "RecordCipher",
    "RecordEnvelope",
    "ReservationExpiryResult",
    "RegistryAccessProbe",
    "RegistryAccessProbeKind",
    "RegistryAccessReviewSnapshot",
    "RegistryEvent",
    "RegistryAuthenticator",
    "RegistryMetricsSnapshot",
    "RegistryRepository",
    "RegistryService",
    "RegistryApi",
    "RegistryApiMetricsSnapshot",
    "RegistryApiObservation",
    "RegistryLaunchDecision",
    "RegistryLaunchDecisionRecord",
    "RegistryLaunchThresholds",
    "RegistryRetentionDecision",
    "RegistryRetentionPolicy",
    "RetentionAction",
    "RequestContext",
    "SQLiteRegistryRepository",
    "SongRecord",
    "StoredAttributionRecord",
    "TenantRecord",
    "TenantExportExport",
    "TenantExportManifest",
    "SignedVerificationReport",
    "ScheduledRegistryOperation",
    "VerificationReportPayload",
    "build_watermark_report_payload",
    "build_tenant_export_manifest",
    "canonical_report_bytes",
    "default_registry_operations",
    "deserialize_block_record",
    "digest_payload",
    "due_registry_operations",
    "evaluate_registry_launch",
    "expire_stale_reserved_exports",
    "registry_access_review_snapshot",
    "registry_handler",
    "observe_registry_api_response",
    "backup_sqlite_database",
    "restore_sqlite_database",
    "rotate_sqlite_record_key",
    "mark_registry_operation_run",
    "review_handle_capacity",
    "review_registry_retention",
    "registry_metrics_snapshot",
    "registry_api_metrics_snapshot",
    "record_registry_launch_decision",
    "rehearse_sqlite_backup_restore",
    "serialize_block_record",
    "sign_verification_report",
    "verify_signed_report",
]
