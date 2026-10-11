"""Render a compact green Tkinter lab for repeated-block attribution experiments.

The app is intentionally a display and control surface rather than a second
watermark implementation. Its controller performs the documented process:

    choose synthetic/WAV cover -> encode repeated blocks
        -> play or transform audio -> verify block votes or pooled evidence

The visible named transformations are manual test inputs. They do not make a
robustness, imperceptibility, compression, or blind-discovery claim.
"""

from __future__ import annotations

import tempfile
import tkinter as tk
import winsound
from collections.abc import Callable
from pathlib import Path
from tkinter import filedialog, ttk

from .demo_app_format import describe_result
from .demo_controller import AttributionDemoController, DISTORTION_NAMES
from .demo_waveform import draw_waveform
from .pilot import write_pcm16_wav


class AttributionDemoApp:
    """Present controller state, local claim controls, transform toggles, and a waveform canvas."""

    def __init__(self, root: tk.Tk) -> None:
        """Build the green themed widgets and render the controller's initial synthetic sample."""

        self._root = root
        self._controller = AttributionDemoController()
        self._sample_name = tk.StringVar(value="Music-like sample")
        self._handle = tk.StringVar()
        self._provenance = tk.StringVar(value="manual local test")
        self._distortions = {name: tk.BooleanVar() for name in DISTORTION_NAMES}
        self._status = tk.StringVar(value="Choose a sample, then issue repeated blocks or provide 8 hex digits.")
        self._details = tk.StringVar()
        self._playback_path: Path | None = None
        self._configure_theme()
        self._build()
        self._refresh()

    def _configure_theme(self) -> None:
        """Configure a restrained dark green ttk palette without requiring external theme assets."""

        self._root.title("Stegosaurus Block Waterfall Attribution Lab")
        self._root.configure(background="#0b2417")
        style = ttk.Style(self._root)
        style.theme_use("clam")
        style.configure("TFrame", background="#0b2417")
        style.configure("TLabel", background="#0b2417", foreground="#e8f5e9")
        style.configure("TCheckbutton", background="#0b2417", foreground="#e8f5e9")
        style.configure("TButton", background="#2e8b57", foreground="#ffffff", padding=7)
        style.map("TButton", background=[("active", "#4caf50")])
        style.configure("TEntry", fieldbackground="#153d27", foreground="#e8f5e9")
        style.configure("TCombobox", fieldbackground="#153d27", foreground="#e8f5e9")

    def _build(self) -> None:
        """Lay out sample, claim, distortion, action, diagnostic, and waveform widgets."""

        frame = ttk.Frame(self._root, padding=14)
        frame.grid(sticky="nsew")
        self._root.columnconfigure(0, weight=1)
        self._root.rowconfigure(0, weight=1)
        frame.columnconfigure(1, weight=1)
        ttk.Label(frame, text="Source").grid(row=0, column=0, sticky="w")
        selector = ttk.Combobox(frame, textvariable=self._sample_name, values=("Music-like sample", "Speech-like sample"), state="readonly")
        selector.grid(row=0, column=1, sticky="ew", padx=6)
        selector.bind("<<ComboboxSelected>>", self._select_sample)
        ttk.Button(frame, text="Load WAV…", command=self._load_wav).grid(row=0, column=2, sticky="ew")
        ttk.Label(frame, text="Registry handle").grid(row=1, column=0, sticky="w", pady=(10, 0))
        ttk.Entry(frame, textvariable=self._handle).grid(row=1, column=1, columnspan=2, sticky="ew", padx=6, pady=(10, 0))
        ttk.Label(frame, text="Provenance").grid(row=2, column=0, sticky="w", pady=(6, 0))
        ttk.Entry(frame, textvariable=self._provenance).grid(row=2, column=1, columnspan=2, sticky="ew", padx=6, pady=(6, 0))
        controls = ttk.Frame(frame)
        controls.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        ttk.Button(controls, text="Issue Blocks", command=self._issue_blocks).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(controls, text="Encode Supplied", command=self._encode_supplied_blocks).grid(row=0, column=1, padx=6)
        ttk.Button(controls, text="Verify Waterfall", command=self._verify).grid(row=0, column=2, padx=6)
        ttk.Button(controls, text="Play Current WAV", command=self._play_current).grid(row=1, column=0, padx=(0, 6), pady=(6, 0))
        ttk.Button(controls, text="Stop Playback", command=self._stop_playback).grid(row=1, column=1, padx=6, pady=(6, 0))
        ttk.Button(controls, text="Save Current WAV", command=self._save_wav).grid(row=1, column=2, padx=6, pady=(6, 0))
        v4 = ttk.LabelFrame(frame, text="V4 Known-Song Leak Demo", padding=8)
        v4.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        ttk.Button(v4, text="Register Song", command=self._v4_register_song).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(v4, text="Register Robust", command=self._v4_register_robust_song).grid(row=0, column=1, padx=6)
        ttk.Button(v4, text="Generate Exports", command=self._v4_generate_exports).grid(row=0, column=2, padx=6)
        ttk.Button(v4, text="Make Clean Leak", command=self._v4_make_leak).grid(row=0, column=3, padx=6)
        ttk.Button(v4, text="Make Proxy Leak", command=self._v4_make_proxy_leak).grid(row=1, column=0, padx=(0, 6), pady=(6, 0))
        ttk.Button(v4, text="Verify Leak", command=self._v4_verify_leak).grid(row=1, column=1, padx=6, pady=(6, 0))
        distortions = ttk.LabelFrame(frame, text="Named Manual Transformations", padding=8)
        distortions.grid(row=5, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        for index, name in enumerate(DISTORTION_NAMES):
            ttk.Checkbutton(distortions, text=name, variable=self._distortions[name]).grid(row=index // 2, column=index % 2, sticky="w", padx=8, pady=2)
        ttk.Button(distortions, text="Apply Selected", command=self._apply_distortions).grid(row=3, column=0, pady=(6, 0), sticky="w")
        ttk.Button(distortions, text="Reset Audio", command=self._reset_audio).grid(row=3, column=1, pady=(6, 0), sticky="w")
        ttk.Label(frame, textvariable=self._status, wraplength=700).grid(row=6, column=0, columnspan=3, sticky="w", pady=(12, 0))
        ttk.Label(frame, textvariable=self._details, wraplength=700).grid(row=7, column=0, columnspan=3, sticky="w", pady=(4, 0))
        self._waveform = tk.Canvas(frame, height=180, background="#06150d", highlightthickness=1, highlightbackground="#2e8b57")
        self._waveform.grid(row=8, column=0, columnspan=3, sticky="nsew", pady=(12, 0))

    def _select_sample(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        """Replace the source with the selected deterministic fixture and refresh the display."""
        self._run_action(lambda: self._controller.select_sample(self._sample_name.get()), "Selected sample")

    def _load_wav(self) -> None:
        """Ask for a PCM16 WAV source, load it through the controller, and refresh the display."""

        path = filedialog.askopenfilename(filetypes=(("PCM WAV", "*.wav"), ("All files", "*.*")))
        if path:
            self._run_action(lambda: self._controller.load_wav(path), "Loaded WAV")

    def _issue_blocks(self) -> None:
        """Run repeated-block issuance and surface the issued opaque handle."""

        def issue() -> object:
            embedding = self._controller.issue_and_encode_blocks(self._provenance.get())
            self._handle.set(embedding.record.handle.hex().upper())
            return embedding

        self._run_action(issue, "Issued repeated-block handle")

    def _encode_supplied_blocks(self) -> None:
        """Encode the caller's hexadecimal handle into repeated attribution blocks."""

        self._run_action(
            lambda: self._controller.encode_supplied_handle_blocks(self._handle.get(), self._provenance.get()),
            "Encoded supplied repeated blocks",
        )

    def _apply_distortions(self) -> None:
        """Apply checked transformations from the clean base audio with their fixed parameters."""
        selected = tuple(name for name, enabled in self._distortions.items() if enabled.get())
        self._run_action(lambda: self._controller.apply_distortions(selected), "Applied named transformations")

    def _reset_audio(self) -> None:
        """Restore untransformed source or encoded audio while leaving toggle selections visible."""

        self._run_action(self._controller.reset_current_audio, "Reset current audio")

    def _verify(self) -> None:
        """Verify the active claim with block-vote and pooling diagnostics."""
        self._run_action(self._controller.verify, "Verified claim")

    def _v4_register_song(self) -> None:
        """Register the current source as the known-song demo catalog entry."""

        self._run_action(lambda: self._controller.v4.register_current_song("V4 demo song"), "V4 registered song")

    def _v4_register_robust_song(self) -> None:
        """Register the current source with the robust V4 demo profile."""

        self._run_action(lambda: self._controller.v4.register_robust_song("V4 robust demo song"), "V4 registered robust song")

    def _v4_generate_exports(self) -> None:
        """Generate demo recipient/export records for the V4 workflow."""

        self._run_action(lambda: self._controller.v4.generate_demo_exports(3), "V4 generated exports")

    def _v4_make_leak(self) -> None:
        """Create and display a clean suspicious excerpt from the demo leaked export."""

        def make() -> object:
            excerpt = self._controller.v4.make_demo_leak()
            self._controller._current_audio = excerpt
            return self._controller.v4.state

        self._run_action(make, "V4 made clean suspicious excerpt")

    def _v4_make_proxy_leak(self) -> None:
        """Create and display a light recorded-proxy suspicious excerpt."""

        def make() -> object:
            excerpt = self._controller.v4.make_robust_proxy_leak()
            self._controller._current_audio = excerpt
            return self._controller.v4.state

        self._run_action(make, "V4 made proxy suspicious excerpt")

    def _v4_verify_leak(self) -> None:
        """Verify the clean suspicious excerpt against V4 demo exports."""

        self._run_action(self._controller.v4.verify_demo_leak, "V4 verified leak")

    def _play_current(self) -> None:
        """Write the displayed waveform to a temporary WAV and play it asynchronously."""
        self._run_action(self._play_current_audio, "Playing current WAV")

    def _stop_playback(self) -> None:
        """Stop asynchronous WAV playback started by the Play button."""

        winsound.PlaySound(None, winsound.SND_PURGE)
        self._status.set("Stopped playback.")
        self._refresh()

    def _save_wav(self) -> None:
        """Ask for a destination path and write the currently displayed mono waveform as PCM16 WAV."""

        path = filedialog.asksaveasfilename(defaultextension=".wav", filetypes=(("PCM WAV", "*.wav"),))
        if path:
            self._run_action(lambda: write_pcm16_wav(path, self._controller.state.current_audio), "Saved current WAV")

    def _play_current_audio(self) -> Path:
        """Persist the current waveform as a temporary WAV and start OS playback."""

        winsound.PlaySound(None, winsound.SND_PURGE)
        if self._playback_path is not None:
            self._playback_path.unlink(missing_ok=True)
        handle = tempfile.NamedTemporaryFile(prefix="stegosaurus-current-", suffix=".wav", delete=False)
        handle.close()
        self._playback_path = Path(handle.name)
        write_pcm16_wav(str(self._playback_path), self._controller.state.current_audio)
        winsound.PlaySound(str(self._playback_path), winsound.SND_FILENAME | winsound.SND_ASYNC)
        return self._playback_path

    def _run_action(self, action: Callable[[], object], success_label: str) -> None:
        """Run one controller action, convert exceptions to visible status, and always update graphics."""

        try:
            result = action()
        except Exception as error:
            self._status.set(f"{type(error).__name__}: {error}")
        else:
            self._status.set(describe_result(success_label, result))
        self._refresh()

    def _refresh(self) -> None:
        """Redraw current waveform and source metadata after every visible state transition."""

        state = self._controller.state
        handle = "none" if state.active_handle is None else state.active_handle.hex().upper()
        snr = "n/a" if state.embedding_signal_to_noise_db is None else f"{state.embedding_signal_to_noise_db:.1f} dB"
        transforms = ", ".join(state.applied_distortions) or "none"
        v4 = self._controller.v4.state
        v4_match = "none" if v4.last_verification is None else v4.last_verification.matched_recipient_label or "not accepted"
        self._details.set(
            f"Source: {state.source_name} | {state.current_audio.duration_seconds:.2f} s @ {state.current_audio.sample_rate} Hz | "
            f"claim: {handle} | mode: block waterfall | blocks: {state.block_count} | "
            f"embedding SNR: {snr} | transforms: {transforms} | "
            f"V4 profile: {v4.profile_name} | V4 exports: {v4.export_count} | "
            f"V4 suspicious excerpt: {'yes' if v4.suspicious_excerpt_ready else 'no'} | V4 match: {v4_match}"
        )
        draw_waveform(self._waveform, state.current_audio.samples)


def main() -> None:
    """Launch the manual Tkinter attribution lab as ``python -m stegosaurus.audio.demo_app``."""

    root = tk.Tk()
    AttributionDemoApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
