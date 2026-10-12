"""Compose small native controls for the guided Saurus file workflow.

The form can exceed a short desktop window. A canvas scrolls only its content,
while the containing view keeps commands in reach. Labels wrap with the available
width and editable path fields use native horizontal scrolling. These controls
do not read audio, choose attribution policy, or infer verification outcomes.
"""

from __future__ import annotations

from collections.abc import Callable
import tkinter as tk
from tkinter import ttk

from .theme import COLORS, SPACE, font

__all__ = ["ScrollForm", "field", "file_row", "note", "section", "wrapped_label"]


class ScrollForm(ttk.Frame):
    """Keep a long form reachable without moving the view's command footer."""

    def __init__(self, parent: tk.Misc) -> None:
        """Create a width-constrained form and its native scrollbar."""

        super().__init__(parent)
        self.canvas = tk.Canvas(self, background=COLORS["surface"], highlightthickness=0)
        self.scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(yscrollcommand=self.scrollbar.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        self.scrollbar.pack(side="right", fill="y")
        self.body = ttk.Frame(self.canvas, padding=(SPACE["xl"], SPACE["xl"]))
        self.window = self.canvas.create_window(0, 0, anchor="nw", window=self.body)
        self.canvas.bind("<Configure>", self._resize)
        self.body.bind("<Configure>", self._content_changed)
        self.bind("<Map>", self._content_changed)

    def bind_inputs(self) -> None:
        """Give only this form's descendants wheel and focus-scroll behavior."""

        pending: list[tk.Misc] = [self.canvas]
        while pending:
            widget = pending.pop()
            widget.bind("<MouseWheel>", self._wheel, add="+")
            widget.bind("<Button-4>", lambda event: self.canvas.yview_scroll(-3, "units"), add="+")
            widget.bind("<Button-5>", lambda event: self.canvas.yview_scroll(3, "units"), add="+")
            widget.bind("<FocusIn>", self._reveal_focus, add="+")
            pending.extend(widget.winfo_children())

    def _resize(self, event: tk.Event) -> None:
        """Keep the form exactly as wide as the available viewport."""

        self.canvas.itemconfigure(self.window, width=event.width)

    def _content_changed(self, event: tk.Event) -> None:
        """Update the scroll region after wrapping, layout, or tab selection."""

        self.canvas.configure(scrollregion=self.canvas.bbox("all"))

    def _wheel(self, event: tk.Event) -> str:
        """Scroll a visible overflowing form without globally binding the wheel."""

        if self.body.winfo_height() > self.canvas.winfo_height():
            units = -1 if event.delta > 0 else 1
            self.canvas.yview_scroll(units * 3, "units")
        return "break"

    def _reveal_focus(self, event: tk.Event) -> None:
        """Keep keyboard-focused controls visible inside a short window."""

        widget = event.widget
        top = widget.winfo_rooty() - self.body.winfo_rooty()
        start = self.canvas.canvasy(0)
        bottom = top + widget.winfo_height()
        height = self.canvas.winfo_height()
        if top < start or bottom > start + height:
            target = top - 12 if top < start else bottom - height + 12
            self.canvas.yview_moveto(max(0, target) / max(1, self.body.winfo_height()))


def wrapped_label(parent: tk.Misc, text: str, style: str = "Help.TLabel") -> ttk.Label:
    """Make a readable label that tracks its actual available width."""

    label = ttk.Label(parent, text=text, style=style, wraplength=480, justify="left")
    label.bind("<Configure>", lambda event: label.configure(wraplength=max(1, event.width)))
    return label


def section(parent: tk.Misc, number: str, title: str) -> ttk.Frame:
    """Start an unframed workflow section with a stable numbered marker."""

    header = ttk.Frame(parent)
    header.pack(fill="x", pady=(SPACE["xl"], SPACE["md"]))
    tk.Label(header, text=number, background=COLORS["tape"], foreground=COLORS["ink"],
             font=font("small", True), padx=8, pady=5).pack(side="left", padx=(0, SPACE["md"]))
    wrapped_label(header, title, "Section.TLabel").pack(side="left", fill="x", expand=True)
    body = ttk.Frame(parent)
    body.pack(fill="x")
    return body


def field(parent: tk.Misc, label: str, variable: tk.StringVar) -> ttk.Entry:
    """Pair a permanent field label with an editable native entry."""

    ttk.Label(parent, text=label, style="Field.TLabel").pack(anchor="w", pady=(0, SPACE["sm"]))
    entry = ttk.Entry(parent, textvariable=variable, width=1)
    entry.pack(fill="x")
    return entry


def file_row(parent: tk.Misc, label: str, variable: tk.StringVar, command: Callable[[], None]) -> tuple[ttk.Entry, ttk.Button]:
    """Lay out a labeled path and a stable file chooser command."""

    ttk.Label(parent, text=label, style="Field.TLabel").pack(anchor="w", pady=(0, SPACE["sm"]))
    row = ttk.Frame(parent)
    row.pack(fill="x", pady=(0, SPACE["md"]))
    entry = ttk.Entry(row, textvariable=variable, width=1)
    entry.pack(side="left", fill="x", expand=True, padx=(0, SPACE["sm"]))
    button = ttk.Button(row, text="Browse...", command=command, width=10)
    button.pack(side="right")
    return entry, button


def note(parent: tk.Misc, text: str) -> tk.Frame:
    """Show concise private-registry guidance in a yellow attention band."""

    band = tk.Frame(parent, background=COLORS["tape"])
    band.pack(fill="x", pady=(SPACE["md"], 0))
    label = tk.Label(band, text=text, background=COLORS["warning_surface"], foreground=COLORS["warning"],
                     font=font("small"), anchor="w", justify="left", padx=12, pady=12, wraplength=480)
    label.pack(fill="x", padx=(4, 0))
    label.bind("<Configure>", lambda event: label.configure(wraplength=max(1, event.width - 24)))
    return band
