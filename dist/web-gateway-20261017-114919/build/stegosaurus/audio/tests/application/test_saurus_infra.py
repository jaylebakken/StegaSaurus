"""Test deployment-artifact reviews without contacting cloud providers.

These tests keep Saurus infrastructure checks local and conservative. They do
not validate a live AWS account, prove IAM least privilege, or replace
CloudFormation deployment validation. They make the checked-in alpha template
carry the tags, encryption, budget, and no-crawler guardrails documented for the
first hosted registry rehearsal.
"""

from __future__ import annotations

from pathlib import Path

from saurus_infra import (
    AlphaEndpointSmokeResult,
    AwsAlphaImageReview,
    AwsAlphaMonitoringReview,
    AwsAlphaSecretsReview,
    AwsAlphaTemplateReview,
    review_aws_alpha_image,
    review_aws_alpha_monitoring,
    review_aws_alpha_secrets,
    review_aws_alpha_template,
    smoke_alpha_endpoint,
)


ROOT = Path(__file__).resolve().parents[5]
TEMPLATE = ROOT / "infra" / "aws-alpha" / "template.yaml"
DOCKERFILE = ROOT / "infra" / "aws-alpha" / "Dockerfile"


def test_aws_alpha_template_passes_local_guardrail_review() -> None:
    """Review the checked-in alpha template for local deployment guardrails."""

    review = review_aws_alpha_template(TEMPLATE)

    assert isinstance(review, AwsAlphaTemplateReview)
    assert review.go
    assert review.blockers == ()
    assert review.resource_count >= 10
    assert review.missing_tagged_resources == ()
    assert review.required_aliases_present
    assert review.has_budget_alert
    assert review.budget_threshold_percent == 80
    assert review.log_retention_days == 14
    assert review.database_private
    assert review.database_encrypted
    assert review.backup_bucket_encrypted
    assert review.has_https_listener
    assert review.has_ecs_service
    assert review.has_database_subnet_group
    assert review.has_ecs_api_secret_injection
    assert review.forbidden_resource_markers == ()
    template_text = TEMPLATE.read_text(encoding="utf-8")
    assert "DeployRegistryService:" in template_text
    assert "ShouldDeployRegistryService:" in template_text
    assert "Condition: ShouldDeployRegistryService" in template_text
    assert "Default: \"\"" in template_text
    assert "AllowedIngressCidr:" in template_text
    assert "CidrIp: !Ref AllowedIngressCidr" in template_text
    assert 'HttpCode: "200"' in template_text
    assert "200-499" not in template_text
    assert "AWS::Cognito::UserPool" in template_text
    assert "AWS::Cognito::UserPoolClient" in template_text
    assert "AWS::Cognito::UserPoolDomain" in template_text
    assert "AWS::Cognito::ManagedLoginBranding" in template_text
    assert "GenerateSecret: false" in template_text
    assert "AllowedOAuthFlows:" in template_text
    assert "        - code" in template_text
    assert "ManagedLoginVersion: 2" in template_text
    assert "DeployWebGateway:" in template_text
    assert "ShouldDeployWebGateway:" in template_text
    assert "GatewayTenantMappingSecret:" in template_text
    assert "AWS::Lambda::Function" in template_text
    assert "AWS::ApiGatewayV2::Api" in template_text
    assert "AWS::ApiGatewayV2::Authorizer" in template_text
    assert "AuthorizerType: JWT" in template_text
    assert "AWS::ApiGatewayV2::Integration" in template_text
    assert "PayloadFormatVersion: \"2.0\"" in template_text
    assert "AWS::Lambda::Permission" in template_text
    assert "SAURUS_GATEWAY_TENANT_MAPPINGS_JSON" in template_text


def test_aws_alpha_template_declares_minimum_operational_alarms() -> None:
    """Require alerting resources before the alpha template is deployable."""

    review = review_aws_alpha_monitoring(TEMPLATE)

    assert isinstance(review, AwsAlphaMonitoringReview)
    assert review.go
    assert review.blockers == ()
    assert review.has_alert_topic
    assert review.missing_alarms == ()
    assert review.alarms_use_topic
    assert set(review.required_alarms) == {
        "RegistryAlb5xxAlarm",
        "RegistryUnhealthyTargetsAlarm",
        "RegistryEcsCpuAlarm",
        "RegistryDatabaseStorageAlarm",
    }


def test_aws_alpha_template_declares_hardened_image_repository() -> None:
    """Require an ECR repository before image push and ECS smoke testing."""

    review = review_aws_alpha_image(TEMPLATE)

    assert isinstance(review, AwsAlphaImageReview)
    assert review.go
    assert review.blockers == ()
    assert review.has_repository
    assert review.immutable_tags
    assert review.scan_on_push
    assert review.encrypted
    assert review.has_lifecycle_policy
    assert review.has_repository_output
    assert review.has_alpha_image_pattern
    assert '"/app[audio,aws-alpha]"' in DOCKERFILE.read_text(encoding="utf-8")


def test_aws_alpha_template_injects_managed_secrets() -> None:
    """Require ECS secret injection for alpha runtime credentials."""

    review = review_aws_alpha_secrets(TEMPLATE)

    assert isinstance(review, AwsAlphaSecretsReview)
    assert review.go
    assert review.blockers == ()
    assert review.missing_secret_envs == ()
    assert review.forbidden_plain_envs == ()
    assert review.execution_role_can_read_secrets
    assert review.has_postgres_runtime_env
    assert set(review.required_secret_envs) == {
        "SAURUS_API_SIGNING_SECRET",
        "SAURUS_DATABASE_SECRET_JSON",
        "SAURUS_BOOTSTRAP_ADMIN_SECRET",
        "SAURUS_DEVICE_ENROLLMENT_SECRET",
    }


def test_aws_alpha_endpoint_smoke_validates_health_and_privacy() -> None:
    """Exercise the deployed endpoint smoke check without contacting AWS."""

    result = smoke_alpha_endpoint(
        "https://registry-alpha.example.test",
        fetch=lambda url, timeout: (200, b'{"status":"ok"}'),
    )

    assert isinstance(result, AlphaEndpointSmokeResult)
    assert result.ok
    assert result.health_url == "https://registry-alpha.example.test/health"
    assert result.body_bytes == len(b'{"status":"ok"}')


def test_aws_alpha_endpoint_smoke_rejects_bad_or_leaky_health() -> None:
    """Block endpoint smoke evidence that is not a clean health response."""

    try:
        smoke_alpha_endpoint("http://registry-alpha.example.test", fetch=lambda url, timeout: (200, b'{"status":"ok"}'))
    except ValueError as error:
        assert "https" in str(error)
    else:
        raise AssertionError("non-HTTPS endpoint should fail")
    try:
        smoke_alpha_endpoint("https://registry-alpha.example.test", fetch=lambda url, timeout: (200, b'{"status":"ok","token":"x"}'))
    except ValueError as error:
        assert "recognized" in str(error)
    else:
        raise AssertionError("leaky health response should fail")


def test_aws_alpha_template_review_blocks_missing_guardrails(tmp_path: Path) -> None:
    """Reject an alpha template that omits tags, budget, encryption, and privacy."""

    template = tmp_path / "template.yaml"
    template.write_text(
        "\n".join(
            (
                'AWSTemplateFormatVersion: "2010-09-09"',
                "Resources:",
                "  RegistryDatabase:",
                "    Type: AWS::RDS::DBInstance",
                "    Properties:",
                "      PubliclyAccessible: true",
                "  RegistryNatGateway:",
                "    Type: AWS::EC2::NatGateway",
                "Outputs:",
                "  Name:",
                "    Value: bad",
            )
        ),
        encoding="utf-8",
    )

    review = review_aws_alpha_template(template)

    assert not review.go
    assert "missing required tags: RegistryDatabase" in review.blockers
    assert "monthly budget alert is missing" in review.blockers
    assert "registry database must not be public" in review.blockers
    assert "forbidden alpha resource marker present: AWS::EC2::NatGateway" in review.blockers


def test_aws_alpha_monitoring_review_blocks_missing_alarms(tmp_path: Path) -> None:
    """Reject monitoring drafts that cannot page alpha operators."""

    template = tmp_path / "template.yaml"
    template.write_text(
        "\n".join(
            (
                'AWSTemplateFormatVersion: "2010-09-09"',
                "Resources:",
                "  RegistryAlb5xxAlarm:",
                "    Type: AWS::CloudWatch::Alarm",
                "Outputs:",
                "  Name:",
                "    Value: bad",
            )
        ),
        encoding="utf-8",
    )

    review = review_aws_alpha_monitoring(template)

    assert not review.go
    assert "operations alert topic is missing" in review.blockers
    assert "missing required alarms: RegistryUnhealthyTargetsAlarm, RegistryEcsCpuAlarm, RegistryDatabaseStorageAlarm" in review.blockers
    assert "required alarms must publish to the operations topic" in review.blockers


def test_aws_alpha_image_review_blocks_unhardened_repository(tmp_path: Path) -> None:
    """Reject image repository drafts without scan, encryption, or output."""

    template = tmp_path / "template.yaml"
    template.write_text(
        "\n".join(
            (
                'AWSTemplateFormatVersion: "2010-09-09"',
                "Resources:",
                "  RegistryImageRepository:",
                "    Type: AWS::ECR::Repository",
            )
        ),
        encoding="utf-8",
    )

    review = review_aws_alpha_image(template)

    assert not review.go
    assert "ECR repository must use immutable tags" in review.blockers
    assert "ECR repository must scan images on push" in review.blockers
    assert "ECR repository KMS encryption is missing" in review.blockers
    assert "ECR repository lifecycle policy is missing" in review.blockers
    assert "ECR repository URI output is missing" in review.blockers
    assert "container image parameter must require an alpha ECR tag" in review.blockers


def test_aws_alpha_secrets_review_blocks_plain_secret_envs(tmp_path: Path) -> None:
    """Reject task definitions that pass secret ARNs as ordinary env values."""

    template = tmp_path / "template.yaml"
    template.write_text(
        "\n".join(
            (
                'AWSTemplateFormatVersion: "2010-09-09"',
                "Resources:",
                "  RegistryTaskDefinition:",
                "    Type: AWS::ECS::TaskDefinition",
                "    Properties:",
                "      ContainerDefinitions:",
                "        - Name: registry",
                "          Environment:",
                "            - Name: SAURUS_DATABASE_SECRET_ARN",
                "              Value: database-secret",
            )
        ),
        encoding="utf-8",
    )

    review = review_aws_alpha_secrets(template)

    assert not review.go
    assert "missing ECS secret envs: SAURUS_API_SIGNING_SECRET, SAURUS_DATABASE_SECRET_JSON, SAURUS_BOOTSTRAP_ADMIN_SECRET, SAURUS_DEVICE_ENROLLMENT_SECRET" in review.blockers
    assert "secret ARN envs must not be plain container envs: SAURUS_DATABASE_SECRET_ARN" in review.blockers
    assert "task execution role cannot read all injected secrets" in review.blockers
    assert "PostgreSQL runtime endpoint env is missing" in review.blockers
