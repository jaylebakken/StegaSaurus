"""Review AWS alpha container image repository guardrails.

The alpha stack needs a place to push the registry container before an ECS
service can smoke-test it. This local review checks that the CloudFormation
draft declares an ECR repository with immutable tags, scan-on-push, encryption,
and a lifecycle policy. It does not build, push, scan, or attest an image.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__ = ["AwsAlphaImageReview", "review_aws_alpha_image"]


@dataclass(frozen=True, slots=True)
class AwsAlphaImageReview:
    """Summarize ECR image repository guardrails for alpha."""

    has_repository: bool
    immutable_tags: bool
    scan_on_push: bool
    encrypted: bool
    has_lifecycle_policy: bool
    has_repository_output: bool
    has_alpha_image_pattern: bool
    go: bool
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate blocker consistency."""

        if self.go and self.blockers:
            raise ValueError("go cannot be true while blockers exist")


def review_aws_alpha_image(path: Path) -> AwsAlphaImageReview:
    """Review ECR image repository settings in one alpha template."""

    template_text = path.read_text(encoding="utf-8")
    has_repository = "AWS::ECR::Repository" in template_text and "RegistryImageRepository" in template_text
    immutable_tags = "ImageTagMutability: IMMUTABLE" in template_text
    scan_on_push = "ScanOnPush: true" in template_text
    encrypted = "EncryptionType: KMS" in template_text and "KmsKey: !GetAtt BackupsKey.Arn" in template_text
    has_lifecycle_policy = "LifecyclePolicyText:" in template_text and "countNumber\": 10" in template_text
    has_repository_output = "RegistryImageRepositoryUri:" in template_text and "RepositoryUri" in template_text
    has_alpha_image_pattern = "saurus-alpha-registry:alpha-" in template_text and "AllowedPattern:" in template_text
    blockers = _blockers(has_repository, immutable_tags, scan_on_push, encrypted, has_lifecycle_policy, has_repository_output, has_alpha_image_pattern)
    return AwsAlphaImageReview(has_repository, immutable_tags, scan_on_push, encrypted, has_lifecycle_policy, has_repository_output, has_alpha_image_pattern, not blockers, blockers)


def _blockers(
    has_repository: bool,
    immutable_tags: bool,
    scan_on_push: bool,
    encrypted: bool,
    has_lifecycle_policy: bool,
    has_repository_output: bool,
    has_alpha_image_pattern: bool,
) -> tuple[str, ...]:
    """Return image repository blockers."""

    blockers: list[str] = []
    if not has_repository:
        blockers.append("ECR repository is missing")
    if not immutable_tags:
        blockers.append("ECR repository must use immutable tags")
    if not scan_on_push:
        blockers.append("ECR repository must scan images on push")
    if not encrypted:
        blockers.append("ECR repository KMS encryption is missing")
    if not has_lifecycle_policy:
        blockers.append("ECR repository lifecycle policy is missing")
    if not has_repository_output:
        blockers.append("ECR repository URI output is missing")
    if not has_alpha_image_pattern:
        blockers.append("container image parameter must require an alpha ECR tag")
    return tuple(blockers)
