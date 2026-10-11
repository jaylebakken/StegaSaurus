"""Provide UI-independent orchestration for the manual attribution lab.

Tkinter only renders state; this controller owns the reproducible process map
used by the buttons:

    sample/WAV -> issue or register a claim -> encode repeated blocks
        -> named transforms -> verify with block votes and pooled evidence

It intentionally preserves the retained-record boundary: verification needs
private carrier evidence retained during embedding and is not arbitrary discovery.
Named transforms are manual test cases, not assertions of robustness.
"""

from __future__ import annotations

from dataclasses import dataclass

from .attribution import (
    BlockAttributionCodec,
    BlockAttributionEmbedding,
    BlockAttributionRecord,
    BlockAttributionVerification,
    InMemoryAttributionRegistry,
    RepeatedBlockWaterfallDecision,
    RepeatedBlockWaterfallPolicy,
)
from .demo_samples import music_like_sample, speech_like_sample
from .demo_transforms import DISTORTION_NAMES, apply_demo_distortion
from .demo_v4_controller import V4DemoController
from .pilot import PcmAudio, read_pcm16_wav


DEMO_BLOCK_DURATION_SECONDS = 150


@dataclass(frozen=True, slots=True)
class DemoState:
    """Expose concise lab state for a UI, CLI, or test without Tkinter coupling."""

    source_name: str
    source_audio: PcmAudio
    current_audio: PcmAudio
    active_handle: bytes | None
    block_count: int
    embedding_signal_to_noise_db: float | None
    applied_distortions: tuple[str, ...]


class AttributionDemoController:
    """Coordinate local registry claims, fixture selection, named transforms, and verification."""

    def __init__(self, master_secret: bytes = b"stegosaurus-demo-master-secret") -> None:
        """Initialize an isolated local lab with deterministic fixture audio and private registry state."""

        self._registry = InMemoryAttributionRegistry(b"stegosaurus-demo-registry-secret")
        self._block_codec = BlockAttributionCodec(master_secret)
        self._waterfall_policy = RepeatedBlockWaterfallPolicy()
        self._source_name = "Music-like sample"
        self._source_audio = music_like_sample(DEMO_BLOCK_DURATION_SECONDS)
        self._current_audio = self._source_audio
        self._encoded_audio: PcmAudio | None = None
        self._active_handle: bytes | None = None
        self._active_block_record: BlockAttributionRecord | None = None
        self._embedding_signal_to_noise_db: float | None = None
        self._applied_distortions: tuple[str, ...] = ()
        self.v4 = V4DemoController(self._source_audio, master_secret)

    @property
    def state(self) -> DemoState:
        """Return a snapshot of the source, current audio, active claim, and named transforms."""

        return DemoState(
            self._source_name,
            self._source_audio,
            self._current_audio,
            self._active_handle,
            0 if self._active_block_record is None else len(self._active_block_record.block_records),
            self._embedding_signal_to_noise_db,
            self._applied_distortions,
        )

    def select_sample(self, sample_name: str) -> DemoState:
        """Select a named built-in sample and clear any existing local attribution claim."""

        samples = {
            "Music-like sample": lambda: music_like_sample(DEMO_BLOCK_DURATION_SECONDS),
            "Speech-like sample": lambda: speech_like_sample(DEMO_BLOCK_DURATION_SECONDS),
        }
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

    def issue_and_encode_blocks(self, provenance: str, maximum_attempts: int = 32) -> BlockAttributionEmbedding:
        """Issue a local handle and embed it into repeated complete attribution blocks."""

        if isinstance(maximum_attempts, bool) or not isinstance(maximum_attempts, int) or maximum_attempts < 1:
            raise ValueError("maximum_attempts must be a positive integer")
        provenance_bytes = _provenance_bytes(provenance)
        for _ in range(maximum_attempts):
            entry = self._registry.issue(provenance_bytes)
            embedding = self._block_codec.embed(self._source_audio, entry.handle)
            if self._block_codec.verify(embedding.audio, embedding.record).recovered:
                self._activate_block_embedding(entry.handle, embedding)
                return embedding
            self._registry.discard(entry.handle)
        raise RuntimeError("could not issue a handle that passes clean block attribution calibration")

    def encode_supplied_handle_blocks(
        self,
        handle_hex: str,
        provenance: str,
    ) -> tuple[BlockAttributionEmbedding, tuple[BlockAttributionVerification, RepeatedBlockWaterfallDecision]]:
        """Register and embed a supplied handle into repeated attribution blocks."""

        handle = _parse_handle(handle_hex)
        self._registry.register(handle, _provenance_bytes(provenance))
        embedding = self._block_codec.embed(self._source_audio, handle)
        self._activate_block_embedding(handle, embedding)
        return embedding, self.verify()

    def apply_distortions(self, selected_names: tuple[str, ...]) -> DemoState:
        """Apply selected named transformations in displayed order, always starting from encoded base audio."""

        unknown_names = set(selected_names).difference(DISTORTION_NAMES)
        if unknown_names:
            raise ValueError(f"unknown distortions: {', '.join(sorted(unknown_names))}")
        transformed = self._base_audio()
        for name in DISTORTION_NAMES:
            if name in selected_names:
                transformed = apply_demo_distortion(transformed, name)
        self._current_audio = transformed
        self._applied_distortions = tuple(name for name in DISTORTION_NAMES if name in selected_names)
        return self.state

    def reset_current_audio(self) -> DemoState:
        """Restore the clean encoded audio when present, otherwise restore the selected source."""

        self._current_audio = self._base_audio()
        self._applied_distortions = ()
        return self.state

    def verify(self) -> tuple[BlockAttributionVerification, RepeatedBlockWaterfallDecision]:
        """Verify the active claim through block-vote and pooled-evidence gates."""

        if self._active_handle is None:
            raise ValueError("encode audio before verifying an attribution claim")
        if self._active_block_record is None:
            raise RuntimeError("active handle has no retained block verification record")
        verification = self._block_codec.verify(self._current_audio, self._active_block_record)
        return verification, self._waterfall_policy.decide(verification)

    def _set_source(self, source_name: str, audio: PcmAudio) -> None:
        """Replace the selected source and reset transient state that belongs to its prior waveform."""

        self._source_name = source_name
        self._source_audio = audio
        self._current_audio = audio
        self._encoded_audio = None
        self._active_handle = None
        self._active_block_record = None
        self._embedding_signal_to_noise_db = None
        self._applied_distortions = ()
        self.v4.reset_source(audio)

    def _activate_block_embedding(self, handle: bytes, embedding: BlockAttributionEmbedding) -> None:
        """Make a repeated-block embedding the clean base audio for manual transformations."""

        self._active_handle = handle
        self._active_block_record = embedding.record
        self._encoded_audio = embedding.audio
        self._current_audio = embedding.audio
        self._embedding_signal_to_noise_db = min(embedding.block_signal_to_noise_db)
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


