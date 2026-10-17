"""Evaluate song-fingerprint engines before choosing discovery thresholds.

The discovery service must calibrate song recognition on held-out positives and
negatives. This module defines a matcher protocol, labeled examples, measured
evaluation output, and a conservative threshold selector. It does not implement
or bless a production fingerprint engine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol

from .media import DecodedMedia


class FingerprintMatcher(Protocol):
    """Score whether bounded media matches a monitored song fingerprint."""

    @property
    def engine_version(self) -> str:
        """Return the matcher implementation/version label."""

    def score(self, media: DecodedMedia, public_fingerprint_id: str) -> float:
        """Return a normalized song-match score between zero and one."""


@dataclass(frozen=True, slots=True)
class LabeledFingerprintExample:
    """Declare one held-out fingerprint evaluation example."""

    media: DecodedMedia
    public_fingerprint_id: str
    expected_match: bool

    def __post_init__(self) -> None:
        """Validate the target fingerprint identity."""

        if not self.public_fingerprint_id.strip():
            raise ValueError("public_fingerprint_id must not be empty")


@dataclass(frozen=True, slots=True)
class FingerprintEvaluation:
    """Summarize measured matcher behavior at one threshold."""

    engine_version: str
    threshold: float
    example_count: int
    true_positive_count: int
    false_positive_count: int
    true_negative_count: int
    false_negative_count: int

    @property
    def precision(self) -> float:
        """Return accepted-candidate precision, or one when no candidates pass."""

        accepted = self.true_positive_count + self.false_positive_count
        return 1.0 if accepted == 0 else self.true_positive_count / accepted

    @property
    def miss_rate(self) -> float:
        """Return positive examples missed by the threshold."""

        positives = self.true_positive_count + self.false_negative_count
        return 0.0 if positives == 0 else self.false_negative_count / positives

    @property
    def false_positive_rate(self) -> float:
        """Return negative examples incorrectly accepted by the threshold."""

        negatives = self.true_negative_count + self.false_positive_count
        return 0.0 if negatives == 0 else self.false_positive_count / negatives


def evaluate_matcher(
    matcher: FingerprintMatcher,
    examples: tuple[LabeledFingerprintExample, ...],
    threshold: float,
) -> FingerprintEvaluation:
    """Evaluate a matcher against labeled positives and negatives."""

    if not examples:
        raise ValueError("examples must not be empty")
    if not 0.0 <= threshold <= 1.0:
        raise ValueError("threshold must be between zero and one")
    true_positive = false_positive = true_negative = false_negative = 0
    for example in examples:
        accepted = matcher.score(example.media, example.public_fingerprint_id) >= threshold
        if accepted and example.expected_match:
            true_positive += 1
        elif accepted:
            false_positive += 1
        elif example.expected_match:
            false_negative += 1
        else:
            true_negative += 1
    return FingerprintEvaluation(
        matcher.engine_version,
        threshold,
        len(examples),
        true_positive,
        false_positive,
        true_negative,
        false_negative,
    )


def choose_threshold(
    matcher: FingerprintMatcher,
    examples: tuple[LabeledFingerprintExample, ...],
    candidate_thresholds: tuple[float, ...],
    *,
    maximum_false_positive_rate: float,
) -> FingerprintEvaluation:
    """Pick the lowest-miss measured threshold satisfying a false-positive bound."""

    if not candidate_thresholds:
        raise ValueError("candidate_thresholds must not be empty")
    evaluations = tuple(evaluate_matcher(matcher, examples, threshold) for threshold in candidate_thresholds)
    eligible = [item for item in evaluations if item.false_positive_rate <= maximum_false_positive_rate]
    if not eligible:
        raise ValueError("no threshold satisfies the false-positive bound")
    return min(eligible, key=lambda item: (item.miss_rate, -item.threshold))
