"""Check the shared design resource contract without opening a desktop window.

Native Tk and browser CSS consume one palette, so stale generated CSS or missing
packaged images would split the visual identity. These checks exercise resource
loading and readable semantic text pairings, not pixel-perfect widget internals
or a claim of complete accessibility conformance.
"""

from __future__ import annotations

from importlib.resources import files
import struct

import pytest

from saurus_style import TOKENS, asset_bytes
from saurus_style.build import css_tokens


def luminance(hex_color: str) -> float:
    """Compute relative sRGB luminance for a declared palette color."""

    channels = [int(hex_color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [value / 12.92 if value <= 0.04045 else ((value + 0.055) / 1.055) ** 2.4 for value in channels]
    return sum(value * weight for value, weight in zip(linear, (0.2126, 0.7152, 0.0722)))


@pytest.mark.parametrize("foreground,background", [
    ("ink", "surface"), ("muted", "canvas"), ("ink", "tape"),
    ("on_dark", "ink"), ("muted_on_dark", "ink"),
    ("on_dark", "signal_navy"), ("muted_on_dark", "signal_navy"),
    ("success", "success_surface"), ("warning", "warning_surface"), ("error", "error_surface"),
])
def test_semantic_text_has_readable_contrast(foreground: str, background: str) -> None:
    """Keep body text and all verdict text at or above a 4.5:1 ratio."""

    low, high = sorted(luminance(TOKENS["color"][key]) for key in (foreground, background))
    assert (high + 0.05) / (low + 0.05) >= 4.5


def test_generated_css_matches_native_tokens() -> None:
    """Catch token edits that would leave browser surfaces on an old palette."""

    assert files("saurus_style").joinpath("tokens.css").read_text(encoding="utf-8") == css_tokens()


def test_native_brand_assets_are_packaged() -> None:
    """Check native PNG resources have their promised sizes and an alpha channel."""

    for variant in ("mark", "mark-on-dark"):
        for size in (32, 64, 128):
            data = asset_bytes(f"{variant}-{size}.png")
            assert data[:8] == b"\x89PNG\r\n\x1a\n"
            assert struct.unpack(">II", data[16:24]) == (size, size)
            assert data[25] == 6


def test_primary_waveform_logo_is_packaged() -> None:
    """Keep both approved primary-logo treatments available to web surfaces."""

    for name in ("waveform-stegosaurus.svg", "waveform-stegosaurus-line.svg"):
        data = asset_bytes(name)
        assert data.startswith(b"<svg")
        assert b"viewBox=\"0 0 1440 720\"" in data

    native = asset_bytes("waveform-stegosaurus-180.png")
    assert native[:8] == b"\x89PNG\r\n\x1a\n"
    assert struct.unpack(">II", native[16:24]) == (180, 90)
