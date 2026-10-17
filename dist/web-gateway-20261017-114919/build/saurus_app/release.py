"""Provide the launch entry point used by packaged desktop artifacts.

The normal app entry point opens the Tk workspace immediately. A release
artifact also needs a fast launch check that proves the packaged modules, style
assets, credential store seam, and Tk construction path work without asking a
tester to click through the interface. This module keeps those concerns beside
the desktop app while leaving encode/decode behavior in `registry.py`.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
import tkinter as tk

from .app import SaurusApp, main as launch_app
from .credentials import MemoryCredentialStore

__all__ = ["DesktopLaunchCheck", "launch_check", "main"]


@dataclass(frozen=True, slots=True)
class DesktopLaunchCheck:
    """Summarize one packaged desktop launch check."""

    ok: bool
    title: str
    tab_count: int
    registry_status: str
    credential_status: str


def launch_check() -> DesktopLaunchCheck:
    """Build and tear down the desktop workspace without showing it."""

    root = tk.Tk()
    root.withdraw()
    app = SaurusApp(root, credential_store=MemoryCredentialStore())
    try:
        root.update_idletasks()
        return DesktopLaunchCheck(
            True,
            root.title(),
            app._tabs.index("end"),
            app._registry_status.get(),
            app._credential_status.get(),
        )
    finally:
        app._executor.shutdown(wait=False)
        root.destroy()


def main(argv: list[str] | None = None) -> int:
    """Launch the desktop app or run a package-friendly launch check."""

    parser = argparse.ArgumentParser(description="Launch or check the Saurus desktop application.")
    parser.add_argument("--launch-check", action="store_true", help="Build the hidden desktop workspace and print JSON.")
    args = parser.parse_args(argv)
    if args.launch_check:
        print(json.dumps(asdict(launch_check()), indent=2, sort_keys=True))
        return 0
    launch_app()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
