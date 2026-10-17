"""Apply a deterministic secret-keyed permutation to protected carrier bits.

Interleaving spreads a local burst across codeword symbols so Reed--Solomon sees
more independent damage. It is not encryption: the payload remains opaque only
when the application chooses opaque registry handles and authenticates lookup.
"""

from __future__ import annotations

from collections.abc import Sequence
import hashlib
import hmac

from .transport_framing import BitFramer
from .transport_models import CarrierBit

class KeyedBitInterleaver:
    """Apply a reproducible secret-keyed permutation to a fixed bit sequence length."""

    def __init__(self, secret: bytes) -> None:
        """Initialize the interleaver with a non-empty shared secret."""

        if not secret:
            raise ValueError("secret must not be empty")
        self._secret = bytes(secret)

    def interleave(self, bits: Sequence[int]) -> tuple[int, ...]:
        """Permute data bits into their carrier transmission order."""

        normalized_bits = BitFramer._validate_binary_bits(bits)
        permutation = self._permutation(len(normalized_bits))
        return tuple(normalized_bits[source_index] for source_index in permutation)

    def deinterleave(self, bits: Sequence[CarrierBit]) -> tuple[CarrierBit, ...]:
        """Invert the secret-keyed permutation while preserving carrier erasures."""

        normalized_bits = BitFramer._validate_carrier_bits(bits)
        permutation = self._permutation(len(normalized_bits))
        restored_bits: list[CarrierBit] = [None] * len(normalized_bits)
        for transmitted_index, source_index in enumerate(permutation):
            restored_bits[source_index] = normalized_bits[transmitted_index]
        return tuple(restored_bits)

    def _permutation(self, length: int) -> tuple[int, ...]:
        """Derive a Fisher--Yates permutation from HMAC output and sequence length."""

        positions = list(range(length))
        for upper_index in range(length - 1, 0, -1):
            digest = hmac.new(
                self._secret,
                length.to_bytes(4, "big") + upper_index.to_bytes(4, "big"),
                hashlib.sha256,
            ).digest()
            swap_index = int.from_bytes(digest[:8], "big") % (upper_index + 1)
            positions[upper_index], positions[swap_index] = (
                positions[swap_index],
                positions[upper_index],
            )
        return tuple(positions)

