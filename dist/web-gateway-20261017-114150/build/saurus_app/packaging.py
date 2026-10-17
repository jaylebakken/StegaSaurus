"""Build a lightweight alpha package for the Saurus desktop app.

The alpha desktop does not yet need an installer or a frozen executable. A
Python zip application is enough to prove the source tree can be assembled into
one launchable artifact on the target OS while still relying on the Python
environment used for local development. The package deliberately excludes test
fixtures and archived experiments so release checks stay quick and focused.
"""

from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass
import json
from pathlib import Path
import shutil
import subprocess
import sys
from tempfile import TemporaryDirectory
from typing import Literal
import zipapp

from .security import review_desktop_secret_posture

__all__ = ["DesktopPackageResult", "build_desktop_zipapp", "main"]

PACKAGE_NAMES = ("saurus_app", "saurus_registry", "saurus_style", "stegosaurus")
EXCLUDED_DIRS = {"__pycache__", ".pytest_cache", "tests", "experiments"}
ReleaseChannel = Literal["alpha", "production"]


@dataclass(frozen=True, slots=True)
class DesktopPackageResult:
    """Summarize one desktop package build."""

    output_path: Path
    size_bytes: int
    launch_check_passed: bool
    package_names: tuple[str, ...]
    release_channel: str


def build_desktop_zipapp(
    output_path: Path,
    *,
    launch_check: bool = True,
    release_channel: ReleaseChannel = "alpha",
) -> DesktopPackageResult:
    """Create one `.pyz` desktop artifact and optionally launch-check it."""

    _validate_release_channel(release_channel)
    destination = output_path.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    with TemporaryDirectory(prefix="saurus-desktop-package-") as temporary:
        staging = Path(temporary) / "app"
        staging.mkdir()
        source_root = Path(__file__).resolve().parents[1]
        for package_name in PACKAGE_NAMES:
            _copy_package(source_root / package_name, staging / package_name)
        zipapp.create_archive(staging, target=destination, main="saurus_app.release:main", interpreter="/usr/bin/env python")
    passed = _run_launch_check(destination) if launch_check else False
    return DesktopPackageResult(destination, destination.stat().st_size, passed, PACKAGE_NAMES, release_channel)


def main(argv: list[str] | None = None) -> int:
    """Build the alpha desktop package and print a concise JSON manifest."""

    parser = argparse.ArgumentParser(description="Build the Saurus desktop alpha zipapp.")
    parser.add_argument("--output", type=Path, default=Path("dist") / "saurus-desktop.pyz")
    parser.add_argument("--release-channel", choices=("alpha", "production"), default="alpha")
    parser.add_argument("--skip-launch-check", action="store_true")
    args = parser.parse_args(argv)
    result = build_desktop_zipapp(args.output, launch_check=not args.skip_launch_check, release_channel=args.release_channel)
    print(json.dumps(_json_result(result), indent=2, sort_keys=True))
    return 0


def _validate_release_channel(release_channel: ReleaseChannel) -> None:
    """Block production packaging while a local-demo watermark secret remains."""

    if release_channel == "alpha":
        return
    posture = review_desktop_secret_posture()
    if not posture.production_ready:
        raise ValueError(f"production package requires KMS-backed watermark grants; current secret scope is {posture.scope}")


def _copy_package(source: Path, destination: Path) -> None:
    """Copy one import package while excluding local-only heavy directories."""

    if not source.is_dir():
        raise ValueError(f"package source does not exist: {source}")
    shutil.copytree(source, destination, ignore=lambda directory, names: sorted(_ignored_names(directory, names)))


def _ignored_names(_directory: str, names: list[str]) -> set[str]:
    """Return local-only package entries to omit from the alpha artifact."""

    return {name for name in names if name in EXCLUDED_DIRS or name.endswith((".pyc", ".pyo"))}


def _run_launch_check(package_path: Path) -> bool:
    """Run the packaged app's hidden Tk launch check."""

    completed = subprocess.run(
        [sys.executable, str(package_path), "--launch-check"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0:
        raise RuntimeError(completed.stderr.strip() or completed.stdout.strip() or "packaged launch check failed")
    return True


def _json_result(result: DesktopPackageResult) -> dict[str, object]:
    """Return a JSON-safe package result."""

    payload = asdict(result)
    payload["output_path"] = str(result.output_path)
    return payload


if __name__ == "__main__":
    raise SystemExit(main())
