"""Lay out the Encode and Decode views with shared Saurus components.

Each view is a short sequence of input sections and a fixed command footer.
The existing controller owns variables and operations, while these functions
only compose widgets and bind explicit commands. Decode copy describes retained
claim verification rather than discovery of unknown watermark identities.
"""

from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from typing import TYPE_CHECKING

from .theme import COLORS, SPACE, font, waveform_image
from .widgets import ScrollForm, field, file_row, note, section, wrapped_label

if TYPE_CHECKING:
    from .app import SaurusApp

__all__ = ["build_header", "build_encode", "build_decode"]


def build_header(root: tk.Tk) -> tk.PhotoImage:
    """Place the waveform stegosaurus on its deep navy identity band."""

    header = tk.Frame(root, background=COLORS["signal_navy"], padx=24, pady=8)
    header.pack(fill="x")
    logo = waveform_image(root)
    tk.Label(header, image=logo, background=COLORS["signal_navy"]).pack(side="left", padx=(0, 12))
    tk.Label(header, text="Saurus", font=font("title", True), background=COLORS["signal_navy"],
             foreground=COLORS["on_dark"]).pack(side="left")
    tk.Label(header, text="AUDIO WORKSPACE", font=font("caption", True), background=COLORS["signal_navy"],
             foreground=COLORS["muted_on_dark"]).pack(side="right")
    tape = tk.Canvas(root, height=6, background=COLORS["tape"], highlightthickness=0)
    tape.pack(fill="x")
    tape.bind("<Configure>", lambda event: _draw_tape(tape, event.width))
    return logo


def _draw_tape(canvas: tk.Canvas, width: int) -> None:
    """Tile the same diagonal motif as the shared tape asset on resize."""

    canvas.delete("all")
    for x in range(0, width + 32, 32):
        canvas.create_polygon(x, 0, x + 12, 0, x + 6, 6, x - 6, 6, fill=COLORS["signal_navy"], outline="")


def _view(parent: ttk.Frame, title: str, subtitle: str) -> ScrollForm:
    """Create the scrollable part of a view above its fixed footer."""

    form = ScrollForm(parent)
    form.pack(fill="both", expand=True)
    wrapped_label(form.body, title, "Title.TLabel").pack(fill="x", pady=(0, 8))
    wrapped_label(form.body, subtitle).pack(fill="x")
    signal = tk.Canvas(form.body, height=28, background=COLORS["surface"], highlightthickness=0)
    signal.pack(fill="x", pady=(14, 0))
    signal.bind("<Configure>", lambda event: _draw_signal(signal, event.width))
    return form


def _draw_signal(canvas: tk.Canvas, width: int) -> None:
    """Draw the shared audio pulse as a quiet workflow divider."""

    canvas.delete("all")
    center = 14
    canvas.create_line(0, center, width, center, fill=COLORS["border"], width=1)
    points = (0, 14, 18, 14, 26, 8, 34, 21, 42, 4, 50, 24, 58, 10, 66, 18, 74, 14, 92, 14)
    canvas.create_line(*points, fill=COLORS["forest"], width=2, smooth=False)
    canvas.create_line(42, 4, 50, 24, fill=COLORS["tape_pressed"], width=3)


def _footer(app: SaurusApp, parent: ttk.Frame, mode: str, text: str) -> None:
    """Keep the mode's primary action and readiness prompt in reach."""

    ttk.Separator(parent).pack(fill="x")
    footer = ttk.Frame(parent, padding=(SPACE["xl"], SPACE["lg"]))
    footer.pack(fill="x")
    button = ttk.Button(footer, text=text, style="Primary.TButton", command=app._encode if mode == "encode" else app._decode)
    button.pack(side="right", padx=(16, 0))
    prompt = wrapped_label(footer, "")
    prompt.pack(side="left", fill="x", expand=True)
    app._actions[mode] = button
    app._prompts[mode] = prompt


def build_encode(app: SaurusApp, parent: ttk.Frame) -> None:
    """Compose the three-step source, registry, and destination form."""

    form = _view(parent, "Create a registered copy", "Encode audio for a named recipient.")
    body = section(form.body, "01", "Choose source audio")
    _input(app, body, "Source WAV", app._encode_source, ".wav")
    hint = "Drop a file into the path field or browse. " if app._drop_enabled else ""
    wrapped_label(body, hint + "16-bit PCM WAV. The exported audio is mono.").pack(fill="x")
    columns = ttk.Frame(form.body)
    columns.pack(fill="x")
    left, right = ttk.Frame(columns), ttk.Frame(columns)
    columns.bind("<Configure>", lambda event: _reflow(columns, left, right, event.width))
    body = section(left, "02", "Add registry details")
    for label, variable in (("Project / song", app._project), ("Recipient", app._recipient)):
        row = ttk.Frame(body)
        row.pack(fill="x", pady=(0, 16))
        app._controls.append(field(row, label, variable))
    app._controls.append(field(body, "Registry notes (optional)", app._notes))
    body = section(right, "03", "Save your files")
    _input(app, body, "Encoded WAV", app._encode_output, ".wav", save=True)
    _input(app, body, "Private registry JSON", app._encode_registry, ".json", save=True)
    note(body, "Share the encoded WAV. Keep the registry JSON private; you will need it to verify this copy.")
    form.bind_inputs()
    app._forms.append(form)
    _footer(app, parent, "encode", "Encode file")


def _reflow(parent: ttk.Frame, left: ttk.Frame, right: ttk.Frame, width: int) -> None:
    """Use two readable columns on desktop and stacked steps in short widths."""

    wide = width >= 830
    parent.columnconfigure(0, weight=1, uniform="steps")
    parent.columnconfigure(1, weight=1 if wide else 0, uniform="steps" if wide else "")
    left.grid(row=0, column=0, sticky="new", padx=(0, 16 if wide else 0))
    right.grid(row=0 if wide else 1, column=1 if wide else 0, sticky="new", padx=(16 if wide else 0, 0))


def build_decode(app: SaurusApp, parent: ttk.Frame) -> None:
    """Compose retained-claim verification with an explicit abstention boundary."""

    form = _view(parent, "Verify a registered copy", "Check audio against a retained registry claim.")
    body = section(form.body, "01", "Choose audio to check")
    _input(app, body, "WAV to verify", app._decode_wav, ".wav")
    hint = "Drop a file into the path field or browse. " if app._drop_enabled else ""
    wrapped_label(body, hint + "16-bit PCM WAV.").pack(fill="x")
    body = section(form.body, "02", "Select the retained registry")
    _input(app, body, "Private registry JSON", app._decode_registry, ".json")
    note(body, "Use the JSON saved when this copy was encoded. A result verifies only the selected claim; it does not search for an unknown recipient.")
    form.bind_inputs()
    app._forms.append(form)
    _footer(app, parent, "decode", "Decode / verify")


def _input(app: SaurusApp, parent: ttk.Frame, label: str, variable: tk.StringVar, extension: str, save: bool = False) -> None:
    """Wire one reusable path row to its chooser and optional drop target."""

    entry, button = file_row(parent, label, variable, lambda: app._choose(variable, extension, save))
    app._controls.extend((entry, button))
    if app._drop_enabled and not save:
        entry.drop_target_register("DND_Files")
        entry.dnd_bind("<<Drop>>", lambda event: app._accept_drop(event, variable))
