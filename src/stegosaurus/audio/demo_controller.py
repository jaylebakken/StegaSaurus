"""Provide UI-independent orchestration for the manual attribution lab.

Tkinter only renders state; this controller owns the reproducible process map
used by the buttons:

    sample/WAV -> issue or register a claim -> encode -> named transforms
        -> resolve retained record -> verify that one supplied claim

It intentionally preserves the v1 boundary: verification needs a retained
private carrier map and is not blind discovery. Named transforms are manual
test cases, not assertions of robustness.
"""

from __future__ import annotations

from dataclasses import dataclass

from .attack_codec import mp3_round_trip
from .attack_signal import add_white_noise, low_pass_filter, normalize_peak, resample_audio, trim_audio
from .attribution import (
    AttributionEmbedding,
    AttributionVerification,
    InMemoryAttributionRegistry,
    SpectralAttributionDecoder,
    SpectralAttributionEncoder,
)
from .demo_samples import music_like_sample, speech_like_sample
from .pilot import PcmAudio, read_pcm16_wav


DISTORTION_NAMES = (
    "Normalize peak (0.85)",
    "White noise (30 dB)",
    "Low-pass filter (4 kHz)",
    "MP3 round trip (96 kbps)",
    "Resample 12 kHz round trip",
    "Leading crop (250 ms)",
)


@dataclass(frozen=True, slots=True)
class DemoState:
    """Expose concise lab state for a UI, CLI, or test without Tkinter coupling."""

    source_name: str
    source_audio: PcmAudio
    current_audio: PcmAudio
    active_handle: bytes | None
    embedding_signal_to_noise_db: float | None
    applied_distortions: tuple[str, ...]


class AttributionDemoController:
    """Coordinate local registry claims, fixture selection, named transforms, and verification."""

    def __init__(self, master_secret: bytes = b"stegosaurus-demo-master-secret") -> None:
        """Initialize an isolated local lab with deterministic fixture audio and private registry state."""

        self._registry = InMemoryAttributionRegistry(b"stegosaurus-demo-registry-secret")
        self._encoder = SpectralAttributionEncoder(master_secret)
        self._decoder = SpectralAttributionDecoder(master_secret)
        self._source_name = "Music-like sample"
        self._source_audio = music_like_sample()
        self._current_audio = self._source_audio
        self._encoded_audio: PcmAudio | None = None
        self._active_handle: bytes | None = None
        self._embedding_signal_to_noise_db: float | None = None
        self._applied_distortions: tuple[str, ...] = ()

    @property
    def state(self) -> DemoState:
        """Return a snapshot of the source, current audio, active claim, and named transforms."""

        return DemoState(
            self._source_name,
            self._source_audio,
            self._current_audio,
            self._active_handle,
            self._embedding_signal_to_noise_db,
            self._applied_distortions,
        )

    def select_sample(self, sample_name: str) -> DemoState:
        """Select a named built-in sample and clear any existing local attribution claim."""

        samples = {"Music-like sample": music_like_sample, "Speech-like sample": speech_like_sample}
        try:
            audio_factory = samples[sample_name]
        except KeyError as error:
            raise ValueError(f"unknown sample: {sample_name}") from error
        self._set_source(sample_name, audio_factory())
        return self.state

    def load_wav(self, path: str) -> DemoState:
        """Load a PCM16 WAV as a new source and clear existing local attribution state."""

        self._set_source(path, read_pcm16_wav(path))
        return self.state

    def issue_and_encode(self, provenance: str) -> AttributionEmbedding:
        """Issue a calibrated local handle, embed it, and retain its private verification record."""

        entry, embedding = self._encoder.issue_and_encode(
            self._source_audio,
            self._registry,
            _provenance_bytes(provenance),
        )
        self._activate_embedding(entry.handle, embedding)
        return embedding

    def encode_supplied_handle(self, handle_hex: str, provenance: str) -> tuple[AttributionEmbedding, AttributionVerification]:
        """Register and embed a supplied handle, returning its immediate clean verification result."""

        handle = _parse_handle(handle_hex)
        self._registry.register(handle, _provenance_bytes(provenance))
        embedding = self._encoder.encode(self._source_audio, handle)
        self._registry.retain_record(embedding.record)
        self._activate_embedding(handle, embedding)
        return embedding, self.verify()

    def apply_distortions(self, selected_names: tuple[str, ...]) -> DemoState:
        """Apply selected named transformations in displayed order, always starting from encoded base audio."""

        unknown_names = set(selected_names).difference(DISTORTION_NAMES)
        if unknown_names:
            raise ValueError(f"unknown distortions: {', '.join(sorted(unknown_names))}")
        transformed = self._base_audio()
        for name in DISTORTION_NAMES:
            if name in selected_names:
                transformed = _apply_distortion(transformed, name)
        self._current_audio = transformed
        self._applied_distortions = tuple(name for name in DISTORTION_NAMES if name in selected_names)
        return self.state

    def reset_current_audio(self) -> DemoState:
        """Restore the clean encoded audio when present, otherwise restore the selected source."""

        self._current_audio = self._base_audio()
        self._applied_distortions = ()
        return self.state

    def verify(self) -> AttributionVerification:
        """Verify the active claimed handle through its local registry-retained private carrier map."""

        if self._active_handle is None:
            raise ValueError("encode audio before verifying an attribution claim")
        record = self._registry.record_for(self._active_handle)
        if record is None:
            raise RuntimeError("active handle has no retained private verification record")
        return self._decoder.verify(self._current_audio, record)

    def _set_source(self, source_name: str, audio: PcmAudio) -> None:
        """Replace the selected source and reset transient state that belongs to its prior waveform."""

        self._source_name = source_name
        self._source_audio = audio
        self._current_audio = audio
        self._encoded_audio = None
        self._active_handle = None
        self._embedding_signal_to_noise_db = None
        self._applied_distortions = ()

    def _activate_embedding(self, handle: bytes, embedding: AttributionEmbedding) -> None:
        """Make a completed embedding the clean base audio for later manual transformations."""

        self._active_handle = handle
        self._encoded_audio = embedding.audio
        self._current_audio = embedding.audio
        self._embedding_signal_to_noise_db = embedding.signal_to_noise_db
        self._applied_distortions = ()

    def _base_audio(self) -> PcmAudio:
        """Return the clean encoded waveform when available or the current source before encoding."""

        return self._source_audio if self._encoded_audio is None else self._encoded_audio


def _parse_handle(handle_hex: str) -> bytes:
    """Parse exactly eight hexadecimal characters into the v1 four-byte registry handle."""

    normalized = handle_hex.strip()
    if len(normalized) != 8:
        raise ValueError("registry handle must contain exactly 8 hexadecimal characters")
    try:
        return bytes.fromhex(normalized)
    except ValueError as error:
        raise ValueError("registry handle must contain only hexadecimal characters") from error


def _provenance_bytes(provenance: str) -> bytes:
    """Validate non-empty local provenance text and encode it for the authenticated in-memory registry."""

    normalized = provenance.strip()
    if not normalized:
        raise ValueError("provenance must not be empty")
    return normalized.encode("utf-8")


def _apply_distortion(audio: PcmAudio, name: str) -> PcmAudio:
    """Apply one visible manual-test transformation using fixed, replayable parameters."""

    if name == "Normalize peak (0.85)":
        return normalize_peak(audio, 0.85)
    if name == "White noise (30 dB)":
        return add_white_noise(audio, 30.0, seed=20261009)
    if name == "Low-pass filter (4 kHz)":
        return low_pass_filter(audio, 4000.0)
    if name == "MP3 round trip (96 kbps)":
        return mp3_round_trip(audio, 96)
    if name == "Resample 12 kHz round trip":
        return resample_audio(resample_audio(audio, 12000), audio.sample_rate)
    if name == "Leading crop (250 ms)":
        return trim_audio(audio, 0.25, audio.duration_seconds)
    raise ValueError(f"unknown distortion: {name}")
