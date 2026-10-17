"""Provide the directional PCM-to-watermarked-PCM entry point.

Pseudocode:
    shared secret + daily epoch + PCM
      -> expected detector bits
      -> secret STFT-pair modulation
      -> watermarked PCM plus coverage and SNR diagnostics

``SpectralAudioEncoder`` is intentionally detector-pilot-only: it does not
write an attribution handle into a production waveform API. The returned SNR is
a measurement of this synthetic fixture, not an imperceptibility certification.
"""

from __future__ import annotations

from datetime import date, datetime

from .pilot import PcmAudio, SpectralAudioPilot, SpectralPilotConfig, SpectralPilotEmbedding
from .schema import AudioWatermarkConfig, AudioWatermarkSchema


class SpectralAudioEncoder:
    """Encode an epoch-keyed statistical pilot into a PCM audio waveform."""

    def __init__(
        self,
        master_secret: bytes,
        config: SpectralPilotConfig | None = None,
        schema_config: AudioWatermarkConfig | None = None,
    ) -> None:
        """Initialize deterministic spectral encoding with one shared secret and configuration."""

        self._pilot = SpectralAudioPilot(master_secret, config, schema_config)

    @property
    def schema(self) -> AudioWatermarkSchema:
        """Return the keyed schema used to derive this encoder's daily pilot bits."""

        return self._pilot.schema

    def encode(self, audio: PcmAudio, epoch: date | datetime | str) -> SpectralPilotEmbedding:
        """Embed the epoch-keyed pilot in suitable STFT frames of the supplied audio."""

        return self._pilot.embed(audio, epoch)
