"""Expose the detector-only spectral pilot in research reading order.

Start with this process map, then open the named modules for each step:

    PCM/WAV (`pilot_types`)
      -> STFT and frequency range (`pilot_transform`)
      -> keyed bin pairs (`pilot_pairs`)
      -> frame modulation and confidence (`pilot_frames`)
      -> offset scan and statistical decision (`pilot_workflow`)

Toy example:
    pilot = SpectralAudioPilot(b"secret")
    embedded = pilot.embed(audio, "2026-10-09")
    decision = pilot.extract(embedded.audio, "2026-10-09").detection

The API implements an experimental detector pilot. It does not expose a
production attribution-token waveform encoder or decoder, and it makes no
claim of universal compression, DSP, or perceptual robustness.
"""

from .pilot_frames import SpectralFrameCarrierMixin
from .pilot_pairs import SpectralPairMixin
from .pilot_transform import SpectralTransformMixin
from .pilot_types import (
    AudioSamples,
    PcmAudio,
    SpectralPilotConfig,
    SpectralPilotEmbedding,
    SpectralPilotExtraction,
    read_pcm16_wav,
    write_pcm16_wav,
)
from .pilot_workflow import SpectralPilotWorkflow


class SpectralAudioPilot(
    SpectralPilotWorkflow,
    SpectralFrameCarrierMixin,
    SpectralTransformMixin,
    SpectralPairMixin,
):
    """Compose the documented spectral helpers into the legacy-compatible pilot API."""


__all__ = [
    "AudioSamples",
    "PcmAudio",
    "SpectralAudioPilot",
    "SpectralPilotConfig",
    "SpectralPilotEmbedding",
    "SpectralPilotExtraction",
    "read_pcm16_wav",
    "write_pcm16_wav",
]
