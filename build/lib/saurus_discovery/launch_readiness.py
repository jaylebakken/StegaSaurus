"""Record discovery launch-readiness choices before live crawling.

Discovery should move from local rehearsals to real public sources only after
the source path, legal/policy review, recognition engine, representative corpus,
and measured thresholds are written down. This module records that evidence in
small immutable records. It does not crawl, fetch media, license an engine, or
approve client notifications.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from .fingerprint import FingerprintEvaluation

__all__ = [
    "DiscoveryLegalPolicyReviewRecord",
    "DiscoveryRecognitionEngineSelection",
    "DiscoveryThresholdCalibration",
    "PublicSourceSelection",
    "RepresentativeCorpusSummary",
    "record_discovery_threshold_calibration",
]


@dataclass(frozen=True, slots=True)
class PublicSourceSelection:
    """Record one real public source and its permitted access path."""

    source_id: str
    access_reference: str
    owner_id: str
    selected_utc: datetime

    def __post_init__(self) -> None:
        """Validate public source selection evidence."""

        for value, name in (
            (self.source_id, "source_id"),
            (self.access_reference, "access_reference"),
            (self.owner_id, "owner_id"),
        ):
            _require_text(value, name)
        _require_aware(self.selected_utc, "selected_utc")


@dataclass(frozen=True, slots=True)
class DiscoveryLegalPolicyReviewRecord:
    """Record source, retention, notice, and opt-out legal review."""

    source_policy_reference: str
    retention_reference: str
    notice_reference: str
    opt_out_reference: str
    counsel_reviewer_id: str
    reviewed_utc: datetime
    approved: bool

    def __post_init__(self) -> None:
        """Validate discovery legal/policy review evidence."""

        for value, name in (
            (self.source_policy_reference, "source_policy_reference"),
            (self.retention_reference, "retention_reference"),
            (self.notice_reference, "notice_reference"),
            (self.opt_out_reference, "opt_out_reference"),
            (self.counsel_reviewer_id, "counsel_reviewer_id"),
        ):
            _require_text(value, name)
        _require_aware(self.reviewed_utc, "reviewed_utc")


@dataclass(frozen=True, slots=True)
class DiscoveryRecognitionEngineSelection:
    """Record the selected or licensed song-recognition engine."""

    engine_name: str
    engine_version: str
    license_reference: str
    selected_utc: datetime

    def __post_init__(self) -> None:
        """Validate recognition engine selection evidence."""

        for value, name in (
            (self.engine_name, "engine_name"),
            (self.engine_version, "engine_version"),
            (self.license_reference, "license_reference"),
        ):
            _require_text(value, name)
        _require_aware(self.selected_utc, "selected_utc")


@dataclass(frozen=True, slots=True)
class RepresentativeCorpusSummary:
    """Record measured corpus coverage for discovery threshold selection."""

    positive_count: int
    negative_count: int
    edited_count: int
    excerpted_count: int
    codec_variant_count: int
    corpus_reference: str

    def __post_init__(self) -> None:
        """Validate representative corpus counters."""

        for value, name in (
            (self.positive_count, "positive_count"),
            (self.negative_count, "negative_count"),
            (self.edited_count, "edited_count"),
            (self.excerpted_count, "excerpted_count"),
            (self.codec_variant_count, "codec_variant_count"),
        ):
            if value <= 0:
                raise ValueError(f"{name} must be positive")
        _require_text(self.corpus_reference, "corpus_reference")


@dataclass(frozen=True, slots=True)
class DiscoveryThresholdCalibration:
    """Record threshold evidence from measured false-positive and miss rates."""

    evaluation: FingerprintEvaluation
    maximum_false_positive_rate: float
    maximum_miss_rate: float
    reviewer_id: str
    calibrated_utc: datetime
    ready: bool
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate threshold calibration provenance and blockers."""

        if not 0.0 <= self.maximum_false_positive_rate <= 1.0:
            raise ValueError("maximum_false_positive_rate must be a ratio")
        if not 0.0 <= self.maximum_miss_rate <= 1.0:
            raise ValueError("maximum_miss_rate must be a ratio")
        _require_text(self.reviewer_id, "reviewer_id")
        _require_aware(self.calibrated_utc, "calibrated_utc")
        if self.ready and self.blockers:
            raise ValueError("ready cannot be true while blockers exist")


def record_discovery_threshold_calibration(
    evaluation: FingerprintEvaluation,
    maximum_false_positive_rate: float,
    maximum_miss_rate: float,
    reviewer_id: str,
    calibrated_utc: datetime,
) -> DiscoveryThresholdCalibration:
    """Record threshold calibration from measured matcher rates."""

    blockers: list[str] = []
    if evaluation.false_positive_rate > maximum_false_positive_rate:
        blockers.append("false-positive rate is above threshold")
    if evaluation.miss_rate > maximum_miss_rate:
        blockers.append("miss rate is above threshold")
    return DiscoveryThresholdCalibration(
        evaluation,
        maximum_false_positive_rate,
        maximum_miss_rate,
        reviewer_id,
        calibrated_utc,
        not blockers,
        tuple(blockers),
    )


def _require_text(value: str, name: str) -> None:
    """Require one visible text value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _require_aware(value: datetime, name: str) -> None:
    """Require one timezone-aware timestamp."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
