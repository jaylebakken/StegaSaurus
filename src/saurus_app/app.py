"""Run the guided Saurus desktop workspace with a shared native visual theme.

Encode: select a WAV, add registry fields, save audio and private JSON.
Decode: select audio and that retained JSON, then verify the selected claim.
The presentation uses saurus_style tokens and assets; the existing registry
module remains the boundary to the experimental audio engine. Long operations
run on one worker and return to Tk through polling, keeping progress responsive.
Both ``python app.py`` and ``python -m saurus_app.app`` are supported.
"""

from __future__ import annotations

from concurrent.futures import Future, ThreadPoolExecutor
from collections.abc import Callable
from pathlib import Path
import sys
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "saurus_app"

from .registry import DecodeResult, EncodeResult, RegistryFields, decode_file, default_output_paths, encode_file
from .theme import COLORS, apply_theme, brand_image, font
from .views import build_decode, build_encode, build_header
from .widgets import ScrollForm

try:
    from tkinterdnd2 import TkinterDnD
except ImportError:
    TkinterDnD = None

__all__ = ["SaurusApp", "main"]


class SaurusApp:
    """Coordinate file selection, guided state, and asynchronous operations."""

    def __init__(self, root: tk.Tk) -> None:
        """Build the themed application and start with genuinely empty fields."""

        self._root = root
        self._controls: list[ttk.Widget] = []
        self._actions: dict[str, ttk.Button] = {}
        self._prompts: dict[str, ttk.Label] = {}
        self._forms: list[ScrollForm] = []
        self._busy = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="saurus")
        self._drop_enabled = bool(root.tk.call("info", "commands", "tkdnd::drop_target"))
        self._encode_source = tk.StringVar(root)
        self._encode_output = tk.StringVar(root)
        self._encode_registry = tk.StringVar(root)
        self._project = tk.StringVar(root)
        self._recipient = tk.StringVar(root)
        self._notes = tk.StringVar(root)
        self._decode_wav = tk.StringVar(root)
        self._decode_registry = tk.StringVar(root)
        apply_theme(root)
        root.title("Saurus | Audio Workspace")
        root.geometry(f"1040x{min(920, max(620, root.winfo_screenheight() - 160))}")
        root.minsize(760, 620)
        self._icon = brand_image(root)
        root.iconphoto(True, self._icon)
        self._logo = build_header(root)
        shell = ttk.Frame(root, style="Shell.TFrame", padding=(24, 20, 24, 16))
        shell.pack(fill="both", expand=True)
        self._tabs = ttk.Notebook(shell)
        self._tabs.pack(fill="both", expand=True)
        for title, builder in (("Encode", build_encode), ("Decode", build_decode)):
            panel = ttk.Frame(self._tabs)
            self._tabs.add(panel, text=title)
            builder(self, panel)
        self._tabs.enable_traversal()
        self._progress = ttk.Progressbar(shell, mode="indeterminate")
        self._status = tk.StringVar(root, "Ready. Files are processed on this computer.")
        self._status_label = tk.Label(shell, textvariable=self._status, font=font("small"), anchor="w", justify="left", padx=12, pady=10)
        self._status_label.pack(fill="x", pady=(8, 0))
        self._status_label.bind("<Configure>", lambda event: self._status_label.configure(wraplength=max(1, event.width - 24)))
        self._set_status(self._status.get())
        self._encode_source.trace_add("write", self._source_changed)
        for variable in self._required("encode") + self._required("decode") + (self._notes,):
            variable.trace_add("write", lambda *_: self._edited())
        self._refresh()
        root.protocol("WM_DELETE_WINDOW", self._close)

    def _required(self, mode: str) -> tuple[tk.StringVar, ...]:
        """List fields required before the primary command becomes available."""

        if mode == "decode":
            return self._decode_wav, self._decode_registry
        return self._encode_source, self._project, self._recipient, self._encode_output, self._encode_registry

    def _edited(self) -> None:
        """Clear stale result evidence when any of the submitted inputs change."""

        if not self._busy:
            self._set_status("Inputs updated. Run Encode or Decode to check this selection.")
        self._refresh()

    def _refresh(self) -> None:
        """Reflect incomplete, ready, and busy states in both command footers."""

        labels = {"encode": ("Choose a source WAV.", "Add a project or song name.", "Add a recipient.", "Choose an encoded WAV destination.", "Choose a private registry destination."),
                  "decode": ("Choose a WAV to verify.", "Choose its retained registry JSON.")}
        for mode, action in self._actions.items():
            missing = next((label for variable, label in zip(self._required(mode), labels[mode]) if not variable.get().strip()), "")
            action.state(["disabled"] if self._busy or missing else ["!disabled"])
            ready = "Ready to encode and save both files." if mode == "encode" else "Ready to verify the selected claim."
            self._prompts[mode].configure(text="Working. Please keep this window open." if self._busy else missing or ready)

    def _source_changed(self, *_args: str) -> None:
        """Fill friendly destinations when a complete source path is entered."""

        source = Path(self._encode_source.get().strip())
        if source.is_file():
            output, registry = default_output_paths(source)
            self._encode_output.set(str(output))
            self._encode_registry.set(str(registry))

    def _choose(self, variable: tk.StringVar, extension: str, save: bool = False) -> None:
        """Open a native file dialog and preserve the value on cancellation."""

        types = (("PCM WAV" if extension == ".wav" else "Saurus registry", f"*{extension}"),)
        if save:
            path = filedialog.asksaveasfilename(parent=self._root, defaultextension=extension, filetypes=types, initialfile=Path(variable.get()).name)
        else:
            path = filedialog.askopenfilename(parent=self._root, filetypes=types + (("All files", "*.*"),))
        if path:
            variable.set(path)

    def _accept_drop(self, event: tk.Event, variable: tk.StringVar) -> str:
        """Accept a single dropped file when the optional Tk extension is active."""

        if self._busy:
            return "none"
        paths = self._root.tk.splitlist(event.data)
        if len(paths) != 1:
            self._set_status("Choose one file at a time.", "warning")
            return "none"
        variable.set(paths[0])
        return "copy"

    def _encode(self) -> None:
        """Snapshot the form, validate paths, and submit the existing encoder."""

        if self._busy:
            return
        source, output, registry = (Path(var.get().strip()) for var in (self._encode_source, self._encode_output, self._encode_registry))
        if len({path.resolve() for path in (source, output, registry)}) != 3:
            self._set_status("Choose separate paths for the source WAV, encoded WAV, and registry JSON.", "error")
            return
        if not source.is_file() or not all(path.parent.is_dir() for path in (output, registry)):
            self._set_status("Choose an existing source WAV and destination folders.", "error")
            return
        existing = [str(path) for path in (output, registry) if path.exists()]
        if existing and not messagebox.askyesno("Replace existing outputs?", "These output files already exist:\n\n" + "\n".join(existing), parent=self._root):
            return
        fields = RegistryFields(self._project.get(), self._recipient.get(), self._notes.get())
        self._start(lambda: encode_file(source, output, registry, fields), "Encoding and checking the registered copy...")

    def _decode(self) -> None:
        """Snapshot the two input paths and submit retained-claim verification."""

        if self._busy:
            return
        wav, registry = Path(self._decode_wav.get().strip()), Path(self._decode_registry.get().strip())
        if not wav.is_file() or not registry.is_file():
            self._set_status("Choose an existing WAV and its retained registry JSON.", "error")
            return
        self._start(lambda: decode_file(wav, registry), "Verifying the selected registry claim...")

    def _start(self, operation: Callable[[], EncodeResult | DecodeResult], message: str) -> None:
        """Run audio work off the UI thread and poll its explicit result."""

        self._busy = True
        for control in self._controls:
            control.state(["disabled"])
        for index in range(2):
            self._tabs.tab(index, state="disabled" if index != self._tabs.index("current") else "normal")
        self._refresh()
        self._set_status(message)
        self._progress.pack(fill="x", pady=(12, 0), before=self._status_label)
        self._progress.start(12)
        future = self._executor.submit(operation)
        self._root.after(80, lambda: self._poll(future))

    def _poll(self, future: Future[EncodeResult | DecodeResult]) -> None:
        """Deliver completed results on the Tk thread and restore controls."""

        if not future.done():
            self._root.after(80, lambda: self._poll(future))
            return
        self._busy = False
        self._progress.stop()
        self._progress.configure(value=0)
        self._progress.pack_forget()
        for control in self._controls:
            control.state(["!disabled"])
        for index in range(2):
            self._tabs.tab(index, state="normal")
        self._refresh()
        try:
            result = future.result()
        except Exception as error:
            self._set_status(f"Operation could not finish. {error}", "error")
            return
        if isinstance(result, EncodeResult):
            self._decode_wav.set(str(result.output_wav))
            self._decode_registry.set(str(result.registry_json))
            self._set_status(f"Copy created.\nWAV: {result.output_wav}\nPrivate registry: {result.registry_json}", "success")
        else:
            verdict = "Registry claim verified" if result.accepted else "No accepted match"
            detail = f"{result.project} / {result.recipient}" if result.accepted else "This check could not verify the selected claim."
            self._set_status(f"{verdict}. {detail}\nHandle {result.handle_hex} | {result.block_votes}/{result.block_count} block votes | {result.reason}", "success" if result.accepted else "warning")

    def _set_status(self, text: str, tone: str = "neutral") -> None:
        """Pair explicit status wording with the shared semantic palette."""

        self._status.set(text)
        self._status_label.configure(background=COLORS["subtle" if tone == "neutral" else f"{tone}_surface"],
                                     foreground=COLORS["muted" if tone == "neutral" else tone])

    def _close(self) -> None:
        """Let active writes finish before disposing of the worker and window."""

        if self._busy:
            self._set_status("An operation is still running. This window can close when it finishes.", "warning")
            return
        self._executor.shutdown(wait=False)
        self._root.destroy()


def main() -> None:
    """Launch from a module or direct script, with optional file-drop support."""

    root = TkinterDnD.Tk() if TkinterDnD is not None else tk.Tk()
    SaurusApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
