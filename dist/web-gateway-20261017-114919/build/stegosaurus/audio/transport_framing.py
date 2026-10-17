"""Frame carrier bits with synchronization markers and recover bounded drift.

Pseudocode:
    protected bits -> [SYNC | data] [SYNC | data] -> carrier positions
    received positions -> scan for nearby SYNC markers -> data or erasure

The framer detects local disagreement; it cannot by itself solve arbitrary
insertions, deletions, or time-scale drift in a real audio stream.
"""

from __future__ import annotations

from collections.abc import Sequence
import math

from .transport_models import CarrierBit, FrameRecovery, SyncScanRecovery

_DEFAULT_SYNC_PATTERN = (1, 0, 1, 1, 0, 0, 1, 0)

class BitFramer:
    """Insert and inspect fixed synchronization patterns around data-bit frames."""

    def __init__(
        self,
        data_bits_per_frame: int = 64,
        sync_pattern: Sequence[int] = _DEFAULT_SYNC_PATTERN,
    ) -> None:
        """Initialize validated frame data capacity and a binary sync pattern."""

        if data_bits_per_frame < 1:
            raise ValueError("data_bits_per_frame must be positive")
        self._data_bits_per_frame = data_bits_per_frame
        self._sync_pattern = self._validate_binary_bits(sync_pattern)

    @property
    def data_bits_per_frame(self) -> int:
        """Return the maximum number of protected data bits in one frame."""

        return self._data_bits_per_frame

    @property
    def sync_pattern(self) -> tuple[int, ...]:
        """Return the fixed synchronization pattern inserted before each frame."""

        return self._sync_pattern

    def carrier_bit_count(self, data_bit_count: int) -> int:
        """Return the exact carrier count needed to transport data bits in frames."""

        if data_bit_count < 0:
            raise ValueError("data_bit_count must not be negative")
        if not data_bit_count:
            return 0
        frame_count = math.ceil(data_bit_count / self._data_bits_per_frame)
        return data_bit_count + frame_count * len(self._sync_pattern)

    def frame(self, data_bits: Sequence[int]) -> tuple[int, ...]:
        """Prefix each data chunk with a synchronization pattern for carrier embedding."""

        normalized_bits = self._validate_binary_bits(data_bits)
        framed_bits: list[int] = []
        for start in range(0, len(normalized_bits), self._data_bits_per_frame):
            framed_bits.extend(self._sync_pattern)
            framed_bits.extend(normalized_bits[start : start + self._data_bits_per_frame])
        return tuple(framed_bits)

    def unframe(
        self,
        carrier_bits: Sequence[CarrierBit],
        data_bit_count: int,
    ) -> FrameRecovery:
        """Recover data positions and report sync mismatches from ordered carrier bits."""

        if data_bit_count < 0:
            raise ValueError("data_bit_count must not be negative")
        normalized_bits = self._validate_carrier_bits(carrier_bits)
        recovered_bits: list[CarrierBit] = []
        synchronization_mismatches = 0
        source_position = 0
        remaining_data_bits = data_bit_count
        while remaining_data_bits:
            for expected_sync_bit in self._sync_pattern:
                observed_sync_bit = self._at_or_none(normalized_bits, source_position)
                if observed_sync_bit != expected_sync_bit:
                    synchronization_mismatches += 1
                source_position += 1
            current_frame_bits = min(remaining_data_bits, self._data_bits_per_frame)
            for _ in range(current_frame_bits):
                recovered_bits.append(self._at_or_none(normalized_bits, source_position))
                source_position += 1
            remaining_data_bits -= current_frame_bits
        return FrameRecovery(
            tuple(recovered_bits),
            synchronization_mismatches,
            max(0, len(normalized_bits) - source_position),
        )

    def scan_unframe(
        self,
        carrier_bits: Sequence[CarrierBit],
        data_bit_count: int,
        search_radius: int = 16,
        maximum_sync_mismatches: int = 0,
    ) -> SyncScanRecovery:
        """Resynchronize each frame by scanning near its expected sync-pattern position."""

        if data_bit_count < 0:
            raise ValueError("data_bit_count must not be negative")
        if search_radius < 0:
            raise ValueError("search_radius must not be negative")
        if not 0 <= maximum_sync_mismatches <= len(self._sync_pattern):
            raise ValueError("maximum_sync_mismatches is outside the sync-pattern range")
        normalized_bits = self._validate_carrier_bits(carrier_bits)
        recovered_bits: list[CarrierBit] = []
        frame_starts: list[int | None] = []
        synchronization_mismatches = 0
        expected_start = 0
        last_observed_position = 0
        remaining_data_bits = data_bit_count
        while remaining_data_bits:
            current_frame_bits = min(remaining_data_bits, self._data_bits_per_frame)
            frame_start, mismatch_count = self._find_sync(
                normalized_bits,
                expected_start,
                search_radius,
            )
            if frame_start is None or mismatch_count > maximum_sync_mismatches:
                frame_starts.append(None)
                synchronization_mismatches += len(self._sync_pattern)
                recovered_bits.extend([None] * current_frame_bits)
                expected_start += len(self._sync_pattern) + current_frame_bits
            else:
                frame_starts.append(frame_start)
                synchronization_mismatches += mismatch_count
                data_start = frame_start + len(self._sync_pattern)
                recovered_bits.extend(
                    self._at_or_none(normalized_bits, data_start + offset)
                    for offset in range(current_frame_bits)
                )
                expected_start = data_start + current_frame_bits
                last_observed_position = max(last_observed_position, expected_start)
            remaining_data_bits -= current_frame_bits
        return SyncScanRecovery(
            tuple(recovered_bits),
            synchronization_mismatches,
            max(0, len(normalized_bits) - last_observed_position),
            tuple(frame_starts),
        )

    @staticmethod
    def _at_or_none(bits: Sequence[CarrierBit], position: int) -> CarrierBit:
        """Return a carrier bit at one position or an erasure after the observed end."""

        return bits[position] if position < len(bits) else None

    def _find_sync(
        self,
        carrier_bits: Sequence[CarrierBit],
        expected_start: int,
        search_radius: int,
    ) -> tuple[int | None, int]:
        """Locate the least-mismatched sync pattern near one predicted frame position."""

        first_position = max(0, expected_start - search_radius)
        last_position = min(
            len(carrier_bits) - len(self._sync_pattern),
            expected_start + search_radius,
        )
        if last_position < first_position:
            return None, len(self._sync_pattern)
        candidates: list[tuple[int, int]] = []
        for position in range(first_position, last_position + 1):
            mismatches = sum(
                self._at_or_none(carrier_bits, position + offset) != expected_bit
                for offset, expected_bit in enumerate(self._sync_pattern)
            )
            candidates.append((mismatches, position))
        mismatch_count, position = min(
            candidates,
            key=lambda candidate: (
                candidate[0],
                abs(candidate[1] - expected_start),
                candidate[1] < expected_start,
                candidate[1],
            ),
        )
        return position, mismatch_count

    @staticmethod
    def _validate_binary_bits(bits: Sequence[int]) -> tuple[int, ...]:
        """Validate and copy a sequence containing only binary integer values."""

        normalized_bits = tuple(bits)
        if any(bit not in (0, 1) for bit in normalized_bits):
            raise ValueError("bits must contain only 0 or 1")
        return normalized_bits

    @staticmethod
    def _validate_carrier_bits(bits: Sequence[CarrierBit]) -> tuple[CarrierBit, ...]:
        """Validate and copy carrier observations that may include erasures."""

        normalized_bits = tuple(bits)
        if any(bit not in (0, 1, None) for bit in normalized_bits):
            raise ValueError("carrier bits must contain 0, 1, or None")
        return normalized_bits


