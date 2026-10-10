"""Wrap Reed--Solomon encoding and decoding for future audio attribution.

This is a narrow validation boundary around ``reedsolo``. It protects opaque
registry-handle bytes after a carrier has produced bit observations; it does not
select audio carriers or decide whether a watermark is statistically present.

Pseudocode:
    payload bytes -> systematic RS codeword -> transport bits
    observed bits -> known byte erasures + unknown byte errors -> RS decode

The correction condition is ``2 * unknown_errors + known_erasures <= parity``.
Calling an uncertain carrier an erasure is therefore often safer than guessing a
bit. The wrapper records corrected positions but does not claim recovery under
any named audio transformation unless an experiment measures that path.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass

from reedsolo import RSCodec, ReedSolomonError


class ErrorCorrectionError(ValueError):
    """Report an invalid or uncorrectable Reed--Solomon codeword."""


@dataclass(frozen=True, slots=True)
class DecodedPayload:
    """Represent a recovered payload and the symbol positions corrected in transit."""

    payload: bytes
    corrected_positions: tuple[int, ...]


class ReedSolomonCodec:
    """Encode payloads and recover them from errors or declared erasures."""

    def __init__(self, parity_symbols: int) -> None:
        """Initialize a GF(256) codec with the requested parity-symbol count."""

        if not 1 <= parity_symbols < 255:
            raise ValueError("parity_symbols must be between 1 and 254")
        self._parity_symbols = parity_symbols
        self._codec = RSCodec(parity_symbols)

    @property
    def parity_symbols(self) -> int:
        """Return the number of parity bytes appended to each encoded payload."""

        return self._parity_symbols

    def encode(self, payload: bytes) -> bytes:
        """Return one systematic codeword containing payload and parity symbols."""

        normalized_payload = bytes(payload)
        if not normalized_payload:
            raise ValueError("payload must not be empty")
        if len(normalized_payload) + self._parity_symbols > 255:
            raise ValueError("payload and parity symbols must fit in one codeword")
        return bytes(self._codec.encode(normalized_payload))

    def decode(
        self,
        codeword: bytes,
        erasure_positions: Iterable[int] = (),
    ) -> DecodedPayload:
        """Recover a payload from a codeword and optionally declared erasure indices."""

        normalized_codeword = bytes(codeword)
        if len(normalized_codeword) <= self._parity_symbols:
            raise ErrorCorrectionError("codeword does not contain a payload")
        if len(normalized_codeword) > 255:
            raise ErrorCorrectionError("codeword exceeds the GF(256) symbol limit")
        erasures = self._validate_erasure_positions(
            erasure_positions,
            len(normalized_codeword),
        )
        try:
            payload, _, corrected_positions = self._codec.decode(
                normalized_codeword,
                erase_pos=list(erasures),
            )
        except ReedSolomonError as error:
            raise ErrorCorrectionError("codeword could not be corrected") from error
        return DecodedPayload(bytes(payload), tuple(corrected_positions))

    @staticmethod
    def _validate_erasure_positions(
        erasure_positions: Iterable[int],
        codeword_length: int,
    ) -> tuple[int, ...]:
        """Validate, sort, and deduplicate declared codeword erasure positions."""

        positions = tuple(erasure_positions)
        if any(not isinstance(position, int) for position in positions):
            raise ErrorCorrectionError("erasure positions must be integers")
        if any(position < 0 or position >= codeword_length for position in positions):
            raise ErrorCorrectionError("erasure position is outside the codeword")
        if len(set(positions)) != len(positions):
            raise ErrorCorrectionError("erasure positions must not repeat")
        return tuple(sorted(positions))
