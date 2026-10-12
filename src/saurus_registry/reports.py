"""Build signed verification reports with constrained evidence language.

Signed reports are not legal notices and do not accuse a recipient. They bind a
small evidence-language-safe payload to a signing key so an operator can later
prove the report text and registry identifiers were not altered. The module
does not receive audio, private block records, or crawler media.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
import hmac
import json
from typing import Literal


ReportOutcome = Literal["accepted", "rejected", "abstained"]


@dataclass(frozen=True, slots=True)
class VerificationReportPayload:
    """Represent the canonical facts allowed in one verification report."""

    tenant_id: str
    export_id: str
    verification_event_id: str
    profile_version: str
    outcome: ReportOutcome
    evidence_class: str
    system_statement: str
    result_statement: str
    user_label_statement: str
    issued_utc: datetime

    def __post_init__(self) -> None:
        """Validate report identity, allowed outcome, and safe wording."""

        for value, name in (
            (self.tenant_id, "tenant_id"),
            (self.export_id, "export_id"),
            (self.verification_event_id, "verification_event_id"),
            (self.profile_version, "profile_version"),
            (self.evidence_class, "evidence_class"),
            (self.system_statement, "system_statement"),
            (self.result_statement, "result_statement"),
        ):
            _require_text(value, name)
        if self.outcome not in ("accepted", "rejected", "abstained"):
            raise ValueError("outcome is not supported")
        if self.evidence_class != "watermark match":
            raise ValueError("verification reports must use the watermark match evidence class")
        _reject_unsafe_words(self.result_statement)
        if self.issued_utc.tzinfo is None or self.issued_utc.utcoffset() is None:
            raise ValueError("issued_utc must be timezone-aware")


@dataclass(frozen=True, slots=True)
class SignedVerificationReport:
    """Bind one verification report payload to a canonical signature."""

    payload: VerificationReportPayload
    key_id: str
    signature: str
    algorithm: str = "hmac-sha256-report-v1"

    def __post_init__(self) -> None:
        """Validate signature metadata."""

        _require_text(self.key_id, "key_id")
        _require_text(self.signature, "signature")
        if self.algorithm != "hmac-sha256-report-v1":
            raise ValueError("report signature algorithm is not supported")


def build_watermark_report_payload(
    *,
    tenant_id: str,
    export_id: str,
    verification_event_id: str,
    profile_version: str,
    outcome: ReportOutcome,
    recipient_label: str,
    issued_utc: datetime,
) -> VerificationReportPayload:
    """Build a report payload using the approved watermark-match wording."""

    result = f"Audio evidence matched registered export event {export_id} under profile {profile_version}."
    if outcome == "rejected":
        result = f"The selected export claim {export_id} did not match the available evidence under profile {profile_version}."
    elif outcome == "abstained":
        result = f"Saurus could not reach an accepted result for export event {export_id} under profile {profile_version}."
    return VerificationReportPayload(
        tenant_id,
        export_id,
        verification_event_id,
        profile_version,
        outcome,
        "watermark match",
        f"Verification event {verification_event_id} was recorded by Saurus.",
        result,
        f"Export event {export_id} has the user label {recipient_label.strip()}.",
        issued_utc,
    )


def sign_verification_report(payload: VerificationReportPayload, key_id: str, secret: bytes) -> SignedVerificationReport:
    """Return a signed report for one canonical payload."""

    _require_text(key_id, "key_id")
    if not secret:
        raise ValueError("secret must not be empty")
    signature = hmac.new(secret, canonical_report_bytes(payload), hashlib.sha256).hexdigest()
    return SignedVerificationReport(payload, key_id, signature)


def verify_signed_report(report: SignedVerificationReport, secret: bytes) -> bool:
    """Return whether one report signature matches its canonical payload."""

    if not secret:
        raise ValueError("secret must not be empty")
    expected = hmac.new(secret, canonical_report_bytes(report.payload), hashlib.sha256).hexdigest()
    return hmac.compare_digest(report.signature, expected)


def canonical_report_bytes(payload: VerificationReportPayload) -> bytes:
    """Serialize one report payload into canonical signed bytes."""

    document = {
        "tenant_id": payload.tenant_id,
        "export_id": payload.export_id,
        "verification_event_id": payload.verification_event_id,
        "profile_version": payload.profile_version,
        "outcome": payload.outcome,
        "evidence_class": payload.evidence_class,
        "system_statement": payload.system_statement,
        "result_statement": payload.result_statement,
        "user_label_statement": payload.user_label_statement,
        "issued_utc": payload.issued_utc.isoformat(),
    }
    return json.dumps(document, sort_keys=True, separators=(",", ":")).encode("utf-8")


def _require_text(value: str, name: str) -> None:
    """Require one visible text value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _reject_unsafe_words(statement: str) -> None:
    """Reject report result text that turns evidence into recipient blame."""

    lowered = statement.lower()
    for word in ("leaked", "leak", "fault", "accuse", "guilty"):
        if word in lowered:
            raise ValueError("report wording must not accuse a recipient")
