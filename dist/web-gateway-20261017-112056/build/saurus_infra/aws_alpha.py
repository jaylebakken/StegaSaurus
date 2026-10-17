"""Review the slim AWS alpha CloudFormation draft before deployment.

Saurus keeps the first hosted registry small: one container task, PostgreSQL,
managed secrets, KMS, encrypted backup storage, short logs, and budget alerts.
This module performs a conservative local preflight over the
checked-in template text:

It splits top-level resources, checks tags, budget, encryption, short logs, and
returns blockers instead of deploying anything.

It is not a replacement for CloudFormation validation, IAM Access Analyzer,
CloudTrail/KMS evidence, or a real deployed smoke test.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

__all__ = ["AwsAlphaTemplateReview", "review_aws_alpha_template"]

_RESOURCE_START = re.compile(r"^  ([A-Za-z0-9]+):\s*$")
_TYPE_LINE = re.compile(r"^\s+Type:\s+(.+?)\s*$", re.MULTILINE)
_RETENTION_LINE = re.compile(r"RetentionInDays:\s+(\d+)")
_BUDGET_THRESHOLD_LINE = re.compile(r"Threshold:\s+(\d+)")

_REQUIRED_ALIASES = (
    "alias/saurus/alpha/registry-records",
    "alias/saurus/alpha/encode-grants",
    "alias/saurus/alpha/reports",
    "alias/saurus/alpha/backups",
)
_TAGGABLE_TYPES = {
    "AWS::CloudWatch::Alarm",
    "AWS::ECR::Repository",
    "AWS::ECS::TaskDefinition",
    "AWS::ECS::Cluster",
    "AWS::ECS::Service",
    "AWS::EC2::SecurityGroup",
    "AWS::ElasticLoadBalancingV2::LoadBalancer",
    "AWS::ElasticLoadBalancingV2::TargetGroup",
    "AWS::IAM::Role",
    "AWS::KMS::Key",
    "AWS::Logs::LogGroup",
    "AWS::RDS::DBInstance",
    "AWS::RDS::DBSubnetGroup",
    "AWS::S3::Bucket",
    "AWS::SecretsManager::Secret",
    "AWS::SNS::Topic",
}
_FORBIDDEN_RESOURCE_MARKERS = ("AWS::EC2::NatGateway", "Crawler", "DiscoveryWorker", "MediaStore")


@dataclass(frozen=True, slots=True)
class AwsAlphaTemplateReview:
    """Summarize local guardrail checks for the AWS alpha template."""

    resource_count: int
    missing_tagged_resources: tuple[str, ...]
    required_aliases_present: bool
    has_budget_alert: bool
    budget_threshold_percent: int | None
    log_retention_days: int | None
    database_private: bool
    database_encrypted: bool
    backup_bucket_encrypted: bool
    has_https_listener: bool
    has_ecs_service: bool
    has_database_subnet_group: bool
    has_ecs_api_secret_injection: bool
    forbidden_resource_markers: tuple[str, ...]
    go: bool
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate numeric fields and blocker consistency."""

        if self.resource_count <= 0:
            raise ValueError("resource_count must be positive")
        if self.budget_threshold_percent is not None and self.budget_threshold_percent <= 0:
            raise ValueError("budget_threshold_percent must be positive when present")
        if self.log_retention_days is not None and self.log_retention_days <= 0:
            raise ValueError("log_retention_days must be positive when present")
        if self.go and self.blockers:
            raise ValueError("go cannot be true while blockers exist")


def review_aws_alpha_template(path: Path) -> AwsAlphaTemplateReview:
    """Review one checked-in AWS alpha CloudFormation template."""

    template_text = path.read_text(encoding="utf-8")
    resources = _resource_blocks(template_text)
    missing_tags = _missing_tagged_resources(resources)
    budget_threshold = _budget_threshold(template_text)
    log_retention_days = _log_retention(template_text)
    forbidden = tuple(marker for marker in _FORBIDDEN_RESOURCE_MARKERS if marker in template_text)
    required_aliases_present = all(alias in template_text for alias in _REQUIRED_ALIASES)
    has_budget_alert = "AWS::Budgets::Budget" in template_text and budget_threshold is not None
    database_private = "PubliclyAccessible: false" in template_text
    database_encrypted = "StorageEncrypted: true" in template_text
    backup_bucket_encrypted = "SSEAlgorithm: aws:kms" in template_text
    has_https_listener = "AWS::ElasticLoadBalancingV2::Listener" in template_text and "Protocol: HTTPS" in template_text
    has_ecs_service = "AWS::ECS::Service" in template_text and "AwsvpcConfiguration:" in template_text
    has_database_subnet_group = "AWS::RDS::DBSubnetGroup" in template_text and "DBSubnetGroupName:" in template_text
    has_ecs_api_secret_injection = all(
        marker in template_text
        for marker in ("Secrets:", "Name: SAURUS_API_SIGNING_SECRET", "ValueFrom: !Ref RegistryApiSigningSecret", "saurus-alpha-registry-secret-injection")
    )
    blockers = _blockers(
        missing_tags,
        required_aliases_present,
        has_budget_alert,
        budget_threshold,
        log_retention_days,
        database_private,
        database_encrypted,
        backup_bucket_encrypted,
        has_https_listener,
        has_ecs_service,
        has_database_subnet_group,
        has_ecs_api_secret_injection,
        forbidden,
    )
    return AwsAlphaTemplateReview(
        len(resources),
        missing_tags,
        required_aliases_present,
        has_budget_alert,
        budget_threshold,
        log_retention_days,
        database_private,
        database_encrypted,
        backup_bucket_encrypted,
        has_https_listener,
        has_ecs_service,
        has_database_subnet_group,
        has_ecs_api_secret_injection,
        forbidden,
        not blockers,
        blockers,
    )


def _resource_blocks(template_text: str) -> dict[str, str]:
    """Return top-level CloudFormation resource blocks keyed by logical ID."""

    resources: dict[str, list[str]] = {}
    current_name: str | None = None
    inside_resources = False
    for line in template_text.splitlines():
        if line == "Resources:":
            inside_resources = True
            continue
        if line == "Outputs:":
            break
        if not inside_resources:
            continue
        match = _RESOURCE_START.match(line)
        if match:
            current_name = match.group(1)
            resources[current_name] = [line]
            continue
        if current_name is not None:
            resources[current_name].append(line)
    return {name: "\n".join(lines) for name, lines in resources.items()}


def _resource_type(block: str) -> str | None:
    """Extract one resource type from a resource block."""

    match = _TYPE_LINE.search(block)
    return match.group(1) if match else None


def _missing_tagged_resources(resources: dict[str, str]) -> tuple[str, ...]:
    """Find taggable resources missing the alpha tag triplet."""

    missing: list[str] = []
    for name, block in resources.items():
        resource_type = _resource_type(block)
        if resource_type not in _TAGGABLE_TYPES:
            continue
        if not all(marker in block for marker in ("Key: project", "Value: saurus", "Key: env", "Value: alpha", "Key: owner")):
            missing.append(name)
    return tuple(missing)


def _budget_threshold(template_text: str) -> int | None:
    """Read the first budget alert threshold from the template."""

    for match in _BUDGET_THRESHOLD_LINE.finditer(template_text):
        if "ThresholdType: PERCENTAGE" in template_text[match.end() : match.end() + 120]:
            return int(match.group(1))
    return None


def _log_retention(template_text: str) -> int | None:
    """Read the registry log retention period from the template."""

    match = _RETENTION_LINE.search(template_text)
    return int(match.group(1)) if match else None


def _blockers(
    missing_tags: tuple[str, ...],
    required_aliases_present: bool,
    has_budget_alert: bool,
    budget_threshold: int | None,
    log_retention_days: int | None,
    database_private: bool,
    database_encrypted: bool,
    backup_bucket_encrypted: bool,
    has_https_listener: bool,
    has_ecs_service: bool,
    has_database_subnet_group: bool,
    has_ecs_api_secret_injection: bool,
    forbidden: tuple[str, ...],
) -> tuple[str, ...]:
    """List alpha template blockers from local guardrail evidence."""

    blockers: list[str] = []
    if missing_tags:
        blockers.append("missing required tags: " + ", ".join(missing_tags))
    if not required_aliases_present:
        blockers.append("required KMS aliases are missing")
    if not has_budget_alert:
        blockers.append("monthly budget alert is missing")
    elif budget_threshold is None or budget_threshold > 80:
        blockers.append("budget alert threshold must be 80 percent or lower")
    if log_retention_days is None or log_retention_days > 14:
        blockers.append("registry log retention must be 14 days or less")
    if not database_private:
        blockers.append("registry database must not be public")
    if not database_encrypted:
        blockers.append("registry database encryption is missing")
    if not backup_bucket_encrypted:
        blockers.append("backup bucket KMS encryption is missing")
    if not has_https_listener:
        blockers.append("HTTPS load-balancer listener is missing")
    if not has_ecs_service:
        blockers.append("ECS service networking is missing")
    if not has_database_subnet_group:
        blockers.append("database subnet group wiring is missing")
    if not has_ecs_api_secret_injection:
        blockers.append("ECS API signing secret injection is missing")
    if forbidden:
        blockers.append("forbidden alpha resource marker present: " + ", ".join(forbidden))
    return tuple(blockers)
