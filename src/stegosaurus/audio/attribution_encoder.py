"""Provide the directional PCM-to-claimed-handle attribution encoder.

The encoder uses the fixed v1 profile selected by iteration 020: a four-byte
external registry handle, sixteen Reed--Solomon parity symbols, four replica
spans, and the `500-3800 Hz` spectral band. It returns the audio plus a private
verification record that the registry must retain. The record is not embedded
metadata and must not be published with the audio.
"""

from __future__ import annotations

from .attribution_models import AttributionEmbedding, SpectralAttributionConfig
from .attribution_repetition import FourReplicaAttributionCodec
from .attribution_registry import InMemoryAttributionRegistry, RegistryEntry
from .pilot import PcmAudio, SpectralAudioPilot, SpectralPilotConfig
from .schema import AudioWatermarkConfig


class SpectralAttributionEncoder:
    """Embed a fixed-size opaque registry handle into four retained spectral carrier maps."""

    def __init__(self, master_secret: bytes, config: SpectralAttributionConfig | None = None) -> None:
        """Initialize the frozen v1 spectral and Reed--Solomon attribution profile."""

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
        """Return the immutable v1 profile used for this encoder."""

        return self._config

    def encode(self, audio: PcmAudio, handle: bytes) -> AttributionEmbedding:
        """Embed one issued four-byte handle and return audio plus its private verification record."""

        return self._codec.embed(audio, handle)

    def issue_and_encode(
        self,
        audio: PcmAudio,
        registry: InMemoryAttributionRegistry,
        provenance: bytes,
        maximum_attempts: int = 32,
    ) -> tuple[RegistryEntry, AttributionEmbedding]:
        """Issue, self-verify, and retain a handle record, reissuing candidate handle bits when calibration fails."""

        if not isinstance(registry, InMemoryAttributionRegistry):
            raise TypeError("registry must be an InMemoryAttributionRegistry")
        if isinstance(maximum_attempts, bool) or not isinstance(maximum_attempts, int) or maximum_attempts < 1:
            raise ValueError("maximum_attempts must be a positive integer")
        for _ in range(maximum_attempts):
            entry = registry.issue(provenance)
            embedding = self.encode(audio, entry.handle)
            verification = self._codec.verify(embedding.audio, embedding.record)
            if verification.recovered:
                registry.retain_record(embedding.record)
                return entry, embedding
            registry.discard(entry.handle)
        raise RuntimeError("could not issue a handle that passes clean v1 attribution calibration")
