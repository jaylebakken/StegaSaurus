"""Expose the public-web discovery service contracts.

Discovery is separate from the private registry. It tracks approved public
sources, connector contracts, URL safety decisions, scheduler state, and review
candidate records. It does not fetch private content, bypass access controls,
or make recipient-attribution claims.
"""

from __future__ import annotations

from .adjudication import CandidateAdjudication, CandidateAdjudicationSnapshot, CandidateReviewLabel, candidate_adjudication_snapshot
from .baseline import DiscoveryBaselineRun
from .connector import DiscoveryConnector
from .controls import ConnectorControlPlane, ConnectorHealthSnapshot
from .coverage import SourceCoverageSnapshot, source_coverage_snapshot
from .dashboard import DiscoveryAlert, DiscoveryAlertSeverity, DiscoveryDashboardSnapshot, discovery_dashboard_snapshot
from .enrollment import DiscoveryPilotEnrollment, enroll_discovery_pilot
from .escalation import ExternalActionApproval, ExternalActionKind, review_external_action
from .feed import FeedEntry, ReviewedFeedConnector
from .fingerprint import (
    FingerprintEvaluation,
    FingerprintMatcher,
    LabeledFingerprintExample,
    choose_threshold,
    evaluate_matcher,
)
from .gates import ConnectorGateResult, ConnectorQualityCase, evaluate_connector_gate
from .incident import DiscoveryIncidentDrill, IncidentAction, IncidentDrillResult, IncidentStep
from .live_gate import LiveCrawlGateDecision, evaluate_live_crawl_gate
from .launch_readiness import (
    DiscoveryLegalPolicyReviewRecord,
    DiscoveryRecognitionEngineSelection,
    DiscoveryThresholdCalibration,
    PublicSourceSelection,
    RepresentativeCorpusSummary,
    record_discovery_threshold_calibration,
)
from .media import DecodedMedia, MediaLimits, decode_public_media
from .media_cost import MediaCostRecord, MediaCostSnapshot, media_cost_snapshot
from .models import (
    CandidateEvidenceClass,
    CandidateEvidenceDecision,
    CandidateRecord,
    ConnectorPolicy,
    DiscoveryTarget,
    PageCandidate,
    ReviewState,
    SourceReview,
    classify_candidate_evidence,
)
from .optout import OptOutRequest, OptOutResult, apply_opt_out
from .pilot import DiscoveryPilotDecision, DiscoveryPilotDecisionRecord, DiscoveryPilotMetrics, DiscoveryPilotThresholds, evaluate_discovery_pilot, record_discovery_pilot_decision
from .scheduler import DiscoveryScheduler, JobState
from .review import ReviewAction, ReviewQueue, ReviewSnapshot
from .review_metrics import ReviewMetricsSnapshot, review_metrics_snapshot
from .source_metrics import FeedSourceMetricsSnapshot, feed_source_metrics_snapshot
from .sources import SourceCatalog, SourceCatalogEntry
from .url_policy import FetchDecision, canonicalize_url, dedupe_urls, evaluate_fetch_url

__all__ = [
    "CandidateEvidenceClass",
    "CandidateEvidenceDecision",
    "CandidateAdjudication",
    "CandidateAdjudicationSnapshot",
    "CandidateRecord",
    "CandidateReviewLabel",
    "ConnectorPolicy",
    "ConnectorGateResult",
    "ConnectorControlPlane",
    "ConnectorHealthSnapshot",
    "ConnectorQualityCase",
    "DecodedMedia",
    "DiscoveryConnector",
    "DiscoveryAlert",
    "DiscoveryAlertSeverity",
    "DiscoveryBaselineRun",
    "DiscoveryDashboardSnapshot",
    "DiscoveryIncidentDrill",
    "DiscoveryLegalPolicyReviewRecord",
    "DiscoveryPilotDecision",
    "DiscoveryPilotDecisionRecord",
    "DiscoveryPilotMetrics",
    "DiscoveryPilotEnrollment",
    "DiscoveryPilotThresholds",
    "DiscoveryScheduler",
    "DiscoveryTarget",
    "DiscoveryRecognitionEngineSelection",
    "DiscoveryThresholdCalibration",
    "ExternalActionApproval",
    "ExternalActionKind",
    "FetchDecision",
    "FeedEntry",
    "FeedSourceMetricsSnapshot",
    "FingerprintEvaluation",
    "FingerprintMatcher",
    "IncidentAction",
    "IncidentDrillResult",
    "IncidentStep",
    "JobState",
    "LabeledFingerprintExample",
    "LiveCrawlGateDecision",
    "MediaLimits",
    "MediaCostRecord",
    "MediaCostSnapshot",
    "OptOutRequest",
    "OptOutResult",
    "PageCandidate",
    "PublicSourceSelection",
    "RepresentativeCorpusSummary",
    "ReviewState",
    "ReviewAction",
    "ReviewQueue",
    "ReviewMetricsSnapshot",
    "ReviewSnapshot",
    "ReviewedFeedConnector",
    "SourceReview",
    "SourceCatalog",
    "SourceCatalogEntry",
    "SourceCoverageSnapshot",
    "apply_opt_out",
    "canonicalize_url",
    "candidate_adjudication_snapshot",
    "choose_threshold",
    "classify_candidate_evidence",
    "dedupe_urls",
    "decode_public_media",
    "discovery_dashboard_snapshot",
    "evaluate_matcher",
    "evaluate_discovery_pilot",
    "evaluate_fetch_url",
    "evaluate_connector_gate",
    "evaluate_live_crawl_gate",
    "enroll_discovery_pilot",
    "feed_source_metrics_snapshot",
    "source_coverage_snapshot",
    "review_metrics_snapshot",
    "review_external_action",
    "media_cost_snapshot",
    "record_discovery_pilot_decision",
    "record_discovery_threshold_calibration",
]
