"""Expose the bounded claimed-handle attribution prototypes.

Use these APIs only with a registry that retains attribution records. The v1
surface verifies one retained carrier map. The v2 block surface repeats the
same handle across fixed-duration blocks and pools retained block evidence. The
public facade still does not claim unknown-handle discovery from arbitrary
audio; blind localization remains a measured experiment path until promoted.
"""

from .attribution_core import (
    AttributionEmbedding,
    AttributionRecord,
    AttributionStatus,
    AttributionVerification,
    BlindRecoveryDecision,
    BlindRecoveryDecisionPolicy,
    BlindRecoveryStatus,
    BlindRecoveryVote,
    BlockAttributionCodec,
    BlockAttributionEmbedding,
    BlockAttributionRecord,
    BlockAttributionVerification,
    InMemoryAttributionRegistry,
    RegistryEntry,
    SpectralAttributionConfig,
    SpectralAttributionDecoder,
    SpectralAttributionEncoder,
)

__all__ = [
    "AttributionEmbedding",
    "AttributionRecord",
    "AttributionStatus",
    "AttributionVerification",
    "BlockAttributionCodec",
    "BlockAttributionEmbedding",
    "BlockAttributionRecord",
    "BlockAttributionVerification",
    "BlindRecoveryDecision",
    "BlindRecoveryDecisionPolicy",
    "BlindRecoveryStatus",
    "BlindRecoveryVote",
    "InMemoryAttributionRegistry",
    "RegistryEntry",
    "SpectralAttributionConfig",
    "SpectralAttributionDecoder",
    "SpectralAttributionEncoder",
]
