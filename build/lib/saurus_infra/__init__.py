"""Expose infrastructure readiness helpers for Saurus deployment planning.

The infrastructure package sits outside audio encoding, registry business
logic, and discovery matching. It records local checks for deployment artifacts
such as the slim AWS alpha CloudFormation draft. These helpers do not contact
AWS and do not prove a deployed environment is safe; they keep pre-deployment
expectations reviewable in tests.
"""

from __future__ import annotations

from .aws_alpha import AwsAlphaTemplateReview, review_aws_alpha_template
from .aws_alpha_image import AwsAlphaImageReview, review_aws_alpha_image
from .aws_alpha_monitoring import AwsAlphaMonitoringReview, review_aws_alpha_monitoring
from .aws_alpha_secrets import AwsAlphaSecretsReview, review_aws_alpha_secrets
from .endpoint_smoke import AlphaEndpointSmokeResult, smoke_alpha_endpoint

__all__ = [
    "AlphaEndpointSmokeResult",
    "AwsAlphaImageReview",
    "AwsAlphaMonitoringReview",
    "AwsAlphaSecretsReview",
    "AwsAlphaTemplateReview",
    "review_aws_alpha_image",
    "review_aws_alpha_monitoring",
    "review_aws_alpha_secrets",
    "review_aws_alpha_template",
    "smoke_alpha_endpoint",
]
