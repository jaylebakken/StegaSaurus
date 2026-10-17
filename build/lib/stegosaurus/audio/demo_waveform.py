"""Draw compact waveform previews for the Tkinter attribution lab.

The app uses this helper only for display. It renders a min/max envelope per
canvas column so long audio remains legible without downsampling state leaking
into the attribution controller.
"""

from __future__ import annotations

import tkinter as tk

import numpy as np


def draw_waveform(canvas: tk.Canvas, samples: np.ndarray) -> None:
    """Render min/max sample envelopes across canvas columns."""

    canvas.update_idletasks()
    width = max(canvas.winfo_width(), 640)
    height = max(canvas.winfo_height(), 180)
    canvas.delete("all")
    center = height / 2
    canvas.create_line(0, center, width, center, fill="#1f5f3b")
    for index, chunk in enumerate(np.array_split(samples, width)):
        canvas.create_line(index, center - np.max(chunk) * center, index, center - np.min(chunk) * center, fill="#62c982")
