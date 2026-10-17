"""Serialize opaque bytes into framed, interleaved Reed--Solomon carrier bits.

Pseudocode:
    token bytes -> RS codeword -> bits -> keyed permutation -> sync frames
    observations -> unframe -> inverse permutation -> byte erasures -> RS decode

An undecided carrier bit becomes a byte erasure. A wrong confident bit remains
an unknown byte error, which consumes twice as much Reed--Solomon budget.
"""

from __future__ import annotations

from collections.abc import Iterable, Sequence

from .ecc import ErrorCorrectionError, ReedSolomonCodec
from .transport_framing import BitFramer
from .transport_interleaving import KeyedBitInterleaver
from .transport_models import CarrierBit, CarrierPlan, ChannelRecovery, CodewordObservation

class ReedSolomonChannel:
    """Convert payload bytes into framed carrier bits and recover them after extraction."""

    def __init__(
        self,
        codec: ReedSolomonCodec,
        interleaver: KeyedBitInterleaver,
        framer: BitFramer | None = None,
    ) -> None:
        """Initialize the channel with error correction, interleaving, and framing rules."""

        self._codec = codec
        self._interleaver = interleaver
        self._framer = framer or BitFramer()

    def plan(self, payload: bytes) -> CarrierPlan:
        """Encode a payload into the exact ordered bit sequence required from carriers."""

        normalized_payload = bytes(payload)
        codeword = self._codec.encode(normalized_payload)
        interleaved_bits = self._interleaver.interleave(self._bytes_to_bits(codeword))
        return CarrierPlan(
            len(normalized_payload),
            len(codeword),
            self._framer.frame(interleaved_bits),
        )

    @property
    def parity_symbols(self) -> int:
        """Return the Reed--Solomon parity-byte budget used by this channel."""

        return self._codec.parity_symbols

    def carrier_bit_count(self, payload_length: int) -> int:
        """Return how many binary audio-carrier decisions are required for one token length."""

        if payload_length < 1:
            raise ValueError("payload_length must be positive")
        codeword_bits = (payload_length + self._codec.parity_symbols) * 8
        return self._framer.carrier_bit_count(codeword_bits)

    def recover(
        self,
        carrier_bits: Sequence[CarrierBit],
        payload_length: int,
    ) -> ChannelRecovery:
        """Deframe, deinterleave, and error-correct carrier observations into payload bytes."""

        if payload_length < 1:
            raise ValueError("payload_length must be positive")
        observation = self.inspect_carrier_bits(carrier_bits, payload_length)
        try:
            decoded = self._codec.decode(observation.codeword, observation.erasure_positions)
        except ErrorCorrectionError as error:
            return ChannelRecovery(
                None,
                (),
                observation.erasure_positions,
                observation.synchronization_mismatches,
                observation.extra_carrier_bits,
                str(error),
            )
        return ChannelRecovery(
            decoded.payload,
            decoded.corrected_positions,
            observation.erasure_positions,
            observation.synchronization_mismatches,
            observation.extra_carrier_bits,
            None,
        )

    def inspect_carrier_bits(
        self,
        carrier_bits: Sequence[CarrierBit],
        payload_length: int,
    ) -> CodewordObservation:
        """Reconstruct codeword bytes and known erasures without attempting correction."""

        if payload_length < 1:
            raise ValueError("payload_length must be positive")
        codeword_length = payload_length + self._codec.parity_symbols
        frame_recovery = self._framer.unframe(carrier_bits, codeword_length * 8)
        codeword_bits = self._interleaver.deinterleave(frame_recovery.data_bits)
        codeword, erasure_positions = self._bits_to_bytes(codeword_bits)
        return CodewordObservation(
            codeword,
            erasure_positions,
            frame_recovery.synchronization_mismatches,
            frame_recovery.extra_carrier_bits,
        )

    @staticmethod
    def _bytes_to_bits(data: bytes) -> tuple[int, ...]:
        """Serialize bytes into most-significant-bit-first binary carrier values."""

        return tuple(
            (byte_value >> shift) & 1
            for byte_value in bytes(data)
            for shift in range(7, -1, -1)
        )

    @staticmethod
    def _bits_to_bytes(bits: Iterable[CarrierBit]) -> tuple[bytes, tuple[int, ...]]:
        """Serialize eight-bit groups and mark any group containing an erasure."""

        normalized_bits = tuple(bits)
        if len(normalized_bits) % 8:
            raise ValueError("codeword bit count must be divisible by eight")
        bytes_out = bytearray()
        erasure_positions: list[int] = []
        for byte_position in range(0, len(normalized_bits), 8):
            bit_group = normalized_bits[byte_position : byte_position + 8]
            if None in bit_group:
                erasure_positions.append(byte_position // 8)
                bytes_out.append(0)
                continue
            byte_value = 0
            for bit_value in bit_group:
                byte_value = (byte_value << 1) | int(bit_value)
            bytes_out.append(byte_value)
        return bytes(bytes_out), tuple(erasure_positions)
