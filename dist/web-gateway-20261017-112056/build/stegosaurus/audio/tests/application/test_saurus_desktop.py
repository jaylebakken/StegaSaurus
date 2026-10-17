"""Exercise user-visible desktop state transitions with the existing Tk runtime.

Audio round trips live in test_saurus_app.py. These checks cover the changed
presentation contract: jobs lock submitted inputs, return useful results, recover
from errors, and keep the command accessible in a compact window. A host without
a graphical Tk display skips the native checks but still runs resource tests.
"""

from __future__ import annotations

from collections.abc import Iterator
from concurrent.futures import Future
from pathlib import Path
import subprocess
import sys
from threading import Event
import time
import tkinter as tk
from tkinter import simpledialog

import pytest

from saurus_app.app import SaurusApp
from saurus_app.credentials import MemoryCredentialStore
from saurus_app.registry import DecodeResult, EncodeResult
from saurus_app.theme import COLORS


@pytest.fixture
def desktop() -> Iterator[SaurusApp]:
    """Create a disposable native workspace when the host supports Tk windows."""

    try:
        root = tk.Tk()
    except tk.TclError as error:
        pytest.skip(f"Tk display unavailable: {error}")
    root.withdraw()
    app = SaurusApp(root, credential_store=MemoryCredentialStore())
    yield app
    app._executor.shutdown(wait=True)
    root.destroy()


def wait_for_job(app: SaurusApp) -> None:
    """Pump Tk events until a bounded test job has delivered its result."""

    deadline = time.monotonic() + 5
    while app._busy and time.monotonic() < deadline:
        app._root.update()
        time.sleep(0.01)
    assert not app._busy


def test_encode_job_locks_inputs_and_prepares_verification(desktop: SaurusApp, tmp_path: Path) -> None:
    """Keep a running job responsive and seed Decode from the saved outputs."""

    app = desktop
    release = Event()
    result = EncodeResult(tmp_path / "encoded.wav", tmp_path / "private.json", "ABCD1234", 1, 22.0)

    def operation() -> EncodeResult:
        """Hold the worker briefly so the submitted state can be inspected."""

        assert release.wait(3)
        return result

    app._start(operation, "Encoding...")
    try:
        assert app._busy
        assert all(control.instate(["disabled"]) for control in app._controls)
        assert all(button.instate(["disabled"]) for button in app._actions.values())
        assert app._tabs.tab(1, "state") == "disabled"
        app._root.update()
        assert app._status.get() == "Encoding..."
    finally:
        release.set()
    wait_for_job(app)
    assert all(control.instate(["!disabled"]) for control in app._controls)
    assert app._decode_wav.get() == str(result.output_wav)
    assert app._decode_registry.get() == str(result.registry_json)
    assert app._actions["decode"].instate(["!disabled"])
    assert "Copy created" in app._status.get()


@pytest.mark.parametrize("accepted,tone,verdict", [(True, "success", "Registry claim verified"), (False, "warning", "No accepted match")])
def test_verdict_preserves_abstention(desktop: SaurusApp, accepted: bool, tone: str, verdict: str) -> None:
    """Never present a nonaccepted claim as a confirmed identity."""

    future: Future[EncodeResult | DecodeResult] = Future()
    future.set_result(DecodeResult(accepted, "test", "Recorded evidence.", "ABCD1234", "Recipient", "Project", int(accepted), 1, 0))
    desktop._poll(future)
    assert desktop._status.get().startswith(verdict)
    assert desktop._status_label.cget("background") == COLORS[f"{tone}_surface"]
    if not accepted:
        assert "Project / Recipient" not in desktop._status.get()
    desktop._decode_wav.set("different.wav")
    assert "Inputs updated" in desktop._status.get()
    assert desktop._status_label.cget("background") == COLORS["subtle"]


def test_failed_job_restores_the_form(desktop: SaurusApp) -> None:
    """Surface a worker exception as an error and allow another attempt."""

    def operation() -> EncodeResult:
        """Stand in for a file rejected by the audio boundary."""

        raise ValueError("Choose a 16-bit PCM WAV.")

    desktop._start(operation, "Encoding...")
    wait_for_job(desktop)
    assert "could not finish" in desktop._status.get()
    assert "16-bit PCM WAV" in desktop._status.get()
    assert desktop._status_label.cget("background") == COLORS["error_surface"]
    assert all(control.instate(["!disabled"]) for control in desktop._controls)


def test_device_enrollment_controls_store_and_clear_session_credential(desktop: SaurusApp, monkeypatch: pytest.MonkeyPatch) -> None:
    """Expose alpha credential enrollment without writing tokens to status text."""

    answers = iter(("https://registry.saurus.test", "tenant-1", "device-1", "secret-token"))
    monkeypatch.setattr(simpledialog, "askstring", lambda *args, **kwargs: next(answers))

    desktop._enroll_device_credential()
    credential = desktop._credential_manager.credential("https://registry.saurus.test", "tenant-1")

    assert credential.actor_id == "device-1"
    assert desktop._credential_key == ("https://registry.saurus.test", "tenant-1")
    assert desktop._credential_status.get() == "DEVICE ENROLLED"
    assert "secret-token" not in desktop._status.get()

    desktop._sign_out_device()

    assert desktop._credential_key is None
    assert desktop._credential_status.get() == "NO DEVICE"
    with pytest.raises(ValueError, match="not enrolled"):
        desktop._credential_manager.credential("https://registry.saurus.test", "tenant-1")


def test_compact_window_keeps_commands_visible(desktop: SaurusApp) -> None:
    """Keep both action footers inside the smallest supported native window."""

    root = desktop._root
    root.geometry("760x620")
    root.deiconify()
    for index, mode in enumerate(("encode", "decode")):
        desktop._tabs.select(index)
        root.update()
        button = desktop._actions[mode]
        assert button.winfo_ismapped()
        bottom = button.winfo_rooty() - root.winfo_rooty() + button.winfo_height()
        assert 0 < bottom < root.winfo_height()
        assert desktop._forms[index].body.winfo_width() <= desktop._forms[index].canvas.winfo_width()


def test_direct_script_can_import_from_its_own_directory() -> None:
    """Retain the direct python app.py import path while splitting UI modules."""

    import saurus_app.app as app_module

    result = subprocess.run([sys.executable, "-c", "import runpy; runpy.run_path('app.py', run_name='launch_check')"],
                            cwd=Path(app_module.__file__).parent, capture_output=True, text=True, timeout=15)
    assert result.returncode == 0, result.stderr
