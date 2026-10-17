"""Check desktop-visible text for accidental private registry material.

Deployment readiness needs repeatable privacy checks around receipts, smoke
output, status text, and local operation logs. This module is deliberately
small: callers provide the exact secrets or private snippets that must not
appear, and the scanner reports labels that contain them. It does not inspect
audio files or prove hosted log configuration.
"""

from __future__ import annotations

from dataclasses import dataclass

__all__ = ["PrivacyScanFinding", "PrivacyScanResult", "scan_text_artifacts"]


@dataclass(frozen=True, slots=True)
class PrivacyScanFinding:
    """Identify one text artifact that contains a forbidden snippet."""

    label: str
    forbidden_name: str


@dataclass(frozen=True, slots=True)
class PrivacyScanResult:
    """Summarize whether scanned text artifacts avoided forbidden snippets."""

    findings: tuple[PrivacyScanFinding, ...]

    @property
    def passed(self) -> bool:
        """Return whether no forbidden snippets were found."""

        return not self.findings


def scan_text_artifacts(
    artifacts: dict[str, str],
    forbidden: dict[str, str],
) -> PrivacyScanResult:
    """Scan text artifacts for caller-supplied forbidden private snippets."""

    findings: list[PrivacyScanFinding] = []
    for label, text in artifacts.items():
        if not isinstance(label, str) or not label.strip():
            raise ValueError("artifact labels must not be empty")
        if not isinstance(text, str):
            raise TypeError("artifact text must be strings")
        for name, snippet in forbidden.items():
            if not isinstance(name, str) or not name.strip():
                raise ValueError("forbidden names must not be empty")
            if not isinstance(snippet, str):
                raise TypeError("forbidden snippets must be strings")
            if snippet and snippet in text:
                findings.append(PrivacyScanFinding(label, name))
    return PrivacyScanResult(tuple(findings))
