"""Expose the bounded v1 claimed-handle attribution prototype.

Use this API only with a registry that retains each ``AttributionRecord``. The
current implementation verifies a supplied claim through a known carrier map;
it does not discover unknown handles from arbitrary audio. See the module
docstrings for explicit scope limits and named experimental evidence.
"""

from .attribution_decoder import SpectralAttributionDecoder
from .attribution_encoder import SpectralAttributionEncoder
from .attribution_models import (
    AttributionEmbedding,
    AttributionRecord,
    AttributionStatus,
    AttributionVerification,
    SpectralAttributionConfig,
)
from .attribution_registry import InMemoryAttributionRegistry, RegistryEntry

__all__ = [
    "AttributionEmbedding",
    "AttributionRecord",
    "AttributionStatus",
    "AttributionVerification",
    "InMemoryAttributionRegistry",
    "RegistryEntry",
    "SpectralAttributionConfig",
    "SpectralAttributionDecoder",
    "SpectralAttributionEncoder",
]
