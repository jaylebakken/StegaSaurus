"""Translate shared Saurus design tokens into native Tk presentation resources.

Tk does not parse CSS. This adapter reads the same JSON values used to generate
the browser stylesheet, then assigns native fonts, colors, focus, and state maps.
PhotoImage loads the packaged PNG mark without adding an imaging dependency.
Only presentation belongs here; watermark decisions remain in the audio engine.
"""

from __future__ import annotations

import base64
import tkinter as tk
from tkinter import ttk

from saurus_style import TOKENS, asset_bytes

__all__ = ["COLORS", "SPACE", "apply_theme", "brand_image", "font", "waveform_image"]

COLORS = TOKENS["color"]
SPACE = TOKENS["space"]


def font(role: str = "body", bold: bool = False) -> tuple[str, int, str]:
    """Convert the web pixel scale to native points while respecting Tk DPI."""

    return TOKENS["font"]["ui"], round(TOKENS["type"][role] * 0.75), "bold" if bold else "normal"


def brand_image(root: tk.Misc, dark: bool = False, size: int = 64) -> tk.PhotoImage:
    """Load one retained native image from the packaged identity assets."""

    name = f"mark{'-on-dark' if dark else ''}-{size}.png"
    return tk.PhotoImage(master=root, data=base64.b64encode(asset_bytes(name)).decode("ascii"))


def waveform_image(root: tk.Misc) -> tk.PhotoImage:
    """Load the primary waveform stegosaurus at its native header size."""

    return tk.PhotoImage(
        master=root,
        data=base64.b64encode(asset_bytes("waveform-stegosaurus-180.png")).decode("ascii"),
    )


def apply_theme(root: tk.Tk) -> None:
    """Style the workspace and all important interactive states from tokens."""

    root.configure(background=COLORS["canvas"])
    style = ttk.Style(root)
    style.theme_use("clam")
    style.configure(".", font=font(), background=COLORS["surface"], foreground=COLORS["ink"])
    style.configure("TFrame", background=COLORS["surface"])
    style.configure("Shell.TFrame", background=COLORS["canvas"])
    style.configure("TLabel", background=COLORS["surface"], foreground=COLORS["ink"])
    style.configure("Title.TLabel", font=font("title", True))
    style.configure("Section.TLabel", font=font("subtitle", True))
    style.configure("Field.TLabel", font=font("small", True))
    style.configure("Help.TLabel", foreground=COLORS["muted"], font=font("small"))
    style.configure("TEntry", padding=(10, 9), fieldbackground=COLORS["surface"],
                    bordercolor=COLORS["border"], lightcolor=COLORS["border"], darkcolor=COLORS["border"])
    style.map("TEntry", bordercolor=[("focus", COLORS["forest"])],
              lightcolor=[("focus", COLORS["forest"])], darkcolor=[("focus", COLORS["forest"])],
              fieldbackground=[("disabled", COLORS["disabled_surface"])],
              foreground=[("disabled", COLORS["disabled"])])
    style.configure("TButton", padding=(16, 10), font=font("small", True),
                    background=COLORS["surface"], bordercolor=COLORS["border"],
                    lightcolor=COLORS["surface"], darkcolor=COLORS["surface"],
                    focuscolor=COLORS["forest"], focusthickness=2)
    style.map("TButton", background=[("disabled", COLORS["disabled_surface"]),
                                     ("pressed", COLORS["border"]), ("active", COLORS["subtle"])],
              foreground=[("disabled", COLORS["disabled"])])
    style.configure("Primary.TButton", background=COLORS["tape"], bordercolor=COLORS["tape"],
                    lightcolor=COLORS["tape"], darkcolor=COLORS["tape"])
    style.map("Primary.TButton", background=[("disabled", COLORS["disabled_surface"]),
                                             ("pressed", COLORS["tape_pressed"]), ("active", COLORS["tape_hover"])],
              bordercolor=[("disabled", COLORS["disabled_surface"]), ("focus", COLORS["forest"])],
              lightcolor=[("disabled", COLORS["disabled_surface"])], darkcolor=[("disabled", COLORS["disabled_surface"])])
    style.configure("TNotebook", background=COLORS["canvas"], borderwidth=0, tabmargins=(0, 0, 0, 0))
    style.configure("TNotebook.Tab", padding=(28, 12), font=font("small", True),
                    background=COLORS["subtle"], foreground=COLORS["muted"], borderwidth=0)
    style.map("TNotebook.Tab", background=[("selected", COLORS["surface"])],
              foreground=[("selected", COLORS["ink"])], lightcolor=[("selected", COLORS["tape"])],
              padding=[("selected", (28, 12)), ("!selected", (28, 12))], expand=[("selected", (0, 0, 0, 0))])
    style.configure("TSeparator", background=COLORS["border"])
    style.configure("Horizontal.TProgressbar", background=COLORS["forest"],
                    troughcolor=COLORS["subtle"], borderwidth=0, thickness=4)
    style.configure("Vertical.TScrollbar", background=COLORS["border"],
                    troughcolor=COLORS["surface"], borderwidth=0, arrowsize=12)
