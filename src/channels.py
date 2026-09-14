"""Audio sources: channel configuration is the variable that matters most.

Two shapes, both from any file ffmpeg can read:
- mono_source: everything mixed down to one s16le stream (the hard case).
- leg_sources: a stereo file split into two mono streams, one per call leg
  (the easy case; diarisation becomes unnecessary).

Also make_narrowband: simulate the 8kHz telephony path, because a clean
studio sample tests the wrong thing.
"""

from __future__ import annotations

import asyncio
import contextlib
import subprocess
from collections.abc import AsyncIterator
from pathlib import Path

CHUNK_MS = 100


async def _ffmpeg_pcm(
    path: Path, sample_rate: int, *, realtime: bool, extra: list[str]
) -> AsyncIterator[bytes]:
    pacing = ["-re"] if realtime else []
    cmd = [
        "ffmpeg", "-v", "error", *pacing, "-i", str(path), *extra,
        "-f", "s16le", "-ar", str(sample_rate), "-",
    ]
    proc = await asyncio.create_subprocess_exec(
        *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL
    )
    assert proc.stdout is not None
    chunk_bytes = sample_rate * CHUNK_MS // 1000 * 2
    try:
        while True:
            chunk = await proc.stdout.read(chunk_bytes)
            if not chunk:
                break
            yield chunk
    finally:
        with contextlib.suppress(ProcessLookupError):
            proc.terminate()
        await proc.wait()


def mono_source(path: Path, sample_rate: int = 16_000, *, realtime: bool = False) -> AsyncIterator[bytes]:
    """The whole file mixed down to one mono stream."""
    return _ffmpeg_pcm(path, sample_rate, realtime=realtime, extra=["-ac", "1"])


def leg_sources(
    path: Path, sample_rate: int = 16_000, *, realtime: bool = False
) -> tuple[AsyncIterator[bytes], AsyncIterator[bytes]]:
    """A stereo file as two mono streams: (left leg, right leg)."""
    left = _ffmpeg_pcm(
        path, sample_rate, realtime=realtime,
        extra=["-af", "pan=mono|c0=c0"],
    )
    right = _ffmpeg_pcm(
        path, sample_rate, realtime=realtime,
        extra=["-af", "pan=mono|c0=c1"],
    )
    return left, right


def make_narrowband(source: Path, dest: Path) -> None:
    """Telephony simulation: band-limit to 300-3400Hz through an 8kHz path."""
    subprocess.run(
        [
            "ffmpeg", "-y", "-v", "error", "-i", str(source),
            "-af", "highpass=f=300,lowpass=f=3400",
            "-ar", "8000", "-ac", "1", str(dest),
        ],
        check=True,
    )
