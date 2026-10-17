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
from tkinter import messagebox, ttk

if __package__ in {None, ""}:
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    __package__ = "saurus_app"

from .registry import AttributionSummary, DecodeResult, EncodeResult, RegistryFields, decode_file, inspect_registry_file
from .controller import SaurusControllerMixin
from .credentials import CredentialStore, DesktopCredentialManager
from .local_registry import LocalRegistryConfig, default_local_registry_path, local_registry_backend
from .pending import PendingEncodeLog
from .protected_credentials import ProtectedCredentialStoreInfo, default_credential_store
from .recovery import default_pending_log_path, encode_with_pending_log
from .remote_registry import ApiRegistryBackend
from .theme import apply_theme, brand_image, font
from .views import build_attribution, build_decode, build_encode, build_header, build_registry_bar
from .widgets import ScrollForm

try:
    from tkinterdnd2 import TkinterDnD
except ImportError:
    TkinterDnD = None

__all__ = ["SaurusApp", "main"]


class SaurusApp(SaurusControllerMixin):
    """Coordinate file selection, guided state, and asynchronous operations."""

    def __init__(self, root: tk.Tk, credential_store: CredentialStore | None = None) -> None:
        """Build the themed application and start with genuinely empty fields."""

        self._root = root
        self._controls: list[ttk.Widget] = []
        self._actions: dict[str, ttk.Button] = {}
        self._prompts: dict[str, ttk.Label] = {}
        self._forms: list[ScrollForm] = []
        self._busy = False
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="saurus")
        self._drop_enabled = bool(root.tk.call("info", "commands", "tkdnd::drop_target"))
        self._registry_enabled = tk.BooleanVar(root, False)
        self._registry_db = tk.StringVar(root, str(default_local_registry_path()))
        self._registry_status = tk.StringVar(root)
        self._registry_status_label: tk.Label | None = None
        self._pending_log = PendingEncodeLog(default_pending_log_path())
        selected_store, store_info = default_credential_store() if credential_store is None else (credential_store, ProtectedCredentialStoreInfo("test-injected", None, False))
        self._credential_manager = DesktopCredentialManager(selected_store)
        self._credential_store_info = store_info
        self._credential_key: tuple[str, str] | None = None
        self._credential_status = tk.StringVar(root, "NO DEVICE")
        self._credential_status_label: tk.Label | None = None
        self._encode_source = tk.StringVar(root)
        self._encode_output = tk.StringVar(root)
        self._encode_registry = tk.StringVar(root)
        self._project = tk.StringVar(root)
        self._recipient = tk.StringVar(root)
        self._notes = tk.StringVar(root)
        self._decode_wav = tk.StringVar(root)
        self._decode_registry = tk.StringVar(root)
        self._attribution_registry = tk.StringVar(root)
        self._attribution_project = tk.StringVar(root, "No registry loaded")
        self._attribution_recipient = tk.StringVar(root, "Choose a private registry JSON to inspect.")
        self._attribution_handle = tk.StringVar(root, "--")
        self._attribution_blocks = tk.StringVar(root, "--")
        self._attribution_notes = tk.StringVar(root, "Notes appear here after a registry record is loaded.")
        apply_theme(root)
        root.title("Saurus | Audio Workspace")
        root.geometry(f"1040x{min(920, max(620, root.winfo_screenheight() - 160))}")
        root.minsize(760, 620)
        self._icon = brand_image(root)
        root.iconphoto(True, self._icon)
        self._logo = build_header(root)
        shell = ttk.Frame(root, style="Shell.TFrame", padding=(24, 20, 24, 16))
        shell.pack(fill="both", expand=True)
        build_registry_bar(self, shell)
        self._tabs = ttk.Notebook(shell)
        self._tabs.pack(fill="both", expand=True)
        for title, builder in (("Encode", build_encode), ("Decode", build_decode), ("Attribution", build_attribution)):
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
        for variable in self._required("encode") + self._required("decode") + self._required("attribution") + (self._notes, self._registry_enabled, self._registry_db):
            variable.trace_add("write", lambda *_: self._edited())
        self._refresh()
        self._refresh_credential_status()
        root.protocol("WM_DELETE_WINDOW", self._close)

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
        backend = self._registry_backend()
        self._start(lambda: encode_with_pending_log(source, output, registry, fields, backend, self._pending_log), "Encoding and checking the registered copy...")

    def _decode(self) -> None:
        """Snapshot the two input paths and submit retained-claim verification."""

        if self._busy:
            return
        wav, registry = Path(self._decode_wav.get().strip()), Path(self._decode_registry.get().strip())
        if not wav.is_file() or not registry.is_file():
            self._set_status("Choose an existing WAV and its retained registry JSON.", "error")
            return
        backend = self._registry_backend()
        self._start(lambda: self._decode_with_backend(wav, registry, backend), "Verifying the selected registry claim...")

    def _attribution(self) -> None:
        """Load retained attribution context for display without audio verification."""

        if self._busy:
            return
        registry = Path(self._attribution_registry.get().strip())
        if not registry.is_file():
            self._set_status("Choose an existing private registry JSON.", "error")
            return
        backend = self._registry_backend()
        self._start(lambda: inspect_registry_file(registry, backend=backend), "Loading retained attribution context...")

    def _registry_backend(self) -> ApiRegistryBackend | None:
        """Return the optional local registry backend selected in the UI."""

        if not self._registry_enabled.get():
            return None
        return local_registry_backend(LocalRegistryConfig(Path(self._registry_db.get().strip())))

    def _decode_with_backend(self, wav: Path, registry: Path, backend: ApiRegistryBackend | None) -> DecodeResult:
        """Verify one file and report diagnostics when using the local registry."""

        result = decode_file(wav, registry, backend=backend)
        if backend is not None:
            backend.report_verification_result(registry, result)
        return result

    def _start(self, operation: Callable[[], EncodeResult | DecodeResult | AttributionSummary], message: str) -> None:
        """Run audio work off the UI thread and poll its explicit result."""

        self._busy = True
        for control in self._controls:
            control.state(["disabled"])
        for index in range(self._tabs.index("end")):
            self._tabs.tab(index, state="disabled" if index != self._tabs.index("current") else "normal")
        self._refresh()
        self._set_status(message)
        self._progress.pack(fill="x", pady=(12, 0), before=self._status_label)
        self._progress.start(12)
        future = self._executor.submit(operation)
        self._root.after(80, lambda: self._poll(future))

    def _poll(self, future: Future[EncodeResult | DecodeResult | AttributionSummary]) -> None:
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
        for index in range(self._tabs.index("end")):
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
            self._attribution_registry.set(str(result.registry_json))
            self._set_status(f"Copy created.\nWAV: {result.output_wav}\nPrivate registry: {result.registry_json}", "success")
        elif isinstance(result, DecodeResult):
            verdict = "Registry claim verified" if result.accepted else "No accepted match"
            detail = f"{result.project} / {result.recipient}" if result.accepted else "This check could not verify the selected claim."
            self._set_status(f"{verdict}. {detail}\nHandle {result.handle_hex} | {result.block_votes}/{result.block_count} block votes | {result.reason}", "success" if result.accepted else "warning")
        else:
            self._show_attribution(result)
            self._set_status(f"Attribution record loaded for {result.project} / {result.recipient}.", "success")

    def _show_attribution(self, summary: AttributionSummary) -> None:
        """Populate the read-only attribution panel from a loaded registry file."""

        self._attribution_project.set(summary.project or "Untitled project")
        self._attribution_recipient.set(f"Registered recipient: {summary.recipient or 'Unlabeled'}")
        self._attribution_handle.set(summary.handle_hex)
        self._attribution_blocks.set(str(summary.block_count))
        self._attribution_notes.set(summary.notes or "No notes were saved with this registry record.")

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
