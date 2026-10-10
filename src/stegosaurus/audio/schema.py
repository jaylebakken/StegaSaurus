"""Expose the research-readable audio watermark schema facade.

Read this module first when following the application process map:

    epoch + secret -> expected detector bits -> statistical decision
    opaque token -> Reed--Solomon transport plan -> future attribution recovery

``schema_models`` contains the plain configuration and result records, while
``schema_engine`` contains the keyed policy and significance calculation. This
facade preserves the original public imports for applications and experiments.
"""

from .schema_engine import AudioWatermarkSchema
from .schema_models import (
    AudioAttributionResult,
    AudioDetectionResult,
    AudioDetectionStatus,
    AudioWatermarkConfig,
)
from .transport_models import CarrierPlan

__all__ = [
    "AudioAttributionResult",
    "AudioDetectionResult",
    "AudioDetectionStatus",
    "AudioWatermarkConfig",
    "AudioWatermarkSchema",
    "CarrierPlan",
]
