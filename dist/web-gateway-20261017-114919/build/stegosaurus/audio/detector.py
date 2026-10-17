"""Provide the directional PCM-to-presence-decision entry point.

Pseudocode:
    received PCM + shared secret + epoch
      -> STFT soft frame observations over bounded offsets
      -> expected keyed detector bits
      -> corrected statistical decision: verified | inconclusive | absent

``SpectralAudioDetector`` is read-only. It neither changes the received audio
nor recovers a production attribution token; attribution transport remains a
separate experimental decoding path.
"""

from __future__ import annotations

from datetime import date, datetime

from .pilot import PcmAudio, SpectralAudioPilot, SpectralPilotConfig, SpectralPilotExtraction
from .schema import AudioWatermarkConfig, AudioWatermarkSchema


class SpectralAudioDetector:
    """Detect an epoch-keyed statistical pilot in a PCM audio waveform."""

    def __init__(
        self,
        master_secret: bytes,
        config: SpectralPilotConfig | None = None,
        schema_config: AudioWatermarkConfig | None = None,
    ) -> None:
        """Initialize deterministic spectral detection with one shared secret and configuration."""

        self._pilot = SpectralAudioPilot(master_secret, config, schema_config)

    @property
    def schema(self) -> AudioWatermarkSchema:
        """Return the keyed schema used to score this detector's frame observations."""

        return self._pilot.schema

    def detect(self, audio: PcmAudio, epoch: date | datetime | str) -> SpectralPilotExtraction:
        """Extract frame evidence and return the best synchronized detection decision."""

        return self._pilot.extract(audio, epoch)
