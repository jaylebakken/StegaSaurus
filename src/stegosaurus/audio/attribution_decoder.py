"""Provide the directional claimed-handle attribution verifier.

Unlike detector presence scoring, this decoder requires the private
``AttributionRecord`` retained during encoding. A caller first resolves a
claimed handle in its authenticated registry, retrieves the record, then calls
``verify``. This v1 interface intentionally does not claim blind discovery.
"""

from __future__ import annotations

from .attribution_models import AttributionRecord, AttributionVerification, SpectralAttributionConfig
from .attribution_repetition import FourReplicaAttributionCodec
from .pilot import PcmAudio, SpectralAudioPilot, SpectralPilotConfig
from .schema import AudioWatermarkConfig


class SpectralAttributionDecoder:
    """Verify a supplied handle claim from retained carrier maps and received PCM evidence."""

    def __init__(self, master_secret: bytes, config: SpectralAttributionConfig | None = None) -> None:
        """Initialize the same frozen v1 profile required by the matching attribution encoder."""

        self._config = config or SpectralAttributionConfig()
        pilot = SpectralAudioPilot(
            master_secret,
            SpectralPilotConfig(
                minimum_frequency_hz=self._config.minimum_frequency_hz,
                maximum_frequency_hz=self._config.maximum_frequency_hz,
                relative_difference=self._config.relative_difference,
            ),
            AudioWatermarkConfig(
                attribution_token_bytes=self._config.handle_bytes,
                parity_symbols=self._config.parity_symbols,
            ),
        )
        self._codec = FourReplicaAttributionCodec(pilot, self._config.minimum_combined_confidence)

    @property
    def config(self) -> SpectralAttributionConfig:
        """Return the immutable v1 profile used for this decoder."""

        return self._config

    def verify(self, audio: PcmAudio, record: AttributionRecord) -> AttributionVerification:
        """Verify the record's claimed handle against received PCM without attempting blind map reconstruction."""

        return self._codec.verify(audio, record)
