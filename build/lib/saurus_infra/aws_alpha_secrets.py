"""Review managed-secret injection for the AWS alpha registry task.

The CloudFormation draft creates managed secrets for API signing, database
credentials, bootstrap admin, and device enrollment. This local check verifies
that the ECS task receives those values through the task definition `Secrets`
block rather than as plain environment values. It does not confirm live secret
rotation or deployed secret contents.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__ = ["AwsAlphaSecretsReview", "review_aws_alpha_secrets"]

_REQUIRED_SECRET_ENVS = (
    "SAURUS_API_SIGNING_SECRET",
    "SAURUS_DATABASE_SECRET_JSON",
    "SAURUS_BOOTSTRAP_ADMIN_SECRET",
    "SAURUS_DEVICE_ENROLLMENT_SECRET",
)
_FORBIDDEN_ENV_NAMES = (
    "SAURUS_API_SIGNING_SECRET_ARN",
    "SAURUS_DATABASE_SECRET_ARN",
    "SAURUS_BOOTSTRAP_ADMIN_SECRET_ARN",
    "SAURUS_DEVICE_ENROLLMENT_SECRET_ARN",
)


@dataclass(frozen=True, slots=True)
class AwsAlphaSecretsReview:
    """Summarize managed-secret task wiring in the AWS alpha template."""

    required_secret_envs: tuple[str, ...]
    missing_secret_envs: tuple[str, ...]
    forbidden_plain_envs: tuple[str, ...]
    execution_role_can_read_secrets: bool
    has_postgres_runtime_env: bool
    go: bool
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate blocker consistency."""

        if self.go and self.blockers:
            raise ValueError("go cannot be true while blockers exist")


def review_aws_alpha_secrets(path: Path) -> AwsAlphaSecretsReview:
    """Review managed secret injection in one alpha template."""

    template_text = path.read_text(encoding="utf-8")
    missing = tuple(name for name in _REQUIRED_SECRET_ENVS if f"Name: {name}" not in template_text)
    forbidden = tuple(name for name in _FORBIDDEN_ENV_NAMES if f"Name: {name}" in template_text)
    has_postgres_runtime_env = all(
        f"Name: {name}" in template_text
        for name in ("SAURUS_POSTGRES_HOST", "SAURUS_POSTGRES_PORT", "SAURUS_POSTGRES_DATABASE")
    )
    can_read = all(
        marker in template_text
        for marker in ("saurus-alpha-registry-secret-injection", "secretsmanager:GetSecretValue", "RegistryApiSigningSecret", "DatabaseSecret", "BootstrapAdminSecret", "DeviceEnrollmentSecret")
    )
    blockers = _blockers(missing, forbidden, can_read, has_postgres_runtime_env)
    return AwsAlphaSecretsReview(_REQUIRED_SECRET_ENVS, missing, forbidden, can_read, has_postgres_runtime_env, not blockers, blockers)


def _blockers(
    missing_secret_envs: tuple[str, ...],
    forbidden_plain_envs: tuple[str, ...],
    execution_role_can_read_secrets: bool,
    has_postgres_runtime_env: bool,
) -> tuple[str, ...]:
    """Return managed-secret wiring blockers."""

    blockers: list[str] = []
    if missing_secret_envs:
        blockers.append("missing ECS secret envs: " + ", ".join(missing_secret_envs))
    if forbidden_plain_envs:
        blockers.append("secret ARN envs must not be plain container envs: " + ", ".join(forbidden_plain_envs))
    if not execution_role_can_read_secrets:
        blockers.append("task execution role cannot read all injected secrets")
    if not has_postgres_runtime_env:
        blockers.append("PostgreSQL runtime endpoint env is missing")
    return tuple(blockers)
