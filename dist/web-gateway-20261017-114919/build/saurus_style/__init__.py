"""Share Saurus design tokens and packaged brand assets across native surfaces.

The JSON file is the editable source of truth. The desktop reads it at startup;
the build module derives browser CSS and logo files from the same values. Assets
live beside this module so editable installs and built wheels behave alike.
These are presentation resources, independent of audio and attribution policy.
"""

from __future__ import annotations

from importlib.resources import files
import json

__all__ = ["TOKENS", "asset_bytes"]

TOKENS = json.loads(files(__package__).joinpath("tokens.json").read_text(encoding="utf-8"))


def asset_bytes(name: str) -> bytes:
    """Read one packaged asset without depending on the working directory."""

    if not name or "/" in name or "\\" in name or name in {".", ".."}:
        raise ValueError("asset name must be a single filename")
    return files(__package__).joinpath("assets", name).read_bytes()
