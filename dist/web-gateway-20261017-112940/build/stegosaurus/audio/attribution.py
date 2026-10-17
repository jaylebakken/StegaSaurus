"""Expose the bounded claimed-handle attribution prototypes.

Use these APIs only with a registry that retains attribution records. The v1
surface verifies one retained carrier map. The repeated-block surface embeds
the same handle across fixed-duration blocks, pools retained block evidence,
and exposes the repeated-block fast-vote/pooling decision layer. The public
facade still does not claim unknown-handle discovery from arbitrary audio.
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
    RepeatedBlockWaterfallDecision,
    RepeatedBlockWaterfallPolicy,
    RepeatedBlockWaterfallStage,
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
    "RepeatedBlockWaterfallDecision",
    "RepeatedBlockWaterfallPolicy",
    "RepeatedBlockWaterfallStage",
    "SpectralAttributionConfig",
    "SpectralAttributionDecoder",
    "SpectralAttributionEncoder",
]
