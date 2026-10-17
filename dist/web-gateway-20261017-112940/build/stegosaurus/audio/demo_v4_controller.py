"""Provide UI-independent orchestration for the V4 known-song demo.

This controller wraps the product ``KnownSongAttributionWorkflow`` for the
Tkinter demo. It demonstrates the measured clean-file workflow:

    current source -> register song -> create recipient exports
        -> make a clean suspicious excerpt -> identify the matching export

The robust mode demonstrates named synthetic crop-plus-distortion tests measured
in the experiment suite. It does not claim recorded, compressed, or unknown-song
attribution beyond those named checks.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from .attacks import add_reverberation, add_white_noise, low_pass_filter, normalize_peak, resample_audio
from .attribution_workflow import KnownSongAttributionWorkflow, KnownSongVerification
from .pilot import PcmAudio


@dataclass(frozen=True, slots=True)
class V4DemoState:
    """Expose the known-song attribution demo state."""

    song_id: str | None
    profile_name: str
    export_count: int
    suspicious_excerpt_ready: bool
    last_verification: KnownSongVerification | None


class V4DemoController:
    """Coordinate the known-song clean excerpt attribution demo."""

    def __init__(self, source_audio: PcmAudio, master_secret: bytes) -> None:
        """Initialize a V4 workflow around the selected source audio."""

        self._source_audio = source_audio
        self._workflow = KnownSongAttributionWorkflow(master_secret)
        self._song_id: str | None = None
        self._profile_name = "clean"
        self._exports: tuple[tuple[object, PcmAudio], ...] = ()
        self._suspicious_excerpt: PcmAudio | None = None
        self._verification: KnownSongVerification | None = None

    @property
    def state(self) -> V4DemoState:
        """Return current V4 demo state."""

        return V4DemoState(self._song_id, self._profile_name, len(self._exports), self._suspicious_excerpt is not None, self._verification)

    @property
    def suspicious_excerpt(self) -> PcmAudio | None:
        """Return the prepared suspicious excerpt when present."""

        return self._suspicious_excerpt

    def reset_source(self, source_audio: PcmAudio) -> V4DemoState:
        """Replace the source audio and clear V4 registry state."""

        self._source_audio = source_audio
        self._workflow = KnownSongAttributionWorkflow()
        self._song_id = None
        self._profile_name = "clean"
        self._exports = ()
        self._suspicious_excerpt = None
        self._verification = None
        return self.state

    def register_current_song(self, title: str = "V4 demo song") -> V4DemoState:
        """Register the selected source audio as a known-song catalog entry."""

        song = self._workflow.register_song(title, self._source_audio)
        self._profile_name = "clean"
        self._activate_song(song.song_id)
        return self.state

    def register_robust_song(self, title: str = "V4 robust demo song") -> V4DemoState:
        """Register the selected source audio with the robust 15-second profile."""

        song = self._workflow.register_robust_song(title, self._source_audio)
        self._profile_name = "robust"
        self._activate_song(song.song_id)
        return self.state

    def _activate_song(self, song_id: str) -> None:
        """Make one registered song the active demo catalog entry."""

        self._song_id = song_id
        self._exports = ()
        self._suspicious_excerpt = None
        self._verification = None

    def _ensure_song(self) -> None:
        """Register a song for the active demo profile when needed."""

        if self._song_id is not None:
            return
        if self._profile_name == "robust":
            self.register_robust_song()
        else:
            self.register_current_song()

    def generate_demo_exports(self, count: int = 3) -> V4DemoState:
        """Generate recipient/export copies for the registered song."""

        self._ensure_song()
        self._exports = tuple(
            self._workflow.create_export(self._song_id or "", f"export_{index:02d}", (0xB1000000 + index).to_bytes(4, "big"))
            for index in range(count)
        )
        self._suspicious_excerpt = None
        self._verification = None
        return self.state

    def make_demo_leak(self, export_index: int = 1, start_seconds: float = 37.25, duration_seconds: float = 90.0) -> PcmAudio:
        """Create a clean suspicious excerpt from one generated export."""

        audio = self._visible_export(export_index)
        self._suspicious_excerpt = self._crop_export(audio, start_seconds, duration_seconds)
        return self._suspicious_excerpt

    def make_robust_proxy_leak(self, export_index: int = 1, start_seconds: float = 37.25, duration_seconds: float = 90.0) -> PcmAudio:
        """Create a cropped light recorded-proxy leak from one generated export."""

        self._suspicious_excerpt = self._light_recorded_proxy(self.make_demo_leak(export_index, start_seconds, duration_seconds))
        return self._suspicious_excerpt

    def _visible_export(self, export_index: int) -> PcmAudio:
        """Return one generated export audio by index, creating exports if needed."""

        if not self._exports:
            self.generate_demo_exports()
        _, audio = self._exports[export_index]
        return audio

    def _crop_export(self, audio: PcmAudio, start_seconds: float, duration_seconds: float) -> PcmAudio:
        """Create a copied suspicious excerpt from an export waveform."""

        start = int(round(start_seconds * audio.sample_rate))
        count = int(round(duration_seconds * audio.sample_rate))
        return PcmAudio(np.array(audio.samples[start : start + count], copy=True), audio.sample_rate)

    def _light_recorded_proxy(self, audio: PcmAudio) -> PcmAudio:
        """Apply the measured light recorded-proxy demo transform."""

        transformed = resample_audio(resample_audio(audio, 12000), audio.sample_rate)
        transformed = low_pass_filter(transformed, 3800.0)
        transformed = add_reverberation(transformed, 0.080, 0.10, seed=20261011)
        transformed = add_white_noise(transformed, 35.0, seed=20261011)
        return normalize_peak(transformed, 0.85)

    def verify_demo_leak(self) -> KnownSongVerification:
        """Verify the prepared clean suspicious excerpt against registered exports."""

        if self._song_id is None:
            raise ValueError("register a V4 song before verification")
        if self._suspicious_excerpt is None:
            raise ValueError("create a suspicious excerpt before verification")
        if self._profile_name == "robust":
            self._verification = self._workflow.verify_excerpt_with_fallbacks(self._song_id, self._suspicious_excerpt)
        else:
            self._verification = self._workflow.verify_excerpt(self._song_id, self._suspicious_excerpt)
        return self._verification
