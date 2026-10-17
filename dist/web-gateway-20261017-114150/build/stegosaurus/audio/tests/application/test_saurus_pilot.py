"""Test cross-system pilot and production launch decision records.

These tests keep launch signoff separate from audio encoding, statistical
detection, and future attribution decoding. The records tested here do not
claim robustness or deploy a service; they require explicit evidence and human
owners before risky workflows can advance.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from saurus_pilot import (
    REQUIRED_INCIDENT_DRILL_PHASES,
    REQUIRED_LEGAL_POLICY_REVIEW_AREAS,
    REQUIRED_MONITORING_CONTROLS,
    REQUIRED_PRODUCTION_GATES,
    REQUIRED_TENANT_ISOLATION_BOUNDARIES,
    IncidentDrillPhase,
    LegalPolicyReviewArea,
    LegalPolicyReviewRecord,
    KmsGrantLiveTestRecord,
    MonitoringControl,
    MonitoringControlEvidence,
    MonitoringReadinessRecord,
    BackupRestoreDrillRecord,
    KeyRotationDrillRecord,
    PilotScopeRecord,
    PilotSourceSelection,
    PilotTrackSelection,
    ProductionGate,
    ProductionGateEvidence,
    ProductionIncidentDrillRecord,
    ProductionIncidentScenario,
    ProductionLaunchDecisionRecord,
    ProductionThresholdRecord,
    RetentionDeletionReadinessRecord,
    TenantIsolationBoundary,
    TenantIsolationProbeEvidence,
    TenantIsolationReadinessRecord,
    record_backup_restore_drill,
    record_key_rotation_drill,
    record_kms_grant_live_test,
    record_legal_policy_review,
    record_monitoring_readiness,
    record_production_incident_drill,
    record_production_launch_decision,
    record_production_thresholds,
    record_retention_deletion_readiness,
    record_pilot_scope,
    record_tenant_isolation_readiness,
)
from saurus_registry import AWS_KMS_DATA_KEY_GRANT, DeletionApprovalStatus, RegistryDeletionApproval, RegistryLaunchThresholds
from saurus_discovery import DiscoveryPilotThresholds


NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)

PILOT_THRESHOLDS = DiscoveryPilotThresholds(0.8, 0.1, 0.0, 24.0, 15.0, 0, 48.0)


def _ready_evidence() -> tuple[ProductionGateEvidence, ...]:
    """Build passing evidence for every required production gate."""

    return tuple(
        ProductionGateEvidence(gate, f"evidence:{gate.value}", True, "reviewer-1")
        for gate in REQUIRED_PRODUCTION_GATES
    )


def _live_monitoring_controls() -> tuple[MonitoringControlEvidence, ...]:
    """Build live evidence for every required monitoring control."""

    return tuple(
        MonitoringControlEvidence(control, f"monitoring:{control.value}", "pager-owner", True)
        for control in REQUIRED_MONITORING_CONTROLS
    )


def _passing_tenant_isolation_evidence() -> tuple[TenantIsolationProbeEvidence, ...]:
    """Build passing evidence for every tenant-isolation boundary."""

    return tuple(
        TenantIsolationProbeEvidence(boundary, f"isolation:{boundary.value}", "security-reviewer", True)
        for boundary in REQUIRED_TENANT_ISOLATION_BOUNDARIES
    )


def _registry_thresholds() -> RegistryLaunchThresholds:
    """Build explicit registry launch thresholds for production threshold tests."""

    return RegistryLaunchThresholds(0.99, 0.02, 1.0, 1.0, 0, 0, 1.05, 250.0, 0.01, 4_000, 25, 0, 2_000.0)


def test_production_launch_decision_requires_all_gates_and_signoff() -> None:
    """Block production launch until every required gate is ready."""

    missing = record_production_launch_decision(
        (ProductionGateEvidence(ProductionGate.EXTERNAL_SECURITY_REVIEW, "security-report", True, "reviewer-1"),),
        "launch-owner",
        "security-owner",
        "policy-owner",
        NOW,
        "launch requested too early",
        request_launch=True,
    )
    not_ready_evidence = (
        ProductionGateEvidence(ProductionGate.EXTERNAL_SECURITY_REVIEW, "security-report", True, "reviewer-1"),
        ProductionGateEvidence(ProductionGate.KMS_GRANTS_LIVE, "kms-report", False, "reviewer-1"),
    )
    not_ready = record_production_launch_decision(
        not_ready_evidence,
        "launch-owner",
        "security-owner",
        "policy-owner",
        NOW,
        "launch blocked by KMS",
        request_launch=True,
    )
    approved = record_production_launch_decision(
        _ready_evidence(),
        "launch-owner",
        "security-owner",
        "policy-owner",
        NOW,
        "all production gates reviewed",
        request_launch=True,
    )

    assert isinstance(approved, ProductionLaunchDecisionRecord)
    assert not missing.launch_approved
    assert "kms_grants_live" in missing.blockers[0]
    assert not not_ready.launch_approved
    assert not_ready.blockers[-1] == "not-ready production gates: kms_grants_live"
    assert approved.launch_approved
    assert approved.blockers == ()
    with pytest.raises(ValueError, match="policy_owner_id"):
        record_production_launch_decision(_ready_evidence(), "launch-owner", "security-owner", "", NOW, "missing policy owner")
    with pytest.raises(TypeError, match="ProductionGate"):
        ProductionGateEvidence("kms_grants_live", "kms-report", True, "reviewer-1")


def test_production_incident_drill_requires_runbook_phases() -> None:
    """Require contain, assess, recover, communicate, and review drill evidence."""

    incomplete = record_production_incident_drill(
        ProductionIncidentScenario.REGISTRY_CREDENTIAL_EXPOSURE,
        "drill-1",
        "docs/operations-runbooks.md#registry-credential-exposure",
        "ops-owner",
        "reviewer-1",
        NOW,
        (IncidentDrillPhase.CONTAIN, IncidentDrillPhase.ASSESS),
        "credential exposure tabletop started",
    )
    complete = record_production_incident_drill(
        ProductionIncidentScenario.MISTAKEN_DISCOVERY_ALERT,
        "drill-2",
        "docs/operations-runbooks.md#mistaken-discovery-alert-or-external-notice",
        "policy-owner",
        "reviewer-1",
        NOW,
        REQUIRED_INCIDENT_DRILL_PHASES,
        "mistaken alert drill covered correction and notification pause",
    )

    assert isinstance(complete, ProductionIncidentDrillRecord)
    assert not incomplete.complete
    assert "recover" in incomplete.blockers[0]
    assert complete.complete
    assert complete.blockers == ()
    with pytest.raises(ValueError, match="reviewer_id"):
        record_production_incident_drill(
            ProductionIncidentScenario.MISTAKEN_DISCOVERY_ALERT,
            "drill-3",
            "docs/operations-runbooks.md",
            "policy-owner",
            "",
            NOW,
            REQUIRED_INCIDENT_DRILL_PHASES,
            "missing reviewer",
        )
    with pytest.raises(TypeError, match="IncidentDrillPhase"):
        record_production_incident_drill(
            ProductionIncidentScenario.REGISTRY_CREDENTIAL_EXPOSURE,
            "drill-4",
            "docs/operations-runbooks.md",
            "ops-owner",
            "reviewer-1",
            NOW,
            ("contain",),
            "invalid phase",
        )


def test_legal_policy_review_requires_scope_and_counsel_approval() -> None:
    """Block production legal readiness without full scope and counsel approval."""

    incomplete = record_legal_policy_review(
        "counsel-1",
        "policy-owner",
        "client-policy-draft",
        NOW,
        (LegalPolicyReviewArea.EVIDENCE_LANGUAGE,),
        False,
        "review started",
    )
    ready = record_legal_policy_review(
        "counsel-1",
        "policy-owner",
        "client-policy-v1",
        NOW,
        REQUIRED_LEGAL_POLICY_REVIEW_AREAS,
        True,
        "all legal and policy areas approved",
    )

    assert isinstance(ready, LegalPolicyReviewRecord)
    assert not incomplete.production_ready
    assert "discovery_source_policy" in incomplete.blockers[0]
    assert incomplete.blockers[-1] == "counsel approval is missing"
    assert ready.production_ready
    assert ready.blockers == ()
    with pytest.raises(ValueError, match="client_policy_reference"):
        record_legal_policy_review("counsel-1", "policy-owner", "", NOW, REQUIRED_LEGAL_POLICY_REVIEW_AREAS, True, "missing policy")
    with pytest.raises(TypeError, match="LegalPolicyReviewArea"):
        record_legal_policy_review("counsel-1", "policy-owner", "client-policy-v1", NOW, ("evidence_language",), True, "invalid area")


def test_monitoring_readiness_requires_live_controls_and_paging_owner() -> None:
    """Block production monitoring readiness until all controls are live."""

    incomplete = record_monitoring_readiness(
        (MonitoringControlEvidence(MonitoringControl.REGISTRY_API_METRICS, "dashboard-1", "pager-owner", True),),
        NOW,
        "ops-reviewer",
        "registry dashboard exists",
    )
    not_live = record_monitoring_readiness(
        (
            MonitoringControlEvidence(MonitoringControl.REGISTRY_API_METRICS, "dashboard-1", "pager-owner", True),
            MonitoringControlEvidence(MonitoringControl.BUDGET_ALERT, "budget-1", "pager-owner", False),
        ),
        NOW,
        "ops-reviewer",
        "budget alert not subscribed",
    )
    ready = record_monitoring_readiness(_live_monitoring_controls(), NOW, "ops-reviewer", "all monitoring controls live")

    assert isinstance(ready, MonitoringReadinessRecord)
    assert not incomplete.production_ready
    assert "registry_health" in incomplete.blockers[0]
    assert not not_live.production_ready
    assert not_live.blockers[-1] == "not-live monitoring controls: budget_alert"
    assert ready.production_ready
    assert ready.blockers == ()
    with pytest.raises(ValueError, match="paging_owner_id"):
        MonitoringControlEvidence(MonitoringControl.PAGER_ROUTE, "pager-route", "", True)
    with pytest.raises(TypeError, match="MonitoringControl"):
        MonitoringControlEvidence("budget_alert", "budget-1", "pager-owner", True)


def test_tenant_isolation_readiness_requires_all_boundaries_to_pass() -> None:
    """Block production readiness until all isolation boundaries have passing probes."""

    incomplete = record_tenant_isolation_readiness(
        (
            TenantIsolationProbeEvidence(
                TenantIsolationBoundary.REGISTRY_API_AUTHORIZATION,
                "access-review:api",
                "security-reviewer",
                True,
            ),
        ),
        NOW,
        "security-reviewer",
        "API probe passed",
    )
    failing = record_tenant_isolation_readiness(
        (
            TenantIsolationProbeEvidence(
                TenantIsolationBoundary.REGISTRY_API_AUTHORIZATION,
                "access-review:api",
                "security-reviewer",
                True,
            ),
            TenantIsolationProbeEvidence(
                TenantIsolationBoundary.DISCOVERY_PROJECTION,
                "access-review:discovery",
                "security-reviewer",
                False,
            ),
        ),
        NOW,
        "security-reviewer",
        "discovery projection probe failed",
    )
    ready = record_tenant_isolation_readiness(
        _passing_tenant_isolation_evidence(),
        NOW,
        "security-reviewer",
        "all tenant-isolation probes passed",
    )

    assert isinstance(ready, TenantIsolationReadinessRecord)
    assert not incomplete.production_ready
    assert "registry_repository_scope" in incomplete.blockers[0]
    assert not failing.production_ready
    assert failing.blockers[-1] == "failing tenant-isolation boundaries: discovery_projection"
    assert ready.production_ready
    assert ready.blockers == ()
    with pytest.raises(ValueError, match="reviewer_id"):
        TenantIsolationProbeEvidence(TenantIsolationBoundary.KMS_GRANT_SCOPE, "kms-probe", "", True)
    with pytest.raises(TypeError, match="TenantIsolationBoundary"):
        TenantIsolationProbeEvidence("kms_grant_scope", "kms-probe", "security-reviewer", True)


def test_recovery_drills_require_production_shape_and_old_export_verification() -> None:
    """Require production-shaped backup/restore and key-rotation evidence."""

    backup_blocked = record_backup_restore_drill(
        "alpha",
        "sqlite demo database",
        "backup-1",
        "restore-1",
        0.0,
        "ops-reviewer",
        NOW,
    )
    backup_ready = record_backup_restore_drill(
        "alpha",
        "managed PostgreSQL alpha database",
        "backup-2",
        "restore-2",
        1_250.0,
        "ops-reviewer",
        NOW,
    )
    rotation_blocked = record_key_rotation_drill(
        "alpha",
        "managed PostgreSQL alpha database",
        "alias/old",
        "alias/new",
        3,
        0,
        "ops-reviewer",
        NOW,
    )
    rotation_ready = record_key_rotation_drill(
        "alpha",
        "managed PostgreSQL alpha database",
        "alias/old",
        "alias/new",
        3,
        2,
        "ops-reviewer",
        NOW,
    )

    assert isinstance(backup_ready, BackupRestoreDrillRecord)
    assert isinstance(rotation_ready, KeyRotationDrillRecord)
    assert not backup_blocked.production_ready
    assert "PostgreSQL" in backup_blocked.blockers[0]
    assert "elapsed time" in backup_blocked.blockers[-1]
    assert backup_ready.production_ready
    assert backup_ready.blockers == ()
    assert not rotation_blocked.production_ready
    assert rotation_blocked.blockers == ("rotation must verify at least one old export",)
    assert rotation_ready.production_ready
    assert rotation_ready.blockers == ()
    with pytest.raises(ValueError, match="reviewer_id"):
        record_backup_restore_drill("alpha", "managed PostgreSQL", "backup", "restore", 1.0, "", NOW)
    with pytest.raises(ValueError, match="rotated_record_count"):
        record_key_rotation_drill("alpha", "managed PostgreSQL", "old", "new", -1, 1, "ops-reviewer", NOW)


def test_kms_grant_live_test_requires_managed_alias_algorithm_and_audit_evidence() -> None:
    """Require deployed KMS, IAM, CloudTrail, grant audit, and smoke evidence."""

    bad = record_kms_grant_live_test(
        "alpha",
        "alias/demo/local",
        "local-kms-hmac-wrap-v1",
        "short",
        "iam-policy-1",
        "cloudtrail-event-1",
        "grant-audit-1",
        "smoke-1",
        "security-reviewer",
        NOW,
    )
    ready = record_kms_grant_live_test(
        "alpha",
        "alias/saurus/alpha/encode-grants",
        AWS_KMS_DATA_KEY_GRANT,
        "a" * 64,
        "iam-policy-1",
        "cloudtrail-event-1",
        "grant-audit-1",
        "smoke-1",
        "security-reviewer",
        NOW,
    )

    assert isinstance(ready, KmsGrantLiveTestRecord)
    assert not bad.production_ready
    assert bad.blockers == (
        "KMS key alias must use the Saurus encode-grants alias path",
        "grant algorithm must be AWS KMS data-key grant",
        "context digest must be a SHA-256 hex digest",
    )
    assert ready.production_ready
    assert ready.blockers == ()
    with pytest.raises(ValueError, match="cloudtrail_reference"):
        record_kms_grant_live_test(
            "alpha",
            "alias/saurus/alpha/encode-grants",
            AWS_KMS_DATA_KEY_GRANT,
            "a" * 64,
            "iam-policy-1",
            "",
            "grant-audit-1",
            "smoke-1",
            "security-reviewer",
            NOW,
        )


def test_pilot_scope_requires_licensed_tracks_sources_and_thresholds() -> None:
    """Require written pilot scope before baseline or go/no-go review."""

    track = PilotTrackSelection("tenant-1", "song-1", "Demo Song", "license:file-1")
    source = PilotSourceSelection("public-feed", "source-policy:file-1", "policy-reviewer")
    missing = record_pilot_scope("scope-1", "pilot-owner", NOW, (), (), None)
    cross_tenant = record_pilot_scope(
        "scope-2",
        "pilot-owner",
        NOW,
        (track, PilotTrackSelection("tenant-2", "song-2", "Other Song", "license:file-2")),
        (source,),
        PILOT_THRESHOLDS,
    )
    ready = record_pilot_scope("scope-3", "pilot-owner", NOW, (track,), (source,), PILOT_THRESHOLDS)

    assert isinstance(ready, PilotScopeRecord)
    assert not missing.ready
    assert missing.blockers == (
        "pilot tracks are missing",
        "approved public sources are missing",
        "numeric pilot thresholds are missing",
    )
    assert not cross_tenant.ready
    assert cross_tenant.blockers == ("pilot tracks must belong to one tenant",)
    assert ready.ready
    assert ready.blockers == ()
    with pytest.raises(ValueError, match="ownership_reference"):
        PilotTrackSelection("tenant-1", "song-1", "Demo Song", "")
    with pytest.raises(ValueError, match="policy_reviewer_id"):
        PilotSourceSelection("public-feed", "source-policy:file-1", "")


def test_retention_deletion_readiness_requires_policy_backup_and_audit_gate() -> None:
    """Block production deletion readiness until policy and implementation pass."""

    draft = RegistryDeletionApproval("policy-draft", "owner", "counsel", NOW, DeletionApprovalStatus.DRAFT, "draft only")
    approved = RegistryDeletionApproval("policy-v1", "owner", "counsel", NOW, DeletionApprovalStatus.COUNSEL_APPROVED, "approved")
    blocked = record_retention_deletion_readiness(
        draft,
        "retention-review-1",
        "backup-1",
        "deletion-audit-1",
        False,
        "ops-reviewer",
        NOW,
    )
    ready = record_retention_deletion_readiness(
        approved,
        "retention-review-1",
        "backup-1",
        "deletion-audit-1",
        True,
        "ops-reviewer",
        NOW,
    )

    assert isinstance(ready, RetentionDeletionReadinessRecord)
    assert not blocked.production_ready
    assert blocked.blockers == (
        "retention/deletion policy is not counsel approved",
        "destructive deletion implementation is not enabled",
    )
    assert ready.production_ready
    assert ready.blockers == ()
    with pytest.raises(ValueError, match="backup_or_export_reference"):
        record_retention_deletion_readiness(approved, "retention-review-1", "", "deletion-audit-1", True, "ops-reviewer", NOW)


def test_production_thresholds_require_real_pilot_data_reference() -> None:
    """Require production launch thresholds to cite real pilot measurements."""

    draft = record_production_thresholds("local-alpha-draft", _registry_thresholds(), "ops-reviewer", NOW, "draft thresholds")
    ready = record_production_thresholds("pilot-measurements-2026-10", _registry_thresholds(), "ops-reviewer", NOW, "pilot-derived thresholds")

    assert isinstance(ready, ProductionThresholdRecord)
    assert not draft.ready
    assert draft.blockers == ("pilot data reference must identify real pilot measurements",)
    assert ready.ready
    assert ready.blockers == ()
    with pytest.raises(ValueError, match="pilot_data_reference"):
        record_production_thresholds("", _registry_thresholds(), "ops-reviewer", NOW, "missing reference")
