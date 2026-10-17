"""Review AWS alpha monitoring resources before deployment.

The main alpha template review checks broad deployment guardrails. This module
focuses on the operational alert slice: a notification topic and the minimum
CloudWatch alarms that make the disposable registry stack observable enough for
alpha tests. It is local text evidence only; live subscriptions and alarm
delivery still require AWS deployment validation.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

__all__ = ["AwsAlphaMonitoringReview", "review_aws_alpha_monitoring"]

_REQUIRED_ALARMS = (
    "RegistryAlb5xxAlarm",
    "RegistryUnhealthyTargetsAlarm",
    "RegistryEcsCpuAlarm",
    "RegistryDatabaseStorageAlarm",
)


@dataclass(frozen=True, slots=True)
class AwsAlphaMonitoringReview:
    """Summarize local monitoring checks for the AWS alpha template."""

    has_alert_topic: bool
    required_alarms: tuple[str, ...]
    missing_alarms: tuple[str, ...]
    alarms_use_topic: bool
    go: bool
    blockers: tuple[str, ...]

    def __post_init__(self) -> None:
        """Validate blocker consistency."""

        if self.go and self.blockers:
            raise ValueError("go cannot be true while blockers exist")


def review_aws_alpha_monitoring(path: Path) -> AwsAlphaMonitoringReview:
    """Review CloudWatch/SNS monitoring resources in one alpha template."""

    template_text = path.read_text(encoding="utf-8")
    has_alert_topic = "AWS::SNS::Topic" in template_text and "OperationsAlertTopic" in template_text
    missing = tuple(name for name in _REQUIRED_ALARMS if name not in template_text)
    alarms_use_topic = "AlarmActions:" in template_text and "!Ref OperationsAlertTopic" in template_text
    blockers = _blockers(has_alert_topic, missing, alarms_use_topic)
    return AwsAlphaMonitoringReview(
        has_alert_topic,
        _REQUIRED_ALARMS,
        missing,
        alarms_use_topic,
        not blockers,
        blockers,
    )


def _blockers(
    has_alert_topic: bool,
    missing_alarms: tuple[str, ...],
    alarms_use_topic: bool,
) -> tuple[str, ...]:
    """Return local monitoring blockers."""

    blockers: list[str] = []
    if not has_alert_topic:
        blockers.append("operations alert topic is missing")
    if missing_alarms:
        blockers.append("missing required alarms: " + ", ".join(missing_alarms))
    if not alarms_use_topic:
        blockers.append("required alarms must publish to the operations topic")
    return tuple(blockers)
