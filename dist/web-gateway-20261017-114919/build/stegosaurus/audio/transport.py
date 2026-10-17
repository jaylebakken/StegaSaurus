"""Expose the attribution-transport building blocks in reading order.

The transport path is intentionally decomposed:

    opaque bytes -> Reed--Solomon symbols -> keyed interleaving -> sync frames
    carrier observations -> sync recovery -> byte erasures -> RS decoding

Use this facade for stable imports. Read ``transport_framing``,
``transport_interleaving``, and ``transport_channel`` for the individual steps.
The transport code carries bits only; it does not choose audio frequencies or
claim that a waveform survives any particular transformation.
"""

from .transport_channel import ReedSolomonChannel
from .transport_framing import BitFramer
from .transport_interleaving import KeyedBitInterleaver
from .transport_models import (
    CarrierBit,
    CarrierPlan,
    ChannelRecovery,
    CodewordObservation,
    FrameRecovery,
    SyncScanRecovery,
)

__all__ = [
    "BitFramer",
    "CarrierBit",
    "CarrierPlan",
    "ChannelRecovery",
    "CodewordObservation",
    "FrameRecovery",
    "KeyedBitInterleaver",
    "ReedSolomonChannel",
    "SyncScanRecovery",
]
