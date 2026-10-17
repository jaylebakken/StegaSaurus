"""Review user-facing copy for evidence-language risk.

Deployment readiness needs a repeatable way to catch copy that turns technical
evidence into blame, certainty, or unsupported robustness claims. This module is
not a legal review and it does not approve marketing language. It provides a
small scanner for app strings, README text, report wording, and sales drafts so
human reviewers start from a concrete list of risky phrases.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
import re


@dataclass(frozen=True, slots=True)
class EvidenceCopyFinding:
    """Describe one risky phrase in a reviewed text artifact."""

    label: str
    line_number: int
    phrase: str
    reason: str

    def __post_init__(self) -> None:
        """Validate finding metadata."""

        _require_text(self.label, "label")
        _require_text(self.phrase, "phrase")
        _require_text(self.reason, "reason")
        if self.line_number < 1:
            raise ValueError("line_number must be positive")


@dataclass(frozen=True, slots=True)
class EvidenceCopyReview:
    """Summarize copy-review findings across text artifacts."""

    findings: tuple[EvidenceCopyFinding, ...]

    @property
    def passed(self) -> bool:
        """Return whether no risky copy was found."""

        return not self.findings


_RISKY_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"\b(definitely|certainly|guarantee[sd]?|prove[sn]? that)\b", re.IGNORECASE), "avoid certainty beyond measured evidence"),
    (re.compile(r"\b(guilty|at fault|stole|pirated|recipient leaked|recipient caused)\b", re.IGNORECASE), "avoid recipient blame or legal conclusions"),
    (re.compile(r"\b(no registered copy is present|definitely unwatermarked)\b", re.IGNORECASE), "use abstention language instead of absence claims"),
    (re.compile(r"\b(arbitrary edits?|universal robustness|imperceptible|inaudible)\b", re.IGNORECASE), "name measured evaluations instead of broad robustness claims"),
)


def review_evidence_copy(artifacts: Mapping[str, str]) -> EvidenceCopyReview:
    """Scan named text artifacts for evidence-language risks."""

    findings: list[EvidenceCopyFinding] = []
    for label, text in artifacts.items():
        _require_text(label, "label")
        if not isinstance(text, str):
            raise TypeError("artifact text must be a string")
        for line_number, line in enumerate(text.splitlines(), start=1):
            findings.extend(_find_line_risks(label, line_number, line))
    return EvidenceCopyReview(tuple(findings))


def _find_line_risks(label: str, line_number: int, line: str) -> tuple[EvidenceCopyFinding, ...]:
    """Return all risky phrases found in one line."""

    if _is_scope_boundary(line):
        return ()
    found: list[EvidenceCopyFinding] = []
    for pattern, reason in _RISKY_PATTERNS:
        for match in pattern.finditer(line):
            found.append(EvidenceCopyFinding(label, line_number, match.group(0), reason))
    return tuple(found)


def _is_scope_boundary(line: str) -> bool:
    """Return whether a line is explicitly limiting claims rather than making them."""

    lowered = line.lower()
    return any(
        phrase in lowered
        for phrase in (
            "does not claim",
            "not a general",
            "not a broad",
            "not robustness",
            "or robustness guarantee",
            "production claims about",
            "without claiming",
            "require broader validation",
            "requires broader validation",
        )
    )


def _require_text(value: str, name: str) -> None:
    """Require one visible text value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")
