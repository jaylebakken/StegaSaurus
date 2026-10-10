"""Render a compact green Tkinter lab for manual attribution experiments.

The app is intentionally a display and control surface rather than a second
watermark implementation. Its controller performs the documented process:

    choose synthetic/WAV cover -> encode a v1 claim or v2 repeated blocks
        -> select transforms -> verify retained claim evidence

The visible named transformations are manual test inputs. They do not make a
robustness, imperceptibility, compression, or blind-discovery claim.
"""

from __future__ import annotations

import tkinter as tk
from collections.abc import Callable
from tkinter import filedialog, ttk

import numpy as np

from .attribution import AttributionVerification, BlockAttributionVerification
from .demo_controller import AttributionDemoController, DISTORTION_NAMES
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
        self._status = tk.StringVar(value="Choose a sample, then issue a calibrated handle or provide 8 hex digits.")
        self._details = tk.StringVar()
        self._configure_theme()
        self._build()
        self._refresh()

    def _configure_theme(self) -> None:
        """Configure a restrained dark green ttk palette without requiring external theme assets."""

        self._root.title("Stegosaurus Audio Attribution Lab")
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
        ttk.Button(controls, text="Issue V1 Handle", command=self._issue).grid(row=0, column=0, padx=(0, 6))
        ttk.Button(controls, text="Encode V1 Supplied", command=self._encode_supplied).grid(row=0, column=1, padx=6)
        ttk.Button(controls, text="Issue V2 Blocks", command=self._issue_blocks).grid(row=1, column=0, padx=(0, 6), pady=(6, 0))
        ttk.Button(controls, text="Encode V2 Supplied", command=self._encode_supplied_blocks).grid(row=1, column=1, padx=6, pady=(6, 0))
        ttk.Button(controls, text="Verify Claim", command=self._verify).grid(row=0, column=2, padx=6)
        ttk.Button(controls, text="Save Current WAV", command=self._save_wav).grid(row=0, column=3, padx=6)
        distortions = ttk.LabelFrame(frame, text="Named Manual Transformations", padding=8)
        distortions.grid(row=4, column=0, columnspan=3, sticky="ew", pady=(12, 0))
        for index, name in enumerate(DISTORTION_NAMES):
            ttk.Checkbutton(distortions, text=name, variable=self._distortions[name]).grid(row=index // 2, column=index % 2, sticky="w", padx=8, pady=2)
        ttk.Button(distortions, text="Apply Selected", command=self._apply_distortions).grid(row=3, column=0, pady=(6, 0), sticky="w")
        ttk.Button(distortions, text="Reset Audio", command=self._reset_audio).grid(row=3, column=1, pady=(6, 0), sticky="w")
        ttk.Label(frame, textvariable=self._status, wraplength=700).grid(row=5, column=0, columnspan=3, sticky="w", pady=(12, 0))
        ttk.Label(frame, textvariable=self._details, wraplength=700).grid(row=6, column=0, columnspan=3, sticky="w", pady=(4, 0))
        self._waveform = tk.Canvas(frame, height=180, background="#06150d", highlightthickness=1, highlightbackground="#2e8b57")
        self._waveform.grid(row=7, column=0, columnspan=3, sticky="nsew", pady=(12, 0))

    def _select_sample(self, _event: tk.Event[tk.Misc] | None = None) -> None:
        """Replace the source with the selected deterministic fixture and refresh the display."""

        self._run_action(lambda: self._controller.select_sample(self._sample_name.get()), "Selected sample")

    def _load_wav(self) -> None:
        """Ask for a PCM16 WAV source, load it through the controller, and refresh the display."""

        path = filedialog.askopenfilename(filetypes=(("PCM WAV", "*.wav"), ("All files", "*.*")))
        if path:
            self._run_action(lambda: self._controller.load_wav(path), "Loaded WAV")

    def _issue(self) -> None:
        """Run calibrated issuance and surface the issued opaque handle in the entry field."""

        def issue() -> object:
            embedding = self._controller.issue_and_encode(self._provenance.get())
            self._handle.set(embedding.record.handle.hex().upper())
            return embedding

        self._run_action(issue, "Issued calibrated handle")

    def _encode_supplied(self) -> None:
        """Encode the caller's hexadecimal handle and display its immediate clean claim verification."""

        self._run_action(
            lambda: self._controller.encode_supplied_handle(self._handle.get(), self._provenance.get()),
            "Encoded supplied handle",
        )

    def _issue_blocks(self) -> None:
        """Run v2 repeated-block issuance and surface the issued opaque handle."""

        def issue() -> object:
            embedding = self._controller.issue_and_encode_blocks(self._provenance.get())
            self._handle.set(embedding.record.handle.hex().upper())
            return embedding

        self._run_action(issue, "Issued v2 block handle")

    def _encode_supplied_blocks(self) -> None:
        """Encode the caller's hexadecimal handle into repeated v2 blocks."""

        self._run_action(
            lambda: self._controller.encode_supplied_handle_blocks(self._handle.get(), self._provenance.get()),
            "Encoded supplied v2 blocks",
        )

    def _apply_distortions(self) -> None:
        """Apply checked transformations from the clean base audio with their fixed parameters."""

        selected = tuple(name for name, enabled in self._distortions.items() if enabled.get())
        self._run_action(lambda: self._controller.apply_distortions(selected), "Applied named transformations")

    def _reset_audio(self) -> None:
        """Restore untransformed source or encoded audio while leaving toggle selections visible."""

        self._run_action(self._controller.reset_current_audio, "Reset current audio")

    def _verify(self) -> None:
        """Verify the active claim with its retained local carrier map and render decoder diagnostics."""

        self._run_action(self._controller.verify, "Verified claim")

    def _save_wav(self) -> None:
        """Ask for a destination path and write the currently displayed mono waveform as PCM16 WAV."""

        path = filedialog.asksaveasfilename(defaultextension=".wav", filetypes=(("PCM WAV", "*.wav"),))
        if path:
            self._run_action(lambda: write_pcm16_wav(path, self._controller.state.current_audio), "Saved current WAV")

    def _run_action(self, action: Callable[[], object], success_label: str) -> None:
        """Run one controller action, convert exceptions to visible status, and always update graphics."""

        try:
            result = action()
        except Exception as error:
            self._status.set(f"{type(error).__name__}: {error}")
        else:
            self._status.set(self._describe_result(success_label, result))
        self._refresh()

    def _describe_result(self, label: str, result: object) -> str:
        """Summarize known verification diagnostics while keeping generic controller actions concise."""

        verification = result[-1] if isinstance(result, tuple) else result
        if isinstance(verification, AttributionVerification):
            return f"{label}: {verification.status.value}; RS cost {verification.claim_rs_cost}/16."
        if isinstance(verification, BlockAttributionVerification):
            pooled = verification.pooled_verification
            return (
                f"{label}: {verification.status.value}; pooled RS cost {pooled.claim_rs_cost}/16; "
                f"block votes {verification.recovered_block_count}/{len(verification.block_verifications)}."
            )
        return f"{label}."

    def _refresh(self) -> None:
        """Redraw current waveform and source metadata after every visible state transition."""

        state = self._controller.state
        handle = "none" if state.active_handle is None else state.active_handle.hex().upper()
        snr = "n/a" if state.embedding_signal_to_noise_db is None else f"{state.embedding_signal_to_noise_db:.1f} dB"
        transforms = ", ".join(state.applied_distortions) or "none"
        self._details.set(
            f"Source: {state.source_name} | {state.current_audio.duration_seconds:.2f} s @ {state.current_audio.sample_rate} Hz | "
            f"claim: {handle} | mode: {state.attribution_mode} | blocks: {state.block_count} | "
            f"embedding SNR: {snr} | transforms: {transforms}"
        )
        self._draw_waveform(state.current_audio.samples)

    def _draw_waveform(self, samples: np.ndarray) -> None:
        """Render min/max sample envelopes across canvas columns for a legible long-audio preview."""

        self._waveform.update_idletasks()
        width = max(self._waveform.winfo_width(), 640)
        height = max(self._waveform.winfo_height(), 180)
        self._waveform.delete("all")
        center = height / 2
        self._waveform.create_line(0, center, width, center, fill="#1f5f3b")
        chunks = np.array_split(samples, width)
        for index, chunk in enumerate(chunks):
            self._waveform.create_line(index, center - np.max(chunk) * center, index, center - np.min(chunk) * center, fill="#62c982")


def main() -> None:
    """Launch the manual Tkinter attribution lab as ``python -m stegosaurus.audio.demo_app``."""

    root = tk.Tk()
    AttributionDemoApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
