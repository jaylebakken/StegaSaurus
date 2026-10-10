"""Group claimed-handle attribution implementation by task.

The public ``stegosaurus.audio.attribution`` facade re-exports these objects.
This package keeps records, registry behavior, single-block codecs, repeated
block pooling, and blind-recovery policy gates together without mixing them
with lower-level pilot, schema, or transport code.
"""

from __future__ import annotations

from .blind_policy import (
    BlindRecoveryDecision,
    BlindRecoveryDecisionPolicy,
    BlindRecoveryStatus,
    BlindRecoveryVote,
)
from .blocks import BlockAttributionCodec, BlockAttributionEmbedding, BlockAttributionRecord, BlockAttributionVerification
from .decoder import SpectralAttributionDecoder
from .encoder import SpectralAttributionEncoder
from .models import (
    AttributionEmbedding,
    AttributionRecord,
    AttributionStatus,
    AttributionVerification,
    SpectralAttributionConfig,
)
from .registry import InMemoryAttributionRegistry, RegistryEntry

__all__ = [
    "AttributionEmbedding",
    "AttributionRecord",
    "AttributionStatus",
    "AttributionVerification",
    "BlindRecoveryDecision",
    "BlindRecoveryDecisionPolicy",
    "BlindRecoveryStatus",
    "BlindRecoveryVote",
    "BlockAttributionCodec",
    "BlockAttributionEmbedding",
    "BlockAttributionRecord",
    "BlockAttributionVerification",
    "InMemoryAttributionRegistry",
    "RegistryEntry",
    "SpectralAttributionConfig",
    "SpectralAttributionDecoder",
    "SpectralAttributionEncoder",
]

