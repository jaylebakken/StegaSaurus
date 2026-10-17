"""Review desktop release posture for embedded watermark secrets.

The alpha desktop still uses a local-demo watermark secret so the sidecar
workflow can run without a hosted KMS grant service. That constant is not a
production key. This module gives release checks a small, explicit signal:
production packaging must not present the desktop app as carrying a shared
production watermark secret, and the remaining local secret must be labelled as
local demo material until KMS-backed grants replace it.
"""

from __future__ import annotations

from dataclasses import dataclass

from .registry import WATERMARK_SECRET_SCOPE


@dataclass(frozen=True, slots=True)
class DesktopSecretPosture:
    """Summarize whether the desktop watermark secret posture can ship."""

    scope: str
    has_shared_production_secret: bool
    production_ready: bool

    def __post_init__(self) -> None:
        """Validate the posture summary."""

        if not self.scope.strip():
            raise ValueError("scope must not be empty")


def review_desktop_secret_posture() -> DesktopSecretPosture:
    """Return the current desktop watermark-secret release posture."""

    return DesktopSecretPosture(
        WATERMARK_SECRET_SCOPE,
        has_shared_production_secret=False,
        production_ready=WATERMARK_SECRET_SCOPE != "local-demo-only",
    )
