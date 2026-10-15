"""Test public-web discovery contracts without live crawling.

Discovery must start with policy and provenance, not a scraper. These tests
exercise reviewed connector contracts, URL canonicalization, SSRF guardrails,
job budgets, and the global kill switch while keeping recipient attribution and
private registry records out of the discovery layer.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from io import BytesIO
from pathlib import Path
import wave

import pytest

from saurus_discovery import (
    CandidateAdjudication,
    CandidateAdjudicationSnapshot,
    CandidateRecord,
    CandidateEvidenceClass,
    CandidateReviewLabel,
    ConnectorControlPlane,
    ConnectorPolicy,
    ConnectorQualityCase,
    DecodedMedia,
    DiscoveryPilotDecisionRecord,
    DiscoveryPilotMetrics,
    DiscoveryPilotEnrollment,
    DiscoveryPilotThresholds,
    DiscoveryIncidentDrill,
    DiscoveryScheduler,
    DiscoveryTarget,
    DiscoveryAlertSeverity,
    DiscoveryBaselineRun,
    DiscoveryDashboardSnapshot,
    ExternalActionApproval,
    ExternalActionKind,
    FeedEntry,
    FeedSourceMetricsSnapshot,
    DiscoveryLegalPolicyReviewRecord,
    DiscoveryRecognitionEngineSelection,
    DiscoveryThresholdCalibration,
    FingerprintMatcher,
    IncidentStep,
    JobState,
    LabeledFingerprintExample,
    LiveCrawlGateDecision,
    MediaCostRecord,
    MediaCostSnapshot,
    MediaLimits,
    OptOutRequest,
    PageCandidate,
    PublicSourceSelection,
    ReviewQueue,
    RepresentativeCorpusSummary,
    ReviewMetricsSnapshot,
    ReviewState,
    ReviewedFeedConnector,
    SourceCatalog,
    SourceCoverageSnapshot,
    SourceReview,
    apply_opt_out,
    canonicalize_url,
    candidate_adjudication_snapshot,
    choose_threshold,
    classify_candidate_evidence,
    dedupe_urls,
    decode_public_media,
    discovery_dashboard_snapshot,
    enroll_discovery_pilot,
    evaluate_matcher,
    evaluate_discovery_pilot,
    evaluate_connector_gate,
    evaluate_fetch_url,
    evaluate_live_crawl_gate,
    media_cost_snapshot,
    feed_source_metrics_snapshot,
    record_discovery_threshold_calibration,
    record_discovery_pilot_decision,
    review_metrics_snapshot,
    review_external_action,
    source_coverage_snapshot,
)
from saurus_discovery.readiness import DiscoveryBaselineRehearsalResult, run_no_notification_baseline_rehearsal
from saurus_pilot import (
    REQUIRED_SECURITY_REVIEW_AREAS,
    PilotGoNoGoDecisionRecord,
    PilotOwnerAssignments,
    SecurityReviewArea,
    SecurityReviewSignoff,
    record_pilot_go_no_go,
    record_security_review_signoff,
)
from saurus_registry import (
    BackupRestoreRehearsalResult,
    RegistryAccessReviewSnapshot,
    RegistryApiMetricsSnapshot,
    RegistryLaunchThresholds,
    RegistryMetricsSnapshot,
    record_registry_launch_decision,
)


NOW = datetime(2026, 10, 12, 12, 0, tzinfo=timezone.utc)


@dataclass(frozen=True, slots=True)
class StaticConnector:
    """Return predetermined public candidates for scheduler tests."""

    policy: ConnectorPolicy
    review: SourceReview
    candidates: tuple[PageCandidate, ...]

    def search(self, target: DiscoveryTarget) -> tuple[PageCandidate, ...]:
        """Return static candidates for one target song."""

        return self.candidates


@dataclass(frozen=True, slots=True)
class StaticMatcher:
    """Return predetermined scores for fingerprint evaluation tests."""

    engine_version: str
    scores: dict[str, float]

    def score(self, media: DecodedMedia, public_fingerprint_id: str) -> float:
        """Return one score keyed by content digest and target fingerprint."""

        return self.scores[f"{media.content_digest}:{public_fingerprint_id}"]


def _review(approved: bool = True) -> SourceReview:
    """Build one source review fixture."""

    return SourceReview("public-feed", "ops", approved, True, True, "ops@example.test", 14, NOW)


def _policy() -> ConnectorPolicy:
    """Build one strict connector policy fixture."""

    return ConnectorPolicy("public-feed", ("example.com",), max_results_per_job=1)


def _target() -> DiscoveryTarget:
    """Build one client-approved target fixture."""

    return DiscoveryTarget("tenant-1", "song-1", "Night Drive", "fingerprint-public-1")


def _wav_bytes(seconds: float = 0.25, sample_rate: int = 8000, sample_width: int = 2) -> bytes:
    """Build a compact silent PCM WAV payload."""

    frame_count = int(seconds * sample_rate)
    sample = b"\x00" * sample_width
    buffer = BytesIO()
    with wave.open(buffer, "wb") as output:
        output.setnchannels(1)
        output.setsampwidth(sample_width)
        output.setframerate(sample_rate)
        output.writeframes(sample * frame_count)
    return buffer.getvalue()


def _media(label: str) -> DecodedMedia:
    """Build compact decoded-media fixtures for fingerprint evaluation."""

    return DecodedMedia("audio/wav", label, 8000, 1, 2, 8000, 1.0)


def test_url_policy_canonicalizes_dedupes_and_blocks_ssrf() -> None:
    """Normalize public URLs and reject unsafe destinations before fetching."""

    policy = _policy()
    canonical = canonicalize_url("HTTPS://Example.COM:443/watch?b=2&a=1#frag")
    deduped = dedupe_urls(("https://example.com/a#one", "https://EXAMPLE.com/a#two"))
    private = evaluate_fetch_url("https://127.0.0.1/private", ConnectorPolicy("loop", ("127.0.0.1",)))
    wrong_domain = evaluate_fetch_url("https://not-example.test/a", policy)
    allowed = evaluate_fetch_url("https://media.example.com/watch", policy)

    assert canonical == "https://example.com/watch?a=1&b=2"
    assert deduped == ("https://example.com/a",)
    assert (private.allowed, private.reason) == (False, "host resolves to a blocked address class")
    assert (wrong_domain.allowed, wrong_domain.reason) == (False, "host is not approved for connector")
    assert allowed.allowed


def test_scheduler_requires_approved_source_review_and_honors_budget() -> None:
    """Run only approved connectors and cap emitted page candidates."""

    candidates = (
        PageCandidate("public-feed", "https://example.com/one", "One", NOW),
        PageCandidate("public-feed", "https://example.com/two", "Two", NOW),
    )
    connector = StaticConnector(_policy(), _review(), candidates)
    scheduler = DiscoveryScheduler()
    job = scheduler.enqueue("job-1", _target(), connector, NOW)
    complete, output = scheduler.run_next(connector)

    assert job.state is JobState.QUEUED
    assert complete.state is JobState.COMPLETE
    assert complete.result_count == 1
    assert tuple(candidate.title for candidate in output) == ("One",)


def test_scheduler_kill_switch_and_unapproved_source_review() -> None:
    """Block unreviewed connectors and kill queued jobs when disabled."""

    target = _target()
    unapproved = StaticConnector(_policy(), _review(False), ())
    approved = StaticConnector(_policy(), _review(), ())
    scheduler = DiscoveryScheduler()

    with pytest.raises(ValueError, match="not approved"):
        scheduler.enqueue("bad", target, unapproved, NOW)
    scheduler.enqueue("job-1", target, approved, NOW)
    scheduler.disable()
    killed, output = scheduler.run_next(approved)

    assert killed.state is JobState.KILLED
    assert killed.error == "global discovery kill switch is enabled"
    assert output == ()


def test_connector_control_plane_disables_one_connector_and_records_health() -> None:
    """Record connector canaries, budgets, and per-source disable decisions."""

    candidates = (
        PageCandidate("public-feed", "https://example.com/one", "One", NOW),
        PageCandidate("public-feed", "https://example.com/two", "Two", NOW),
    )
    connector = StaticConnector(ConnectorPolicy("public-feed", ("example.com",), max_results_per_job=2), _review(), candidates)
    control_plane = ConnectorControlPlane()
    scheduler = DiscoveryScheduler(control_plane)
    control_plane.record_canary("public-feed", passed=True, checked_utc=NOW, latency_ms=12.5)
    scheduler.enqueue("job-1", _target(), connector, NOW)

    complete, output = scheduler.run_next(connector)
    disabled = control_plane.disable("public-feed", "source returned policy errors")
    scheduler.enqueue("job-2", _target(), connector, NOW)
    killed, killed_output = scheduler.run_next(connector)
    snapshot = control_plane.snapshot("public-feed")

    assert complete.state is JobState.COMPLETE
    assert tuple(candidate.title for candidate in output) == ("One", "Two")
    assert disabled.enabled is False
    assert killed.state is JobState.KILLED
    assert killed_output == ()
    assert snapshot.run_count == 1
    assert snapshot.candidate_count == 2
    assert snapshot.canary_passed is True
    assert snapshot.disabled_reason == "source returned policy errors"


def test_source_catalog_requires_owner_policy_and_control_before_expansion() -> None:
    """Expand sources only after review, policy, and per-source control records exist."""

    control_plane = ConnectorControlPlane()
    catalog = SourceCatalog(control_plane)
    policy = ConnectorPolicy("public-feed", ("example.com",), max_results_per_job=2)
    review = SourceReview("public-feed", "ops-owner", True, True, True, "ops@example.test", 14, NOW)

    entry = catalog.register(policy, review)
    ready = catalog.ready_sources()
    control_plane.disable("public-feed", "source paused before launch")
    paused = catalog.entry("public-feed")

    assert entry.owner == "ops-owner"
    assert entry.expansion_ready
    assert ready == (entry,)
    assert paused.expansion_ready is False
    with pytest.raises(ValueError, match="already registered"):
        catalog.register(policy, review)
    with pytest.raises(ValueError, match="identifiers"):
        SourceCatalog().register(ConnectorPolicy("other-feed", ("example.com",)), review)


def test_discovery_pilot_enrollment_requires_ready_sources_and_one_tenant() -> None:
    """Enroll approved targets only against reviewed ready source records."""

    control_plane = ConnectorControlPlane()
    catalog = SourceCatalog(control_plane)
    catalog.register(ConnectorPolicy("public-feed", ("example.com",), max_results_per_job=2), SourceReview("public-feed", "ops-owner", True, True, True, "ops@example.test", 14, NOW))
    target = _target()

    enrollment = enroll_discovery_pilot("enrollment-1", "ops-owner", NOW, (target,), catalog)

    assert isinstance(enrollment, DiscoveryPilotEnrollment)
    assert enrollment.targets == (target,)
    assert enrollment.source_ids == ("public-feed",)
    control_plane.disable("public-feed", "source paused")
    with pytest.raises(ValueError, match="reviewed source"):
        enroll_discovery_pilot("enrollment-2", "ops-owner", NOW, (target,), catalog)
    second_catalog = SourceCatalog()
    second_catalog.register(ConnectorPolicy("public-feed", ("example.com",), max_results_per_job=2), SourceReview("public-feed", "ops-owner", True, True, True, "ops@example.test", 14, NOW))
    with pytest.raises(ValueError, match="one tenant"):
        enroll_discovery_pilot("enrollment-3", "ops-owner", NOW, (target, DiscoveryTarget("tenant-2", "song-2", "Other", "fp-2")), second_catalog)


def test_source_coverage_snapshot_reports_status_without_completeness_claim() -> None:
    """Publish source coverage and health counters without live crawling."""

    control_plane = ConnectorControlPlane()
    catalog = SourceCatalog(control_plane)
    approved = SourceReview("public-feed", "ops-owner", True, True, True, "ops@example.test", 14, NOW)
    unapproved = SourceReview("new-feed", "policy-owner", False, True, True, "policy@example.test", 14, NOW)
    catalog.register(ConnectorPolicy("public-feed", ("example.com",), max_results_per_job=2), approved)
    catalog.register(ConnectorPolicy("new-feed", ("new.example",), max_results_per_job=2), unapproved)
    control_plane.record_run("public-feed", 3)
    control_plane.record_run("new-feed", 0, error="policy denied")
    control_plane.disable("new-feed", "not approved")

    snapshot = source_coverage_snapshot(catalog)

    assert isinstance(snapshot, SourceCoverageSnapshot)
    assert snapshot.registered_source_count == 2
    assert snapshot.approved_source_count == 1
    assert snapshot.ready_source_count == 1
    assert snapshot.disabled_source_count == 1
    assert snapshot.erroring_source_count == 1
    assert snapshot.total_run_count == 2
    assert snapshot.total_candidate_count == 3
    assert snapshot.total_failure_count == 1
    assert snapshot.source_statuses == ("new-feed:unapproved", "public-feed:ready")


def test_discovery_dashboard_snapshot_surfaces_source_and_review_alerts() -> None:
    """Summarize discovery dashboard alerts without sending notifications."""

    control_plane = ConnectorControlPlane()
    catalog = SourceCatalog(control_plane)
    review = SourceReview("public-feed", "ops-owner", True, True, True, "ops@example.test", 14, NOW)
    catalog.register(ConnectorPolicy("public-feed", ("example.com",), max_results_per_job=2), review)
    control_plane.record_run("public-feed", 1, error="source returned bad metadata")
    control_plane.record_canary("public-feed", passed=False, checked_utc=NOW, latency_ms=40.0, reason="canary page changed")
    queue = ReviewQueue()
    first = CandidateRecord("candidate-1", "tenant-1", "song-1", "public-feed", "https://example.com/a", 0.8, 12.0, ReviewState.PENDING, NOW, NOW + timedelta(days=7))
    second = CandidateRecord("candidate-2", "tenant-1", "song-1", "public-feed", "https://example.com/b", 0.8, 12.0, ReviewState.PENDING, NOW, NOW + timedelta(days=7))
    queue.add(first)
    queue.add(second)

    snapshot = discovery_dashboard_snapshot(catalog, queue, pending_warning_count=1, median_review_warning_minutes=15.0)

    assert isinstance(snapshot, DiscoveryDashboardSnapshot)
    assert snapshot.coverage.erroring_source_count == 1
    assert snapshot.review_metrics.pending_count == 2
    assert snapshot.blocker_count == 1
    assert snapshot.warning_count == 2
    assert tuple(alert.code for alert in snapshot.alerts) == ("source-error", "canary-failed", "review-backlog")
    assert snapshot.alerts[1].severity is DiscoveryAlertSeverity.BLOCKER
    assert snapshot.alerts[1].source_id == "public-feed"


def test_discovery_dashboard_snapshot_reports_healthy_or_blocked_setup() -> None:
    """Report no-source blockers and healthy local dashboard state."""

    empty = discovery_dashboard_snapshot(SourceCatalog(), ReviewQueue(), pending_warning_count=0, median_review_warning_minutes=0.0)
    control_plane = ConnectorControlPlane()
    catalog = SourceCatalog(control_plane)
    catalog.register(ConnectorPolicy("public-feed", ("example.com",), max_results_per_job=2), SourceReview("public-feed", "ops-owner", True, True, True, "ops@example.test", 14, NOW))
    healthy = discovery_dashboard_snapshot(catalog, ReviewQueue(), pending_warning_count=0, median_review_warning_minutes=0.0)

    assert empty.alerts[0].code == "no-sources"
    assert empty.blocker_count == 1
    assert tuple(alert.code for alert in healthy.alerts) == ("healthy",)
    assert healthy.alerts[0].severity is DiscoveryAlertSeverity.INFO
    with pytest.raises(ValueError, match="pending_warning_count"):
        discovery_dashboard_snapshot(catalog, ReviewQueue(), pending_warning_count=-1, median_review_warning_minutes=0.0)


def test_reviewed_feed_connector_filters_policy_and_target_matches() -> None:
    """Emit only matching, canonical, policy-approved feed candidates."""

    connector = ReviewedFeedConnector(
        _policy(),
        _review(),
        (
            FeedEntry("Night Drive public page", "https://example.com/watch?b=2&a=1#frag", "", NOW),
            FeedEntry("Night Drive duplicate page", "https://EXAMPLE.com/watch?a=1&b=2", "", NOW),
            FeedEntry("Night Drive off-domain page", "https://outside.test/watch", "", NOW),
            FeedEntry("Unrelated title", "https://example.com/other", "nothing relevant", NOW),
            FeedEntry("Fingerprint match", "https://media.example.com/fp", "fingerprint-public-1", NOW),
        ),
    )
    output = connector.search(_target())

    assert tuple(candidate.url for candidate in output) == ("https://example.com/watch?a=1&b=2",)
    assert output[0].source_id == "public-feed"


def test_feed_source_metrics_snapshot_counts_denials_and_duplicates() -> None:
    """Measure feed filtering outcomes without crawling or notifications."""

    entries = (
        FeedEntry("Night Drive primary", "https://example.com/watch?b=2&a=1#frag", "", NOW),
        FeedEntry("Night Drive duplicate", "https://EXAMPLE.com/watch?a=1&b=2", "", NOW),
        FeedEntry("Night Drive off-domain", "https://outside.test/watch", "", NOW),
        FeedEntry("Night Drive bad scheme", "http://example.com/watch", "", NOW),
        FeedEntry("Unrelated", "https://example.com/other", "different", NOW),
    )

    snapshot = feed_source_metrics_snapshot(_policy(), _target(), entries)

    assert isinstance(snapshot, FeedSourceMetricsSnapshot)
    assert snapshot.entry_count == 5
    assert snapshot.target_match_count == 4
    assert snapshot.emitted_candidate_count == 1
    assert snapshot.policy_denial_count == 2
    assert snapshot.duplicate_count == 1
    with pytest.raises(ValueError, match="policy_denial_count"):
        FeedSourceMetricsSnapshot("public-feed", 1, 1, 1, -1, 0)


def test_reviewed_feed_connector_requires_approved_source() -> None:
    """Reject feed connectors before search when source review is incomplete."""

    with pytest.raises(ValueError, match="not approved"):
        ReviewedFeedConnector(_policy(), _review(False), ())


def test_connector_gate_evaluates_policy_security_load_and_quality() -> None:
    """Gate the reviewed feed connector before treating it as launchable."""

    connector = ReviewedFeedConnector(
        ConnectorPolicy("public-feed", ("example.com",), max_results_per_job=2),
        _review(),
        (
            FeedEntry("Night Drive", "https://example.com/a", "", NOW),
            FeedEntry("Night Drive mirror", "https://media.example.com/b", "", NOW),
            FeedEntry("Wrong domain", "https://outside.test/c", "Night Drive", NOW),
        ),
    )
    passing = evaluate_connector_gate(
        connector,
        (ConnectorQualityCase(_target(), minimum_results=2),),
        ("https://127.0.0.1/private", "file:///tmp/private.wav", "https://outside.test/c"),
    )
    failing = evaluate_connector_gate(
        connector,
        (ConnectorQualityCase(DiscoveryTarget("tenant-1", "missing", "Other Song", "other-fp"), minimum_results=1),),
        ("https://127.0.0.1/private",),
    )

    assert passing.passed
    assert passing.reasons == ()
    assert not failing.passed
    assert failing.quality_passed is False
    assert "quality" in failing.reasons[0]


def test_candidate_record_keeps_song_match_review_state_only() -> None:
    """Represent a song-level candidate without recipient attribution fields."""

    candidate = CandidateRecord(
        "candidate-1",
        "tenant-1",
        "song-1",
        "public-feed",
        "https://example.com/watch",
        0.82,
        18.5,
        ReviewState.PENDING,
        NOW,
        NOW + timedelta(days=14),
    )

    assert candidate.state is ReviewState.PENDING
    assert candidate.match_score == 0.82
    assert not hasattr(candidate, "recipient_label")


def test_candidate_adjudication_snapshot_labels_pilot_outcomes() -> None:
    """Count true, false, duplicate, and unusable labels separately from workflow state."""

    candidates = (
        CandidateRecord("candidate-1", "tenant-1", "song-1", "public-feed", "https://example.com/a", 0.8, 12.0, ReviewState.ACCEPTED, NOW, NOW + timedelta(days=7)),
        CandidateRecord("candidate-2", "tenant-1", "song-1", "public-feed", "https://example.com/b", 0.6, 8.0, ReviewState.REJECTED, NOW, NOW + timedelta(days=7)),
        CandidateRecord("candidate-3", "tenant-1", "song-1", "public-feed", "https://example.com/c", 0.7, 10.0, ReviewState.SUPPRESSED, NOW, NOW + timedelta(days=7)),
        CandidateRecord("candidate-4", "tenant-1", "song-1", "public-feed", "https://example.com/d", 0.5, 3.0, ReviewState.REJECTED, NOW, NOW + timedelta(days=7)),
        CandidateRecord("candidate-5", "tenant-1", "song-1", "public-feed", "https://example.com/e", 0.4, 2.0, ReviewState.PENDING, NOW, NOW + timedelta(days=7)),
    )
    adjudications = (
        CandidateAdjudication("candidate-1", CandidateReviewLabel.TRUE_MATCH, "reviewer-1", "confirmed song", NOW),
        CandidateAdjudication("candidate-2", CandidateReviewLabel.FALSE_MATCH, "reviewer-1", "wrong song", NOW),
        CandidateAdjudication("candidate-3", CandidateReviewLabel.DUPLICATE, "reviewer-1", "same canonical page", NOW),
        CandidateAdjudication("candidate-4", CandidateReviewLabel.UNUSABLE, "reviewer-1", "preview too short", NOW),
    )

    snapshot = candidate_adjudication_snapshot(candidates, adjudications)

    assert isinstance(snapshot, CandidateAdjudicationSnapshot)
    assert snapshot.candidate_count == 5
    assert snapshot.adjudicated_count == 4
    assert (snapshot.true_match_count, snapshot.false_match_count) == (1, 1)
    assert (snapshot.duplicate_count, snapshot.unusable_count) == (1, 1)
    assert snapshot.unlabeled_candidate_ids == ("candidate-5",)
    with pytest.raises(ValueError, match="more than once"):
        candidate_adjudication_snapshot(candidates, adjudications + (adjudications[0],))
    with pytest.raises(ValueError, match="candidate set"):
        candidate_adjudication_snapshot(candidates, (CandidateAdjudication("missing", CandidateReviewLabel.FALSE_MATCH, "reviewer-1", "not queued", NOW),))


def test_discovery_baseline_run_requires_no_client_notifications() -> None:
    """Bind baseline source and review metrics while blocking notifications."""

    source_metrics = FeedSourceMetricsSnapshot("public-feed", 5, 4, 2, 1, 1)
    adjudication = CandidateAdjudicationSnapshot(3, 2, 1, 1, 0, 0, ("candidate-3",))

    run = DiscoveryBaselineRun("baseline-1", "pilot-reviewer", NOW, NOW + timedelta(hours=2), (source_metrics,), adjudication)

    assert run.client_notification_count == 0
    assert run.emitted_candidate_count == 2
    assert run.policy_denial_count == 1
    assert run.duplicate_count == 1
    assert run.adjudication.unlabeled_candidate_ids == ("candidate-3",)
    with pytest.raises(ValueError, match="client notifications"):
        DiscoveryBaselineRun("baseline-2", "pilot-reviewer", NOW, NOW + timedelta(hours=2), (source_metrics,), adjudication, client_notification_count=1)
    with pytest.raises(ValueError, match="source_metrics"):
        DiscoveryBaselineRun("baseline-3", "pilot-reviewer", NOW, NOW + timedelta(hours=2), (), adjudication)


def test_live_crawl_gate_defaults_to_disabled_until_pilot_evidence_exists() -> None:
    """Keep live crawling off until enrollment, baseline, corpus, legal, and engine gates pass."""

    source_metrics = FeedSourceMetricsSnapshot("public-feed", 5, 4, 2, 1, 1)
    adjudication = CandidateAdjudicationSnapshot(2, 1, 1, 0, 0, 0, ())
    baseline = DiscoveryBaselineRun("baseline-1", "pilot-reviewer", NOW, NOW + timedelta(hours=2), (source_metrics,), adjudication)
    enrollment = DiscoveryPilotEnrollment("enrollment-1", "ops-owner", NOW, (_target(),), ("public-feed",))

    blocked = evaluate_live_crawl_gate(None, (), 0, legal_policy_approved=False, recognition_engine_name="")
    enabled = evaluate_live_crawl_gate(enrollment, (baseline,), 12, legal_policy_approved=True, recognition_engine_name="licensed-song-match-v1")

    assert isinstance(enabled, LiveCrawlGateDecision)
    assert not blocked.enabled
    assert "approved target and source enrollment is missing" in blocked.blockers
    assert "no-notification baseline has not run" in blocked.blockers
    assert enabled.enabled
    assert enabled.blockers == ()
    with pytest.raises(ValueError, match="representative_corpus_case_count"):
        evaluate_live_crawl_gate(enrollment, (baseline,), -1, legal_policy_approved=True, recognition_engine_name="engine")


def test_discovery_no_notification_baseline_rehearsal_keeps_live_crawl_disabled() -> None:
    """Run the local discovery baseline rehearsal without client notifications."""

    result = run_no_notification_baseline_rehearsal()

    assert isinstance(result, DiscoveryBaselineRehearsalResult)
    assert result.baseline.client_notification_count == 0
    assert result.baseline.emitted_candidate_count >= 1
    assert result.baseline.adjudication.unlabeled_candidate_ids == ()
    assert not result.live_gate.enabled
    assert "legal and source-policy approval is missing" in result.live_gate.blockers


def test_candidate_evidence_marks_short_public_preview_as_song_match_only() -> None:
    """Keep short public matches out of attribution follow-up."""

    short = CandidateRecord(
        "candidate-short",
        "tenant-1",
        "song-1",
        "public-feed",
        "https://example.com/short",
        0.9,
        4.0,
        ReviewState.PENDING,
        NOW,
        NOW + timedelta(days=14),
    )
    long = CandidateRecord(
        "candidate-long",
        "tenant-1",
        "song-1",
        "public-feed",
        "https://example.com/long",
        0.91,
        18.0,
        ReviewState.PENDING,
        NOW,
        NOW + timedelta(days=14),
    )

    short_decision = classify_candidate_evidence(short, minimum_attribution_seconds=15.0)
    long_decision = classify_candidate_evidence(long, minimum_attribution_seconds=15.0)

    assert short_decision.evidence_class is CandidateEvidenceClass.SONG_MATCH_ONLY
    assert "too short" in short_decision.reason
    assert long_decision.evidence_class is CandidateEvidenceClass.ATTRIBUTION_ELIGIBLE
    assert not hasattr(short_decision, "recipient_label")
    with pytest.raises(ValueError, match="minimum_attribution_seconds"):
        classify_candidate_evidence(short, minimum_attribution_seconds=-1.0)


def test_external_action_approval_records_human_and_counsel_gate() -> None:
    """Allow a neutral external action only after accepted attribution-eligible review."""

    accepted = CandidateRecord("candidate-1", "tenant-1", "song-1", "public-feed", "https://example.com/a", 0.92, 20.0, ReviewState.ACCEPTED, NOW, NOW + timedelta(days=7))
    pending = CandidateRecord("candidate-2", "tenant-1", "song-1", "public-feed", "https://example.com/b", 0.92, 20.0, ReviewState.PENDING, NOW, NOW + timedelta(days=7))
    decision = classify_candidate_evidence(accepted, minimum_attribution_seconds=15.0)
    pending_decision = classify_candidate_evidence(pending, minimum_attribution_seconds=15.0)

    approval = review_external_action(accepted, decision, ExternalActionKind.LEGAL_WORKFLOW, "reviewer-1", "counsel-1", "client-policy-1", "Public audio is a candidate match for registered song song-1.", NOW)
    blocked_state = review_external_action(pending, pending_decision, ExternalActionKind.EXTERNAL_NOTICE, "reviewer-1", "counsel-1", "client-policy-1", "Public audio is a candidate match for registered song song-1.", NOW)
    blocked_language = review_external_action(accepted, decision, ExternalActionKind.EXTERNAL_NOTICE, "reviewer-1", "counsel-1", "client-policy-1", "The recipient leaked the song.", NOW)

    assert isinstance(approval, ExternalActionApproval)
    assert approval.allowed
    assert approval.reasons == ()
    assert approval.counsel_reviewer_id == "counsel-1"
    assert not blocked_state.allowed
    assert "accepted" in blocked_state.reasons[0]
    assert not blocked_language.allowed
    assert "neutral" in blocked_language.reasons[0]


def test_external_action_approval_blocks_song_match_only_attribution_steps() -> None:
    """Keep short public matches from becoming attribution handoffs or notices."""

    candidate = CandidateRecord("candidate-1", "tenant-1", "song-1", "public-feed", "https://example.com/a", 0.91, 4.0, ReviewState.ACCEPTED, NOW, NOW + timedelta(days=7))
    decision = classify_candidate_evidence(candidate, minimum_attribution_seconds=15.0)

    client_alert = review_external_action(candidate, decision, ExternalActionKind.CLIENT_ALERT, "reviewer-1", "counsel-1", "client-policy-1", "Public audio is a candidate match for registered song song-1.", NOW)
    external_notice = review_external_action(candidate, decision, ExternalActionKind.EXTERNAL_NOTICE, "reviewer-1", "counsel-1", "client-policy-1", "Public audio is a candidate match for registered song song-1.", NOW)
    legal_workflow = review_external_action(candidate, decision, ExternalActionKind.LEGAL_WORKFLOW, "reviewer-1", "counsel-1", "client-policy-1", "Public audio is a candidate match for registered song song-1.", NOW)

    assert client_alert.allowed
    assert not external_notice.allowed
    assert "song-match-only" in external_notice.reasons[0]
    assert not legal_workflow.allowed
    assert "legal workflow" in legal_workflow.reasons[0]
    assert not hasattr(external_notice, "recipient_label")
    with pytest.raises(ValueError, match="identifiers"):
        review_external_action(CandidateRecord("other", "tenant-1", "song-1", "public-feed", "https://example.com/b", 0.9, 20.0, ReviewState.ACCEPTED, NOW, NOW + timedelta(days=7)), decision, ExternalActionKind.CLIENT_ALERT, "reviewer-1", "counsel-1", "client-policy-1", "Public audio is a candidate match.", NOW)


def test_review_queue_records_decisions_and_provenance() -> None:
    """Accept, reject, or suppress candidates with reviewer-visible reasons."""

    queue = ReviewQueue()
    first = CandidateRecord("candidate-1", "tenant-1", "song-1", "public-feed", "https://example.com/a", 0.8, 12.0, ReviewState.PENDING, NOW, NOW + timedelta(days=7))
    second = CandidateRecord("candidate-2", "tenant-1", "song-1", "public-feed", "https://example.com/b", 0.3, 6.0, ReviewState.PENDING, NOW, NOW + timedelta(days=7))
    queue.add(second)
    queue.add(first)
    accepted = queue.decide("candidate-1", ReviewState.ACCEPTED, "reviewer-1", "song candidate for follow-up", NOW)
    rejected = queue.decide("candidate-2", ReviewState.REJECTED, "reviewer-2", "wrong song", NOW)

    assert tuple(candidate.candidate_id for candidate in queue.pending(NOW)) == ()
    assert accepted.state is ReviewState.ACCEPTED
    assert rejected.state is ReviewState.REJECTED
    assert queue.snapshot("candidate-1").actions[0].reason == "song candidate for follow-up"
    with pytest.raises(ValueError, match="no longer pending"):
        queue.decide("candidate-1", ReviewState.SUPPRESSED, "reviewer-1", "duplicate", NOW)


def test_review_metrics_snapshot_measures_review_burden_and_latency() -> None:
    """Summarize review burden without changing candidate states."""

    queue = ReviewQueue()
    first = CandidateRecord("candidate-1", "tenant-1", "song-1", "public-feed", "https://example.com/a", 0.8, 12.0, ReviewState.PENDING, NOW, NOW + timedelta(days=7))
    second = CandidateRecord("candidate-2", "tenant-1", "song-1", "public-feed", "https://example.com/b", 0.3, 6.0, ReviewState.PENDING, NOW, NOW + timedelta(days=7))
    third = CandidateRecord("candidate-3", "tenant-1", "song-1", "public-feed", "https://example.com/c", 0.6, 9.0, ReviewState.PENDING, NOW, NOW + timedelta(days=7))
    queue.add(first)
    queue.add(second)
    queue.add(third)
    queue.decide("candidate-1", ReviewState.ACCEPTED, "reviewer-1", "song candidate for follow-up", NOW + timedelta(minutes=10))
    queue.decide("candidate-2", ReviewState.REJECTED, "reviewer-2", "wrong song", NOW + timedelta(minutes=30))

    snapshot = review_metrics_snapshot(queue)

    assert isinstance(snapshot, ReviewMetricsSnapshot)
    assert snapshot.candidate_count == 3
    assert snapshot.pending_count == 1
    assert snapshot.reviewed_count == 2
    assert snapshot.accepted_count == 1
    assert snapshot.rejected_count == 1
    assert snapshot.median_review_minutes == pytest.approx(20)
    assert snapshot.accepted_median_review_minutes == pytest.approx(10)


def test_review_queue_expires_pending_candidates() -> None:
    """Move stale candidates out of the pending queue with a system action."""

    queue = ReviewQueue()
    candidate = CandidateRecord(
        "candidate-1",
        "tenant-1",
        "song-1",
        "public-feed",
        "https://example.com/a",
        0.8,
        12.0,
        ReviewState.PENDING,
        NOW,
        NOW + timedelta(days=1),
    )
    queue.add(candidate)
    expired = queue.expire(NOW + timedelta(days=2))
    snapshot = queue.snapshot("candidate-1")

    assert expired[0].state is ReviewState.EXPIRED
    assert queue.pending(NOW + timedelta(days=2)) == ()
    assert snapshot.actions[0].reviewer_id == "system"


def test_review_queue_deletes_candidate_with_redacted_tombstone() -> None:
    """Exercise discovery candidate deletion without retaining the public URL."""

    queue = ReviewQueue()
    candidate = CandidateRecord("candidate-1", "tenant-1", "song-1", "public-feed", "https://example.com/a", 0.8, 12.0, ReviewState.PENDING, NOW, NOW + timedelta(days=7))
    queue.add(candidate)

    deleted = queue.delete("candidate-1", "privacy-ops", "source deletion request", NOW)
    snapshot = queue.snapshot("candidate-1")

    assert deleted.state is ReviewState.DELETED
    assert deleted.canonical_url == "deleted://candidate"
    assert snapshot.actions[-1].state is ReviewState.DELETED
    assert tuple(item.candidate_id for item in queue.pending(NOW)) == ()
    with pytest.raises(ValueError, match="already deleted"):
        queue.delete("candidate-1", "privacy-ops", "repeat", NOW)


def test_opt_out_suppresses_matching_pending_candidates_and_records_completion() -> None:
    """Apply a source opt-out without touching unrelated discovery candidates."""

    queue = ReviewQueue()
    first = CandidateRecord("candidate-1", "tenant-1", "song-1", "public-feed", "https://example.com/a", 0.8, 12.0, ReviewState.PENDING, NOW, NOW + timedelta(days=7))
    second = CandidateRecord("candidate-2", "tenant-1", "song-1", "public-feed", "https://example.com/b", 0.8, 12.0, ReviewState.PENDING, NOW, NOW + timedelta(days=7))
    queue.add(first)
    queue.add(second)
    request = OptOutRequest("opt-1", "public-feed", "https://example.com/a", "source-owner", "remove page from monitoring", NOW)

    result = apply_opt_out(queue, request, NOW + timedelta(hours=6))

    assert result.suppressed_candidate_ids == ("candidate-1",)
    assert result.completion_hours == 6.0
    assert queue.snapshot("candidate-1").candidate.state is ReviewState.SUPPRESSED
    assert queue.snapshot("candidate-2").candidate.state is ReviewState.PENDING


def test_discovery_incident_drill_records_containment_restore_and_review() -> None:
    """Rehearse discovery incident response without live crawling."""

    control_plane = ConnectorControlPlane()
    drill = DiscoveryIncidentDrill("incident-1", control_plane)
    drill.record(IncidentStep.DETECTED, "ops", "unexpected source failures", NOW)

    incomplete = drill.result()
    contained = drill.contain_connector("public-feed", "ops", "pause source during investigation", NOW + timedelta(minutes=5))
    drill.record(IncidentStep.RESTORED, "ops", "registry restore rehearsal checked", NOW + timedelta(minutes=20))
    drill.record(IncidentStep.REVIEWED, "ops", "post-incident review completed", NOW + timedelta(minutes=30))
    complete = drill.result()

    assert incomplete.complete is False
    assert IncidentStep.CONTAINED in incomplete.missing_steps
    assert contained.step is IncidentStep.CONTAINED
    assert control_plane.snapshot("public-feed").enabled is False
    assert complete.complete
    assert complete.missing_steps == ()
    assert tuple(action.step for action in drill.actions()) == (
        IncidentStep.DETECTED,
        IncidentStep.CONTAINED,
        IncidentStep.RESTORED,
        IncidentStep.REVIEWED,
    )


def test_review_queue_rejects_duplicate_or_invalid_reviews() -> None:
    """Protect queue identity and keep arbitrary state transitions out."""

    queue = ReviewQueue()
    candidate = CandidateRecord("candidate-1", "tenant-1", "song-1", "public-feed", "https://example.com/a", 0.8, 12.0, ReviewState.PENDING, NOW, NOW + timedelta(days=7))
    queue.add(candidate)

    with pytest.raises(ValueError, match="already queued"):
        queue.add(candidate)
    with pytest.raises(ValueError, match="not allowed"):
        queue.decide("candidate-1", ReviewState.EXPIRED, "reviewer-1", "bad state", NOW)


def test_media_worker_decodes_bounded_pcm_wav_metadata() -> None:
    """Extract safe public media metadata without invoking external codecs."""

    payload = _wav_bytes()
    decoded = decode_public_media(payload, "application/octet-stream", MediaLimits(max_bytes=10_000, max_seconds=1.0))

    assert decoded.mime_type == "audio/wav"
    assert decoded.sample_rate == 8000
    assert decoded.channel_count == 1
    assert decoded.sample_width_bytes == 2
    assert decoded.duration_seconds == 0.25
    assert len(decoded.content_digest) == 64


def test_media_cost_snapshot_tracks_fetch_and_evidence_size() -> None:
    """Measure media byte costs without retaining public media."""

    snapshot = media_cost_snapshot(
        (
            MediaCostRecord("public-feed", fetched_bytes=1_000, retained_evidence_bytes=100, useful_candidate=True),
            MediaCostRecord("public-feed", fetched_bytes=500, retained_evidence_bytes=50, useful_candidate=False),
        )
    )
    empty = media_cost_snapshot(())

    assert isinstance(snapshot, MediaCostSnapshot)
    assert snapshot.record_count == 2
    assert snapshot.bytes_fetched == 1_500
    assert snapshot.retained_evidence_bytes == 150
    assert snapshot.useful_candidate_count == 1
    assert snapshot.fetched_bytes_per_useful_candidate == pytest.approx(1_500)
    assert snapshot.retained_bytes_per_useful_candidate == pytest.approx(150)
    assert empty.fetched_bytes_per_useful_candidate == 0.0


def test_media_cost_records_validate_byte_counters() -> None:
    """Reject byte metrics that would hide invalid evidence accounting."""

    with pytest.raises(ValueError, match="source_id"):
        MediaCostRecord("", fetched_bytes=1, retained_evidence_bytes=0, useful_candidate=False)
    with pytest.raises(ValueError, match="fetched_bytes"):
        MediaCostRecord("public-feed", fetched_bytes=-1, retained_evidence_bytes=0, useful_candidate=False)
    with pytest.raises(ValueError, match="retained_evidence_bytes"):
        MediaCostRecord("public-feed", fetched_bytes=1, retained_evidence_bytes=2, useful_candidate=False)


@pytest.mark.parametrize(
    "payload,mime,limits,match",
    [
        (b"PK\x03\x04archive", "application/zip", MediaLimits(), "archive"),
        (b"x" * 12, "audio/mpeg", MediaLimits(max_bytes=100), "MIME"),
        (b"x" * 12, "audio/wav", MediaLimits(max_bytes=4), "byte limit"),
        (_wav_bytes(seconds=2.0), "audio/wav", MediaLimits(max_bytes=100_000, max_seconds=0.5), "duration"),
        (_wav_bytes(sample_width=1), "audio/wav", MediaLimits(max_bytes=100_000), "geometry"),
    ],
    ids=("archive", "unsupported-mime", "byte-limit", "duration-limit", "bad-geometry"),
)
def test_media_worker_rejects_unsafe_or_out_of_scope_payloads(payload: bytes, mime: str, limits: MediaLimits, match: str) -> None:
    """Reject archives, unsupported media, oversized data, and unsupported WAV geometry."""

    with pytest.raises(ValueError, match=match):
        decode_public_media(payload, mime, limits)


def test_fingerprint_evaluation_reports_measured_rates() -> None:
    """Score held-out positives and negatives without inventing thresholds."""

    matcher: FingerprintMatcher = StaticMatcher(
        "static-v1",
        {
            "pos-a:fp-1": 0.91,
            "pos-b:fp-1": 0.42,
            "neg-a:fp-1": 0.81,
            "neg-b:fp-1": 0.10,
        },
    )
    examples = (
        LabeledFingerprintExample(_media("pos-a"), "fp-1", True),
        LabeledFingerprintExample(_media("pos-b"), "fp-1", True),
        LabeledFingerprintExample(_media("neg-a"), "fp-1", False),
        LabeledFingerprintExample(_media("neg-b"), "fp-1", False),
    )
    evaluation = evaluate_matcher(matcher, examples, 0.8)

    assert evaluation.engine_version == "static-v1"
    assert evaluation.true_positive_count == 1
    assert evaluation.false_positive_count == 1
    assert evaluation.false_negative_count == 1
    assert evaluation.precision == 0.5
    assert evaluation.miss_rate == 0.5
    assert evaluation.false_positive_rate == 0.5


def test_fingerprint_threshold_selection_uses_false_positive_bound() -> None:
    """Choose the measured threshold with bounded false positives and lowest miss rate."""

    matcher = StaticMatcher("static-v1", {"pos-a:fp-1": 0.92, "pos-b:fp-1": 0.82, "neg-a:fp-1": 0.71, "neg-b:fp-1": 0.20})
    examples = (
        LabeledFingerprintExample(_media("pos-a"), "fp-1", True),
        LabeledFingerprintExample(_media("pos-b"), "fp-1", True),
        LabeledFingerprintExample(_media("neg-a"), "fp-1", False),
        LabeledFingerprintExample(_media("neg-b"), "fp-1", False),
    )
    selected = choose_threshold(matcher, examples, (0.5, 0.75, 0.9), maximum_false_positive_rate=0.0)

    assert selected.threshold == 0.75
    assert selected.false_positive_rate == 0.0
    assert selected.miss_rate == 0.0
    with pytest.raises(ValueError, match="no threshold"):
        choose_threshold(matcher, examples, (0.5,), maximum_false_positive_rate=0.0)


def test_discovery_pilot_go_no_go_uses_declared_metrics() -> None:
    """Evaluate pilot go/no-go from measured metrics rather than anecdotes."""

    thresholds = DiscoveryPilotThresholds(
        minimum_precision=0.8,
        maximum_miss_rate=0.1,
        maximum_false_alerts_per_song=0.25,
        maximum_median_latency_hours=24.0,
        maximum_median_review_minutes=15.0,
        maximum_source_errors=2,
        maximum_opt_out_completion_hours=48.0,
    )
    passing = DiscoveryPilotMetrics(8, 6, 5, 1, 1, 0, 0, 12.0, 10.0, 10_000, 500, 5, 1, 0, 24.0, 2, 3)
    failing = DiscoveryPilotMetrics(4, 6, 2, 4, 0, 0, 2, 36.0, 20.0, 10_000, 500, 2, 4, 1, 72.0, 4, 0)

    accepted = evaluate_discovery_pilot(passing, thresholds)
    rejected = evaluate_discovery_pilot(failing, thresholds)
    record = record_discovery_pilot_decision(passing, thresholds, "pilot-reviewer", NOW, "pilot gates pass")

    assert accepted.go
    assert accepted.reasons == ()
    assert rejected.go is False
    assert "precision" in rejected.reasons[0]
    assert "opt-out" in rejected.reasons[-1]
    assert passing.precision == pytest.approx(5 / 6)
    assert isinstance(record, DiscoveryPilotDecisionRecord)
    assert record.decision.go
    assert record.metrics == passing
    assert record.thresholds == thresholds
    assert record.reviewer_id == "pilot-reviewer"
    with pytest.raises(ValueError, match="monitored_song_count"):
        DiscoveryPilotMetrics(-1, 0, 0, 0, 0, 0, 0, 0.0, 0.0, 0, 0, 0, 0, 0, 0.0, 0, 0)
    with pytest.raises(ValueError, match="summary"):
        record_discovery_pilot_decision(passing, thresholds, "pilot-reviewer", NOW, "")


def test_discovery_launch_readiness_records_source_engine_corpus_and_thresholds() -> None:
    """Record real-source, legal, engine, corpus, and threshold evidence."""

    source = PublicSourceSelection("public-feed", "terms-and-robots-review-1", "source-owner", NOW)
    legal = DiscoveryLegalPolicyReviewRecord(
        "source-policy-1",
        "retention-policy-1",
        "notice-policy-1",
        "opt-out-policy-1",
        "counsel-1",
        NOW,
        True,
    )
    engine = DiscoveryRecognitionEngineSelection("licensed-song-match", "v1", "engine-license-1", NOW)
    corpus = RepresentativeCorpusSummary(5, 7, 3, 4, 2, "corpus-manifest-1")
    evaluation = evaluate_matcher(
        StaticMatcher("licensed-song-match-v1", {"positive:fp-1": 0.91, "negative:fp-1": 0.2}),
        (
            LabeledFingerprintExample(DecodedMedia("audio/wav", "positive", 16_000, 1, 2, 16_000, 1.0), "fp-1", True),
            LabeledFingerprintExample(DecodedMedia("audio/wav", "negative", 16_000, 1, 2, 16_000, 1.0), "fp-1", False),
        ),
        0.8,
    )
    calibration = record_discovery_threshold_calibration(evaluation, 0.0, 0.0, "pilot-reviewer", NOW)

    assert source.access_reference == "terms-and-robots-review-1"
    assert isinstance(legal, DiscoveryLegalPolicyReviewRecord)
    assert legal.approved
    assert isinstance(engine, DiscoveryRecognitionEngineSelection)
    assert corpus.codec_variant_count == 2
    assert isinstance(calibration, DiscoveryThresholdCalibration)
    assert calibration.ready
    assert calibration.blockers == ()
    with pytest.raises(ValueError, match="maximum_miss_rate"):
        record_discovery_threshold_calibration(evaluation, 0.0, -0.1, "pilot-reviewer", NOW)
    with pytest.raises(ValueError, match="access_reference"):
        PublicSourceSelection("public-feed", "", "source-owner", NOW)
    with pytest.raises(ValueError, match="positive_count"):
        RepresentativeCorpusSummary(0, 1, 1, 1, 1, "corpus")


def test_pilot_go_no_go_blocks_notifications_until_registry_and_discovery_pass() -> None:
    """Require registry, discovery, owner, and counsel gates before notification."""

    owners = PilotOwnerAssignments("registry-owner", "desktop-owner", "discovery-owner", "security-owner", "policy-owner")
    registry_record = record_registry_launch_decision(
        RegistryMetricsSnapshot("tenant-1", 1, 10, 0, 9, 1, 0, 0.9, 0.0, 20, 1.0, 0, 10, 10 / 9),
        RegistryAccessReviewSnapshot(2, 2, 0, 1, 1, 1.0, ()),
        RegistryApiMetricsSnapshot(3, 12.0, 40.0, 1_200, 5, 0, 0.0),
        BackupRestoreRehearsalResult(Path("backup.sqlite3"), Path("restored.sqlite3"), 50.0, 70.0, 120.0),
        RegistryLaunchThresholds(0.9, 0.1, 1.0, 1.0, 0, 0, 1.25, 100.0, 0.0, 2_000, 10, 0, 500.0),
        "ops-reviewer",
        NOW,
        "registry gates pass",
    )
    discovery_thresholds = DiscoveryPilotThresholds(0.8, 0.1, 0.0, 24.0, 15.0, 0, 48.0)
    discovery_go = record_discovery_pilot_decision(
        DiscoveryPilotMetrics(8, 6, 5, 0, 1, 0, 0, 12.0, 10.0, 10_000, 500, 5, 0, 1, 24.0, 2, 3),
        discovery_thresholds,
        "pilot-reviewer",
        NOW,
        "discovery gates pass",
    )
    discovery_no_go = record_discovery_pilot_decision(
        DiscoveryPilotMetrics(8, 6, 4, 2, 0, 0, 1, 12.0, 10.0, 10_000, 500, 4, 0, 1, 24.0, 2, 2),
        discovery_thresholds,
        "pilot-reviewer",
        NOW,
        "discovery gates fail",
    )

    go = record_pilot_go_no_go(owners, registry_record, discovery_go, "pilot-owner", "counsel-1", "client-review-1", NOW, "pilot gates pass", request_client_notifications=True)
    blocked = record_pilot_go_no_go(owners, registry_record, discovery_no_go, "pilot-owner", "counsel-1", "client-review-1", NOW, "pilot gates blocked", request_client_notifications=True)

    assert isinstance(go, PilotGoNoGoDecisionRecord)
    assert go.go
    assert go.client_notifications_allowed
    assert not blocked.go
    assert not blocked.client_notifications_allowed
    assert blocked.blockers == ("discovery pilot decision is not go",)
    with pytest.raises(ValueError, match="policy_owner_id"):
        PilotOwnerAssignments("registry-owner", "desktop-owner", "discovery-owner", "security-owner", "")


def test_security_review_signoff_blocks_production_until_scope_and_findings_clear() -> None:
    """Require external review coverage and severe-finding closure for production."""

    incomplete = record_security_review_signoff(
        "external-reviewer",
        "security-report-1",
        NOW,
        (SecurityReviewArea.API_AUTHORIZATION, SecurityReviewArea.KEY_MANAGEMENT),
        0,
        1,
        3,
        "review started",
    )
    ready = record_security_review_signoff(
        "external-reviewer",
        "security-report-2",
        NOW,
        REQUIRED_SECURITY_REVIEW_AREAS,
        0,
        0,
        2,
        "required areas reviewed; medium follow-ups accepted by owner",
    )

    assert isinstance(incomplete, SecurityReviewSignoff)
    assert not incomplete.production_ready
    assert "tenant_isolation" in incomplete.blockers[0]
    assert incomplete.blockers[-1] == "1 high finding(s) remain open"
    assert ready.production_ready
    assert ready.blockers == ()
    assert ready.medium_open_count == 2
    with pytest.raises(ValueError, match="critical_open_count"):
        record_security_review_signoff(
            "external-reviewer",
            "security-report-3",
            NOW,
            REQUIRED_SECURITY_REVIEW_AREAS,
            -1,
            0,
            0,
            "invalid finding count",
        )
    with pytest.raises(TypeError, match="SecurityReviewArea"):
        record_security_review_signoff("external-reviewer", "security-report-4", NOW, ("api",), 0, 0, 0, "invalid area")
