"""ElevenLabs Scribe v2 Realtime adapter.

Protocol per the API reference (desk check 2026-08-26):
- wss://api.elevenlabs.io/v1/speech-to-text/realtime (regional variants exist,
  including EU) with xi-api-key header auth server-side.
- Send {"message_type": "input_audio_chunk", "audio_base_64": ..., "sample_rate": N}.
- Receive partial_transcript (interim) and committed_transcript(_with_timestamps).
- keyterms IS a documented realtime parameter (up to 50 terms).
- No realtime diarisation: on mixed-mono audio this adapter is out of the
  running by design; use it on separated legs.
"""

from __future__ import annotations

import base64
import json
import os
from collections.abc import AsyncIterator
from urllib.parse import quote

import aiohttp

from .base import STTAdapter, TranscriptEvent

BASES = {
    "us": "wss://api.elevenlabs.io",
    "eu": "wss://api.eu.residency.elevenlabs.io",
}


def parse_message(message: dict[str, object], *, adapter: str, channel: str) -> TranscriptEvent | None:
    """Scribe realtime message -> TranscriptEvent (None for non-transcript)."""
    kind = message.get("message_type")
    if kind == "partial_transcript":
        final = False
    elif kind in ("committed_transcript", "committed_transcript_with_timestamps"):
        final = True
    else:
        return None
    text = str(message.get("text", "")).strip()
    if not text:
        return None
    return TranscriptEvent(adapter=adapter, text=text, final=final, channel=channel, raw=message)


class ScribeAdapter(STTAdapter):
    def __init__(self, language: str = "en", region: str = "us") -> None:
        self.language = language
        self.region = region
        self.name = f"scribe/v2-realtime/{self.region}"

    def _url(self, sample_rate: int, keyterms: list[str] | None) -> str:
        url = (
            f"{BASES[self.region]}/v1/speech-to-text/realtime"
            f"?model_id=scribe_v2_realtime&audio_format=pcm_{sample_rate}"
            f"&language_code={self.language}&commit_strategy=vad"
        )
        for term in (keyterms or [])[:50]:
            url += f"&keyterms={quote(term)}"
        return url

    async def stream(
        self,
        audio: AsyncIterator[bytes],
        *,
        sample_rate: int = 16_000,
        channel: str = "mono",
        keyterms: list[str] | None = None,
    ) -> AsyncIterator[TranscriptEvent]:
        api_key = os.environ["ELEVENLABS_API_KEY"]
        async with (
            aiohttp.ClientSession() as http,
            http.ws_connect(
                self._url(sample_rate, keyterms),
                headers={"xi-api-key": api_key},
                heartbeat=10,
            ) as ws,
        ):
            async def pump() -> None:
                async for chunk in audio:
                    await ws.send_json(
                        {
                            "message_type": "input_audio_chunk",
                            "audio_base_64": base64.b64encode(chunk).decode(),
                            "sample_rate": sample_rate,
                        }
                    )

            import asyncio

            pump_task = asyncio.create_task(pump())
            try:
                async for msg in ws:
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        break
                    event = parse_message(json.loads(msg.data), adapter=self.name, channel=channel)
                    if event:
                        yield event
            finally:
                pump_task.cancel()
