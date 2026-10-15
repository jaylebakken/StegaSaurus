"""Expose the server-side Saurus registry application contract.

The package defines tenant-scoped domain records, a repository boundary,
canonical private-record serialization, durable local storage, and a thin
versioned API adapter. It does not perform blind handle discovery or audio
processing.
"""

from .api import ApiRequest, ApiResponse, HmacBearerAuthenticator, IdempotencyConflictError, RegistryApi, RegistryAuthenticator, RequestContext, registry_handler
from .api_metrics import RegistryApiMetricsSnapshot, RegistryApiObservation, observe_registry_api_response, registry_api_metrics_snapshot
from .api_log import RegistryRequestLogRecord, registry_request_log_record
from .access_review import RegistryAccessProbe, RegistryAccessProbeKind, RegistryAccessReviewSnapshot, registry_access_review_snapshot
from .application import RegistryService
from .aws_kms_client import AwsKmsClientConfig, Boto3KmsDataKeyClient
from .aws_kms_grants import AwsKmsEncodeGrantProvider, KmsDataKeyClient, KmsIssuedEncodeGrant
from .capacity import CURRENT_HANDLE_BYTES, HandleCapacityReview, review_handle_capacity
from .copy_review import EvidenceCopyFinding, EvidenceCopyReview, review_evidence_copy
from .deletion import REGISTRY_DELETION_REQUESTED_ACTION, DeletionApprovalStatus, RegistryDeletionApproval, record_registry_deletion_request
from .domain import ExportRecord, ExportState, IdempotencyRecord, RegistryEvent, SongRecord, StoredAttributionRecord, TenantRecord
from .envelope import LocalHmacStreamCipher, RecordCipher, RecordEnvelope
from .grant_audit import ENCODE_GRANT_ISSUED_ACTION, encode_grant_audit_digest, record_encode_grant_issuance
from .key_custody import AWS_KMS_DATA_KEY_GRANT, EncodeGrant, EncodeGrantAuditRecord, EncodeGrantScope, LocalKmsKeyring, encode_grant_audit_record, encode_grant_context_digest
from .launch import RegistryLaunchDecision, RegistryLaunchDecisionRecord, RegistryLaunchThresholds, evaluate_registry_launch, record_registry_launch_decision
from .maintenance import BackupRestoreRehearsalResult, KeyRotationResult, backup_sqlite_database, rehearse_sqlite_backup_restore, restore_sqlite_database, rotate_sqlite_record_key
from .memory import InMemoryRegistryRepository
from .metrics import RegistryMetricsSnapshot, registry_metrics_snapshot
from .migrations import CURRENT_SCHEMA_VERSION
from .postgres_migrations import POSTGRES_SCHEMA_VERSION, postgres_migration_statements, render_postgres_migration_plan
from .postgres import PostgresConnectionSettings, PostgresRegistryRepository
from .reconciliation import ReservationExpiryResult, expire_stale_reserved_exports
from .repository import HandleConflictError, RegistryRepository
from .reports import (
    SignedVerificationReport,
    VerificationReportSummary,
    VerificationReportPayload,
    build_watermark_report_payload,
    canonical_report_bytes,
    sign_verification_report,
    summarize_verification_report,
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
    "AWS_KMS_DATA_KEY_GRANT",
    "AwsKmsClientConfig",
    "AwsKmsEncodeGrantProvider",
    "BackupRestoreRehearsalResult",
    "Boto3KmsDataKeyClient",
    "CURRENT_SCHEMA_VERSION",
    "CURRENT_HANDLE_BYTES",
    "ENCODE_GRANT_ISSUED_ACTION",
    "ExportRecord",
    "ExportState",
    "EncodeGrant",
    "EncodeGrantAuditRecord",
    "EncodeGrantScope",
    "EvidenceCopyFinding",
    "EvidenceCopyReview",
    "HandleConflictError",
    "HandleCapacityReview",
    "HmacBearerAuthenticator",
    "IdempotencyConflictError",
    "IdempotencyRecord",
    "InMemoryRegistryRepository",
    "KeyRotationResult",
    "KmsDataKeyClient",
    "KmsIssuedEncodeGrant",
    "LocalHmacStreamCipher",
    "LocalKmsKeyring",
    "RecordCipher",
    "RecordEnvelope",
    "POSTGRES_SCHEMA_VERSION",
    "PostgresConnectionSettings",
    "PostgresRegistryRepository",
    "REGISTRY_DELETION_REQUESTED_ACTION",
    "ReservationExpiryResult",
    "DeletionApprovalStatus",
    "RegistryAccessProbe",
    "RegistryAccessProbeKind",
    "RegistryAccessReviewSnapshot",
    "RegistryEvent",
    "RegistryAuthenticator",
    "RegistryDeletionApproval",
    "RegistryMetricsSnapshot",
    "RegistryRepository",
    "RegistryService",
    "RegistryApi",
    "RegistryApiMetricsSnapshot",
    "RegistryApiObservation",
    "RegistryRequestLogRecord",
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
    "VerificationReportSummary",
    "build_watermark_report_payload",
    "build_tenant_export_manifest",
    "canonical_report_bytes",
    "default_registry_operations",
    "deserialize_block_record",
    "digest_payload",
    "due_registry_operations",
    "evaluate_registry_launch",
    "encode_grant_audit_record",
    "encode_grant_audit_digest",
    "encode_grant_context_digest",
    "expire_stale_reserved_exports",
    "registry_access_review_snapshot",
    "registry_request_log_record",
    "registry_handler",
    "record_encode_grant_issuance",
    "record_registry_deletion_request",
    "observe_registry_api_response",
    "backup_sqlite_database",
    "restore_sqlite_database",
    "rotate_sqlite_record_key",
    "mark_registry_operation_run",
    "review_handle_capacity",
    "review_evidence_copy",
    "review_registry_retention",
    "registry_metrics_snapshot",
    "postgres_migration_statements",
    "registry_api_metrics_snapshot",
    "record_registry_launch_decision",
    "rehearse_sqlite_backup_restore",
    "render_postgres_migration_plan",
    "serialize_block_record",
    "sign_verification_report",
    "summarize_verification_report",
    "verify_signed_report",
]
