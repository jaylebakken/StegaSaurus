"""Run deterministic external codec round trips for named evaluations.

This module isolates the FFmpeg boundary. The benchmark records a named MP3
round trip as one measured transformation; it does not infer robustness to
other codecs, bitrates, encoder versions, or arbitrary resynthesis.

Toy example:
    decoded = mp3_round_trip(audio, bitrate_kbps=96)
"""

from __future__ import annotations

from numbers import Integral
from pathlib import Path
import subprocess
from tempfile import TemporaryDirectory

from .pilot import PcmAudio, read_pcm16_wav, write_pcm16_wav

class AudioToolUnavailable(RuntimeError):
    """Report a requested external audio transformation without its required tool."""


def mp3_round_trip(audio: PcmAudio, bitrate_kbps: int) -> PcmAudio:
    """Encode mono PCM audio as MP3 and decode deterministic mono PCM at its original rate."""

    if isinstance(bitrate_kbps, bool) or not isinstance(bitrate_kbps, Integral):
        raise TypeError("bitrate_kbps must be an integer")
    if not 8 <= bitrate_kbps <= 320:
        raise ValueError("bitrate_kbps must be between 8 and 320")
    ffmpeg_path = _ffmpeg_path()
    with TemporaryDirectory(prefix="stegosaurus-audio-") as directory_name:
        directory = Path(directory_name)
        source_path = directory / "source.wav"
        mp3_path = directory / "transcoded.mp3"
        decoded_path = directory / "decoded.wav"
        write_pcm16_wav(source_path, audio)
        _run_ffmpeg(
            ffmpeg_path,
            "-fflags",
            "+bitexact",
            "-i",
            str(source_path),
            "-vn",
            "-map_metadata",
            "-1",
            "-ac",
            "1",
            "-ar",
            str(audio.sample_rate),
            "-codec:a",
            "libmp3lame",
            "-b:a",
            f"{bitrate_kbps}k",
            str(mp3_path),
        )
        _run_ffmpeg(
            ffmpeg_path,
            "-fflags",
            "+bitexact",
            "-i",
            str(mp3_path),
            "-vn",
            "-map_metadata",
            "-1",
            "-acodec",
            "pcm_s16le",
            "-ac",
            "1",
            "-ar",
            str(audio.sample_rate),
            str(decoded_path),
        )
        return read_pcm16_wav(decoded_path)



def _ffmpeg_path() -> str:
    """Return the optional bundled FFmpeg executable or raise an actionable error."""

    try:
        import imageio_ffmpeg
    except ImportError as error:
        raise AudioToolUnavailable(
            "MP3 evaluation requires the optional audio dependency imageio-ffmpeg"
        ) from error
    ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    if not Path(ffmpeg_path).is_file():
        raise AudioToolUnavailable("imageio-ffmpeg did not provide an executable FFmpeg path")
    return ffmpeg_path


def _run_ffmpeg(ffmpeg_path: str, *arguments: str) -> None:
    """Run FFmpeg non-interactively and raise a concise error on transformation failure."""

    try:
        completed = subprocess.run(
            (ffmpeg_path, "-hide_banner", "-loglevel", "error", "-nostdin", "-y", *arguments),
            capture_output=True,
            text=True,
            check=False,
        )
    except OSError as error:
        raise AudioToolUnavailable(f"unable to run FFmpeg: {error}") from error
    if completed.returncode:
        detail = completed.stderr.strip() or "FFmpeg returned no diagnostic output"
        raise RuntimeError(f"FFmpeg audio transformation failed: {detail}")


