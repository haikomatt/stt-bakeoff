"""Speechmatics realtime adapter — STUB pending a trial key.

Desk check 2026-08-26: UK and EU cloud regions confirmed, on-prem CPU/GPU
containers and air-gapped deployment documented; as a UK/EU company it is the
production-residency conservative choice and the only candidate with realtime
diarisation for mixed-mono audio. The websocket protocol (RT API v2) gets
implemented the day the trial key arrives; the interface is pinned now so it
drops in beside the others.
"""

from __future__ import annotations

from collections.abc import AsyncIterator

from .base import STTAdapter, TranscriptEvent


class SpeechmaticsAdapter(STTAdapter):
    name = "speechmatics/rt/stub"

    async def stream(
        self,
        audio: AsyncIterator[bytes],
        *,
        sample_rate: int = 16_000,
        channel: str = "mono",
        keyterms: list[str] | None = None,
    ) -> AsyncIterator[TranscriptEvent]:
        raise NotImplementedError(
            "Speechmatics adapter awaits a trial key (Matt unblocker, "
            "tracked in the vault hypothesis queue as H2)."
        )
        yield  # pragma: no cover — makes this an async generator
