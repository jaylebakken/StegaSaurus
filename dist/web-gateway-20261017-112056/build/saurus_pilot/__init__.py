"""Expose pilot and production deployment decision records.

The pilot package sits above registry and discovery readiness. It does not
encode audio, crawl the web, or notify clients. Its job is to bind measured
registry, discovery, security, and production evidence to explicit sign-off
before notifications or launch workflows are allowed.
"""

from __future__ import annotations

from .decision import PilotGoNoGoDecisionRecord, PilotOwnerAssignments, record_pilot_go_no_go
from .incident_response import (
    REQUIRED_INCIDENT_DRILL_PHASES,
    REQUIRED_PRODUCTION_INCIDENT_SCENARIOS,
    IncidentDrillPhase,
    ProductionIncidentDrillRecord,
    ProductionIncidentScenario,
    record_production_incident_drill,
)
from .legal_policy import (
    REQUIRED_LEGAL_POLICY_REVIEW_AREAS,
    LegalPolicyReviewArea,
    LegalPolicyReviewRecord,
    record_legal_policy_review,
)
from .kms_live import KmsGrantLiveTestRecord, record_kms_grant_live_test
from .monitoring import (
    REQUIRED_MONITORING_CONTROLS,
    MonitoringControl,
    MonitoringControlEvidence,
    MonitoringReadinessRecord,
    record_monitoring_readiness,
)
from .production import (
    REQUIRED_PRODUCTION_GATES,
    ProductionGate,
    ProductionGateEvidence,
    ProductionLaunchDecisionRecord,
    record_production_launch_decision,
)
from .production_thresholds import ProductionThresholdRecord, record_production_thresholds
from .recovery_drills import (
    BackupRestoreDrillRecord,
    KeyRotationDrillRecord,
    record_backup_restore_drill,
    record_key_rotation_drill,
)
from .retention import RetentionDeletionReadinessRecord, record_retention_deletion_readiness
from .security_review import (
    REQUIRED_SECURITY_REVIEW_AREAS,
    SecurityReviewArea,
    SecurityReviewSignoff,
    record_security_review_signoff,
)
from .scope import PilotScopeRecord, PilotSourceSelection, PilotTrackSelection, record_pilot_scope
from .tenant_isolation import (
    REQUIRED_TENANT_ISOLATION_BOUNDARIES,
    TenantIsolationBoundary,
    TenantIsolationProbeEvidence,
    TenantIsolationReadinessRecord,
    record_tenant_isolation_readiness,
)

__all__ = [
    "PilotGoNoGoDecisionRecord",
    "PilotOwnerAssignments",
    "IncidentDrillPhase",
    "LegalPolicyReviewArea",
    "LegalPolicyReviewRecord",
    "KmsGrantLiveTestRecord",
    "MonitoringControl",
    "MonitoringControlEvidence",
    "MonitoringReadinessRecord",
    "BackupRestoreDrillRecord",
    "KeyRotationDrillRecord",
    "PilotScopeRecord",
    "PilotSourceSelection",
    "PilotTrackSelection",
    "ProductionGate",
    "ProductionGateEvidence",
    "ProductionIncidentDrillRecord",
    "ProductionIncidentScenario",
    "ProductionLaunchDecisionRecord",
    "ProductionThresholdRecord",
    "RetentionDeletionReadinessRecord",
    "REQUIRED_INCIDENT_DRILL_PHASES",
    "REQUIRED_LEGAL_POLICY_REVIEW_AREAS",
    "REQUIRED_MONITORING_CONTROLS",
    "REQUIRED_PRODUCTION_INCIDENT_SCENARIOS",
    "REQUIRED_SECURITY_REVIEW_AREAS",
    "REQUIRED_PRODUCTION_GATES",
    "REQUIRED_TENANT_ISOLATION_BOUNDARIES",
    "SecurityReviewArea",
    "SecurityReviewSignoff",
    "TenantIsolationBoundary",
    "TenantIsolationProbeEvidence",
    "TenantIsolationReadinessRecord",
    "record_pilot_go_no_go",
    "record_pilot_scope",
    "record_legal_policy_review",
    "record_monitoring_readiness",
    "record_backup_restore_drill",
    "record_key_rotation_drill",
    "record_kms_grant_live_test",
    "record_production_incident_drill",
    "record_production_launch_decision",
    "record_production_thresholds",
    "record_retention_deletion_readiness",
    "record_security_review_signoff",
    "record_tenant_isolation_readiness",
]
