"""Record live KMS-backed encode-grant readiness evidence.

The registry has an AWS-KMS-shaped encode grant provider, but production launch
needs evidence from the deployed path: the service role must issue a scoped data
key, the grant must use the managed algorithm, audit metadata must be recorded
without plaintext key material, and CloudTrail/KMS evidence must exist for the
request. This module records that launch gate:

1. Capture the KMS key alias, grant algorithm, context digest, IAM evidence,
   CloudTrail evidence, and grant-audit evidence.
2. Require an accepted encode/decode smoke reference for the grant path.
3. Block production readiness if the evidence is incomplete or not from the
   managed AWS KMS grant algorithm.

The record does not call AWS or unwrap grants. It keeps live KMS validation
separate from local fake-client tests.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from saurus_registry import AWS_KMS_DATA_KEY_GRANT

__all__ = ["KmsGrantLiveTestRecord", "record_kms_grant_live_test"]


@dataclass(frozen=True, slots=True)
class KmsGrantLiveTestRecord:
    """Summarize deployed KMS encode-grant readiness evidence."""

    environment: str
    kms_key_alias: str
    grant_algorithm: str
    context_digest: str
    iam_policy_reference: str
    cloudtrail_reference: str
    grant_audit_reference: str
    smoke_test_reference: str
    reviewer_id: str
    tested_utc: datetime
    production_ready: bool
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate live KMS evidence provenance and readiness consistency."""

        for value, name in (
            (self.environment, "environment"),
            (self.kms_key_alias, "kms_key_alias"),
            (self.grant_algorithm, "grant_algorithm"),
            (self.context_digest, "context_digest"),
            (self.iam_policy_reference, "iam_policy_reference"),
            (self.cloudtrail_reference, "cloudtrail_reference"),
            (self.grant_audit_reference, "grant_audit_reference"),
            (self.smoke_test_reference, "smoke_test_reference"),
            (self.reviewer_id, "reviewer_id"),
        ):
            _require_text(value, name)
        _require_aware(self.tested_utc, "tested_utc")
        if self.production_ready and self.blockers:
            raise ValueError("production_ready cannot be true while blockers exist")


def record_kms_grant_live_test(
    environment: str,
    kms_key_alias: str,
    grant_algorithm: str,
    context_digest: str,
    iam_policy_reference: str,
    cloudtrail_reference: str,
    grant_audit_reference: str,
    smoke_test_reference: str,
    reviewer_id: str,
    tested_utc: datetime,
) -> KmsGrantLiveTestRecord:
    """Create a live KMS grant test record and compute production blockers."""

    blockers = _blockers(kms_key_alias, grant_algorithm, context_digest)
    return KmsGrantLiveTestRecord(
        environment,
        kms_key_alias,
        grant_algorithm,
        context_digest,
        iam_policy_reference,
        cloudtrail_reference,
        grant_audit_reference,
        smoke_test_reference,
        reviewer_id,
        tested_utc,
        not blockers,
        blockers,
    )


def _blockers(kms_key_alias: str, grant_algorithm: str, context_digest: str) -> tuple[str, ...]:
    """List KMS grant evidence blockers."""

    blockers: list[str] = []
    if not kms_key_alias.startswith("alias/saurus/") or not kms_key_alias.endswith("/encode-grants"):
        blockers.append("KMS key alias must use the Saurus encode-grants alias path")
    if grant_algorithm != AWS_KMS_DATA_KEY_GRANT:
        blockers.append("grant algorithm must be AWS KMS data-key grant")
    if len(context_digest.strip()) != 64:
        blockers.append("context digest must be a SHA-256 hex digest")
    return tuple(blockers)


def _require_text(value: str, name: str) -> None:
    """Require one visible text value."""

    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{name} must not be empty")


def _require_aware(value: datetime, name: str) -> None:
    """Require one timezone-aware timestamp."""

    if value.tzinfo is None or value.utcoffset() is None:
        raise ValueError(f"{name} must be timezone-aware")
