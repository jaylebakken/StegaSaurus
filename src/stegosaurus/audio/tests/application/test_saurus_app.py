"""Test the guided Saurus desktop app engine without opening Tkinter.

The desktop surface is intentionally thin.  These checks cover the part that
matters for application behavior: a user-selected WAV plus registry fields
produces an encoded WAV and private JSON sidecar, then decode mode verifies the
encoded WAV against that retained sidecar.
"""

from __future__ import annotations

from saurus_app.registry import RegistryFields, decode_file, default_output_paths, encode_file
from stegosaurus.audio.demo_samples import music_like_sample
from stegosaurus.audio.pilot import write_pcm16_wav


def test_guided_saurus_encode_decode_round_trip(tmp_path) -> None:
    """Encode a clean fixture and verify it with the generated registry sidecar."""

    source_path = tmp_path / "source.wav"
    write_pcm16_wav(source_path, music_like_sample(30))
    output_wav, registry_json = default_output_paths(source_path)

    encoded = encode_file(
        source_path,
        output_wav,
        registry_json,
        RegistryFields("release candidate", "northline promo", "first controlled export"),
    )
    decoded = decode_file(encoded.output_wav, encoded.registry_json)

    assert encoded.output_wav.exists()
    assert encoded.registry_json.exists()
    assert encoded.block_count == 1
    assert decoded.accepted
    assert decoded.recipient == "northline promo"
    assert decoded.project == "release candidate"
