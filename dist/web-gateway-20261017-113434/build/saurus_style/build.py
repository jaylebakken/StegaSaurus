"""Derive browser tokens and small brand assets with the Python standard library.

Run ``python -m saurus_style.build`` after changing tokens.json. The established
site mark is three rising audio bars: forest, yellow, and copper. Vector and
transparent PNG variants use the same geometry; Tk can load PNG without Pillow.
PNG scanlines are encoded here only to keep brand generation dependency-free.
This is a design asset builder, not an audio transform or a UI runtime service.
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
import struct
import zlib

from . import TOKENS

ROOT = Path(__file__).resolve().parent
COLORS = TOKENS["color"]
BARS = ((8, 28, 20, 54, "forest"), (26, 10, 38, 54, "tape"), (44, 20, 56, 54, "copper"))


def css_tokens() -> str:
    """Return namespaced CSS variables in the declared JSON order."""

    lines = ["/* Generated from tokens.json by python -m saurus_style.build. */", ":root {"]
    for group, values in TOKENS.items():
        for name, value in values.items():
            formatted = f'"{value}"' if group == "font" else str(value)
            if isinstance(value, int):
                formatted += "px"
            lines.append(f"  --saurus-{group}-{name.replace('_', '-')}: {formatted};")
    return "\n".join([*lines, "}", ""])


def mark_svg(dark: bool = False) -> str:
    """Render the existing three-bar identity in a 64-unit clear-space box."""

    bars = []
    for left, top, right, bottom, role in BARS:
        color = COLORS["on_dark"] if dark and role == "forest" else COLORS[role]
        bars.append(f'<rect x="{left}" y="{top}" width="{right-left}" height="{bottom-top}" rx="2" fill="{color}"/>')
    return '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="Saurus">' + "".join(bars) + "</svg>\n"


def rgba(color: str) -> tuple[int, int, int, int]:
    """Expand a six-digit brand color to opaque PNG channels."""

    return (*tuple(int(color[index:index + 2], 16) for index in (1, 3, 5)), 255)


def mark_pixel(x: float, y: float, dark: bool) -> tuple[int, int, int, int]:
    """Sample rounded logo bars, keeping outside pixels transparent."""

    for left, top, right, bottom, role in BARS:
        near_x, near_y = max(left + 2, min(x, right - 2)), max(top + 2, min(y, bottom - 2))
        if (x - near_x) ** 2 + (y - near_y) ** 2 <= 4:
            return rgba(COLORS["on_dark"] if dark and role == "forest" else COLORS[role])
    return (0, 0, 0, 0)


def png(width: int, height: int, pixel: Callable[[int, int], tuple[int, int, int, int]]) -> bytes:
    """Encode deterministic RGBA scanlines as a standards-compliant PNG."""

    raw = b"".join(b"\0" + bytes(channel for x in range(width) for channel in pixel(x, y)) for y in range(height))
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)) + chunk(b"IDAT", zlib.compress(raw)) + chunk(b"IEND", b"")


def chunk(kind: bytes, data: bytes) -> bytes:
    """Wrap one PNG chunk with its length and CRC."""

    return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))


def build() -> None:
    """Write committed CSS, scalable logos, PNG icons, and the tape tile."""

    (ROOT / "tokens.css").write_text(css_tokens(), encoding="utf-8")
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    for dark in (False, True):
        stem = "mark-on-dark" if dark else "mark"
        (assets / f"{stem}.svg").write_text(mark_svg(dark), encoding="utf-8")
        for size in (32, 64, 128):
            (assets / f"{stem}-{size}.png").write_bytes(png(size, size, lambda x, y: mark_pixel((x + 0.5) * 64 / size, (y + 0.5) * 64 / size, dark)))
    (assets / "tape.png").write_bytes(png(32, 8, lambda x, y: rgba(COLORS["ink" if (x + y) % 32 < 12 else "tape"])))
    (assets / "tape.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg" width="32" height="8" viewBox="0 0 32 8">'
        f'<path fill="{COLORS["tape"]}" d="M0 0h32v8H0z"/>'
        f'<path fill="{COLORS["ink"]}" d="M0 0h12L4 8H0zm32 0v8h-8z"/></svg>\n', encoding="utf-8",
    )


if __name__ == "__main__":
    build()
