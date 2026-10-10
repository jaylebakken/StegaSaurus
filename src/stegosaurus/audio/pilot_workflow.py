"""Orchestrate pilot embedding, offset scanning, and detector-only extraction.

This mixin is the readable process map for the spectral pilot:

    PCM -> STFT -> keyed pair modulation -> inverse STFT -> watermarked PCM
    received PCM -> STFT -> offset candidates -> soft frame bits -> detector

It deliberately handles statistical detection only. Reed--Solomon attribution
transport is a separate experimental layer and is not exposed as a production
waveform encoder or decoder here.
"""

from __future__ import annotations

from datetime import date, datetime
import hashlib
import hmac

import numpy as np

from .pilot_types import (
    AudioSamples,
    PcmAudio,
    SpectralPilotConfig,
    SpectralPilotEmbedding,
    SpectralPilotExtraction,
)
from .schema import AudioWatermarkConfig, AudioWatermarkSchema


class SpectralPilotWorkflow:
    """Coordinate the high-level detector-pilot flow over reusable spectral helpers."""

    def __init__(
        self,
        master_secret: bytes,
        config: SpectralPilotConfig | None = None,
        schema_config: AudioWatermarkConfig | None = None,
    ) -> None:
        """Initialize domain-separated carrier selection and audio detection schema state."""

        if not master_secret:
            raise ValueError("master_secret must not be empty")
        self._carrier_secret = hmac.new(
            bytes(master_secret),
            b"stegosaurus-spectral-audio-pilot-v1",
            hashlib.sha256,
        ).digest()
        self._config = config or SpectralPilotConfig()
        self._schema = AudioWatermarkSchema(bytes(master_secret), schema_config)

    @property
    def schema(self) -> AudioWatermarkSchema:
        """Return the keyed statistical detector and attribution schema used by this pilot."""

        return self._schema

    def embed(self, audio: PcmAudio, epoch: date | datetime | str) -> SpectralPilotEmbedding:
        """Embed repeated keyed pilot evidence into suitable spectral frames of mono audio."""

        frequencies, spectrum = self._stft(audio)
        expected_bits = self._schema.detection_bits(spectrum.shape[1], epoch)
        lower_bin, upper_bin = self._frequency_bin_range(frequencies)
        embedded_frame_count = 0
        skipped_frame_count = 0
        for frame_index, expected_bit in enumerate(expected_bits):
            if self._embed_frame(spectrum[:, frame_index], expected_bit, lower_bin, upper_bin, frame_index):
                embedded_frame_count += 1
            else:
                skipped_frame_count += 1
        encoded_samples = self._inverse_stft(spectrum, audio)
        noise_samples = encoded_samples - audio.samples
        return SpectralPilotEmbedding(
            PcmAudio(encoded_samples, audio.sample_rate),
            expected_bits,
            embedded_frame_count,
            skipped_frame_count,
            self._signal_to_noise_db(audio.samples, noise_samples),
        )

    def extract(self, audio: PcmAudio, epoch: date | datetime | str) -> SpectralPilotExtraction:
        """Synchronize keyed carriers and extract frame bits before statistical detection."""

        frequencies, spectrum = self._stft(audio)
        lower_bin, upper_bin = self._frequency_bin_range(frequencies)
        candidate_count = self._config.maximum_sync_offset_frames + 1
        offset_results = []
        for frame_offset in range(candidate_count):
            observed_bits, frame_confidences = self._observations_for_offset(
                spectrum, lower_bin, upper_bin, frame_offset
            )
            detection = self._schema.detect(
                observed_bits, epoch, frame_offset, candidate_count
            )
            offset_results.append((frame_offset, observed_bits, frame_confidences, detection))
        frame_offset, observed_bits, frame_confidences, detection = min(
            offset_results,
            key=lambda candidate: candidate[3].tail_probability,
        )
        return SpectralPilotExtraction(
            observed_bits,
            frame_confidences,
            frame_offset,
            candidate_count,
            detection,
        )


    def _observations_for_offset(
        self,
        spectrum: AudioSamples,
        lower_bin: int,
        upper_bin: int,
        frame_offset: int,
    ) -> tuple[tuple[int | None, ...], tuple[float | None, ...]]:
        """Extract observations using carrier pairs keyed to one source-frame offset."""

        observed_bits: list[int | None] = []
        frame_confidences: list[float | None] = []
        for observed_frame_index in range(spectrum.shape[1]):
            observed_bit, confidence = self._extract_frame(
                spectrum[:, observed_frame_index],
                lower_bin,
                upper_bin,
                observed_frame_index + frame_offset,
            )
            observed_bits.append(observed_bit)
            frame_confidences.append(confidence)
        return tuple(observed_bits), tuple(frame_confidences)
