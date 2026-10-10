"""Test UI-independent fixtures and orchestration used by the manual Tkinter attribution lab.

These checks deliberately avoid creating a Tk root so application validation
works in headless environments. The existing attribution tests exercise the
expensive calibrated encode/decode round trip; this module covers the lab's
selection, supplied-handle validation, and deterministic transform boundary.
"""

from __future__ import annotations

import pytest

from stegosaurus.audio.attribution import InMemoryAttributionRegistry
from stegosaurus.audio.demo_controller import AttributionDemoController
from stegosaurus.audio.demo_samples import music_like_sample, speech_like_sample


def test_demo_samples_are_deterministic_thirty_second_mono_covers() -> None:
    """Create the built-in source fixtures at the v1 profile's intended duration and rate."""

    music = music_like_sample()
    speech = speech_like_sample()

    assert music.sample_rate == speech.sample_rate == 16000
    assert music.duration_seconds == speech.duration_seconds == 30
    assert len(music.samples) == len(speech.samples)


def test_demo_controller_selects_samples_and_replays_named_transforms_from_its_base_audio() -> None:
    """Apply a deterministic transform without accumulating previous UI button presses."""

    controller = AttributionDemoController()
    speech = controller.select_sample("Speech-like sample")
    first = controller.apply_distortions(("White noise (30 dB)",))
    second = controller.apply_distortions(("White noise (30 dB)",))

    assert speech.source_name == "Speech-like sample"
    assert first.applied_distortions == ("White noise (30 dB)",)
    assert (first.current_audio.samples == second.current_audio.samples).all()


def test_registry_accepts_idempotent_local_supplied_handle_registration() -> None:
    """Permit re-encoding one local handle with its same provenance but reject rebinding it."""

    registry = InMemoryAttributionRegistry(b"demo-registry-test-secret")
    handle = bytes.fromhex("AB12CD34")

    entry = registry.register(handle, b"local test")

    assert registry.register(handle, b"local test") == entry
    with pytest.raises(ValueError, match="different provenance"):
        registry.register(handle, b"other provenance")


def test_demo_controller_verifies_v2_block_claims() -> None:
    """Exercise the manual lab's repeated-block attribution path without opening Tkinter."""

    controller = AttributionDemoController()

    embedding = controller.issue_and_encode_blocks("local v2 block test")
    verification = controller.verify()

    assert embedding.record.block_records
    assert verification.recovered
    assert verification.pooled_verification.claim_rs_cost <= 16
    assert controller.state.attribution_mode == "v2_blocks"
    assert controller.state.block_count == len(embedding.record.block_records)
