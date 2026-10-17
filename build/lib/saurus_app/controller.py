"""Share small controller helpers for the native Saurus desktop app.

The main application owns workflow actions, while this mixin handles routine UI
state: required-field checks, file dialogs, drag-and-drop acceptance, default
output paths, and status coloring. Keeping these mechanics here prevents the
entrypoint from becoming a monolith as new views are added. No audio encoding,
verification, registry policy, or attribution decision belongs in this module.
"""

from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, simpledialog

from .credentials import DeviceCredential
from .local_registry import LocalRegistryConfig, local_registry_health
from .registry import default_output_paths
from .recovery import pending_summary
from .theme import COLORS

__all__ = ["SaurusControllerMixin"]


class SaurusControllerMixin:
    """Provide field, dialog, drop, and status helpers for ``SaurusApp``."""

    def _required(self, mode: str) -> tuple[tk.StringVar, ...]:
        """List fields required before the primary command becomes available."""

        fields = {
            "encode": (self._encode_source, self._project, self._recipient, self._encode_output, self._encode_registry),
            "decode": (self._decode_wav, self._decode_registry),
            "attribution": (self._attribution_registry,),
        }[mode]
        if self._registry_enabled.get():
            return fields + (self._registry_db,)
        return fields

    def _edited(self) -> None:
        """Clear stale result evidence when any submitted input changes."""

        if not self._busy:
            self._set_status("Inputs updated. Run Encode, Decode, or Attribution to check this selection.")
        self._refresh()

    def _refresh(self) -> None:
        """Reflect incomplete, ready, and busy states in command footers."""

        self._refresh_registry_status()
        labels = {
            "encode": ("Choose a source WAV.", "Add a project or song name.", "Add a recipient.", "Choose an encoded WAV destination.", "Choose a private registry destination."),
            "decode": ("Choose a WAV to verify.", "Choose its retained registry JSON."),
            "attribution": ("Choose a private registry JSON.",),
        }
        ready = {
            "encode": "Ready to encode and save both files.",
            "decode": "Ready to verify the selected claim.",
            "attribution": "Ready to load the retained attribution record.",
        }
        for mode, action in self._actions.items():
            mode_labels = labels[mode] + (("Choose a local registry database.",) if self._registry_enabled.get() else ())
            missing = next((label for variable, label in zip(self._required(mode), mode_labels) if not variable.get().strip()), "")
            action.state(["disabled"] if self._busy or missing else ["!disabled"])
            self._prompts[mode].configure(text="Working. Please keep this window open." if self._busy else missing or ready[mode])

    def _refresh_registry_status(self) -> None:
        """Explain whether the desktop is using sidecar or local registry mode."""

        if self._registry_enabled.get():
            self._registry_status.set("LOCAL REGISTRY ON")
            background, foreground = COLORS["tape"], COLORS["ink"]
        else:
            self._registry_status.set("SIDECAR MODE")
            background, foreground = COLORS["surface"], COLORS["muted"]
        if self._registry_status_label is not None:
            self._registry_status_label.configure(background=background, foreground=foreground)

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

    def _choose_database(self) -> None:
        """Choose or create the desktop-local registry database path."""

        path = filedialog.asksaveasfilename(
            parent=self._root,
            defaultextension=".sqlite",
            filetypes=(("SQLite registry", "*.sqlite"), ("All files", "*.*")),
            initialfile=Path(self._registry_db.get()).name,
        )
        if path:
            self._registry_db.set(path)

    def _show_registry_health(self) -> None:
        """Show an operator-visible summary of the local registry database."""

        health = local_registry_health(LocalRegistryConfig(Path(self._registry_db.get().strip())))
        if not health.exists:
            self._set_status(f"Local registry database has not been created yet.\nPath: {health.database_path}", "warning")
            return
        tenant = "tenant ready" if health.tenant_registered else "tenant missing"
        self._set_status(
            "Local registry health: "
            f"{tenant}; schema {health.schema_version}; "
            f"{health.song_count} song(s), {health.export_count} export(s) "
            f"({health.active_count} active, {health.reserved_count} reserved, "
            f"{health.failed_count} failed, {health.revoked_count} revoked); "
            f"{health.audit_event_count} audit event(s); {health.database_bytes} bytes.\n"
            f"Database: {health.database_path}",
            "success" if health.tenant_registered else "warning",
        )

    def _show_pending_encodes(self) -> None:
        """Show registry-backed encode work that still needs recovery."""

        text = pending_summary(self._pending_log)
        self._set_status(text, "warning" if text.startswith("Pending") else "success")

    def _enroll_device_credential(self) -> None:
        """Ask for an alpha credential and keep it in the session store."""

        values = {
            "registry_url": simpledialog.askstring("Enroll device", "Registry URL", parent=self._root),
            "tenant_id": simpledialog.askstring("Enroll device", "Tenant ID", parent=self._root),
            "actor_id": simpledialog.askstring("Enroll device", "Device or actor ID", parent=self._root),
            "bearer_token": simpledialog.askstring("Enroll device", "Bearer token", parent=self._root, show="*"),
        }
        if any(value is None for value in values.values()):
            self._set_status("Device enrollment canceled.", "neutral")
            return
        credential = DeviceCredential(*(str(values[name]).strip() for name in ("registry_url", "tenant_id", "actor_id", "bearer_token")))
        enrolled = self._credential_manager.enroll(credential)
        self._credential_key = (enrolled.registry_url, enrolled.tenant_id)
        self._refresh_credential_status()
        storage = "OS-backed credential storage" if self._credential_store_info.os_backed else "the current credential store"
        self._set_status(f"Device enrolled for tenant {enrolled.tenant_id} at {enrolled.registry_url}. Token is stored in {storage}.", "success")

    def _sign_out_device(self) -> None:
        """Remove the current session credential from the desktop store."""

        if self._credential_key is None:
            self._set_status("No device credential is enrolled.", "warning")
            return
        registry_url, tenant_id = self._credential_key
        self._credential_manager.sign_out(registry_url, tenant_id)
        self._credential_key = None
        self._refresh_credential_status()
        self._set_status(f"Signed out device credential for tenant {tenant_id}.", "success")

    def _refresh_credential_status(self) -> None:
        """Reflect whether a device credential is enrolled for this session."""

        if self._credential_key is None:
            self._credential_status.set("NO DEVICE")
            background, foreground = COLORS["surface"], COLORS["muted"]
        else:
            self._credential_status.set("DEVICE ENROLLED")
            background, foreground = COLORS["tape"], COLORS["ink"]
        if self._credential_status_label is not None:
            self._credential_status_label.configure(background=background, foreground=foreground)

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

    def _set_status(self, text: str, tone: str = "neutral") -> None:
        """Pair explicit status wording with the shared semantic palette."""

        self._status.set(text)
        self._status_label.configure(
            background=COLORS["subtle" if tone == "neutral" else f"{tone}_surface"],
            foreground=COLORS["muted" if tone == "neutral" else tone],
        )
