"""Deepgram live adapter (nova family), US and EU bases.

EU note (desk check 2026-08-26): api.eu.deepgram.com is EARLY ACCESS with
claimed feature parity; streaming coverage not explicitly confirmed in the
announcement. region="eu" is wired so the day access is granted the harness
answers the question empirically. Until then expect connection failures on EU
and record them as findings, not errors.
"""

from __future__ import annotations

import json
import os
from collections.abc import AsyncIterator

import aiohttp

from .base import STTAdapter, TranscriptEvent

BASES = {
    "us": "wss://api.deepgram.com",
    "eu": "wss://api.eu.deepgram.com",
}


def parse_message(message: dict[str, object], *, adapter: str, channel: str) -> TranscriptEvent | None:
    """Deepgram Results message -> TranscriptEvent (None for non-results/empty)."""
    if message.get("type") != "Results":
        return None
    channel_data = message.get("channel") or {}
    alternatives = channel_data.get("alternatives") or [{}]  # type: ignore[union-attr]
    text = str(alternatives[0].get("transcript", "")).strip()
    if not text:
        return None
    return TranscriptEvent(
        adapter=adapter,
        text=text,
        final=bool(message.get("is_final")),
        channel=channel,
        raw=message,
    )


class DeepgramAdapter(STTAdapter):
    def __init__(self, model: str = "nova-2", language: str = "en-GB", region: str = "us") -> None:
        self.model = model
        self.language = language
        self.region = region
        self.name = f"deepgram/{model}/{region}"

    def _url(self, sample_rate: int, keyterms: list[str] | None) -> str:
        url = (
            f"{BASES[self.region]}/v1/listen"
            f"?model={self.model}&language={self.language}&encoding=linear16"
            f"&sample_rate={sample_rate}&channels=1"
            "&smart_format=true&interim_results=true&endpointing=400"
        )
        # Deepgram guidance: keyterms are for unseen vocabulary, 20-50 terms
        # recommended (100 max); they do not fix phoneme confusion.
        for term in keyterms or []:
            url += f"&keyterm={term}"
        return url

    async def stream(
        self,
        audio: AsyncIterator[bytes],
        *,
        sample_rate: int = 16_000,
        channel: str = "mono",
        keyterms: list[str] | None = None,
    ) -> AsyncIterator[TranscriptEvent]:
        api_key = os.environ["DEEPGRAM_API_KEY"]
        async with (
            aiohttp.ClientSession() as http,
            http.ws_connect(
                self._url(sample_rate, keyterms),
                headers={"Authorization": f"Token {api_key}"},
                heartbeat=10,
            ) as ws,
        ):
            async def pump() -> None:
                async for chunk in audio:
                    await ws.send_bytes(chunk)
                await ws.send_json({"type": "CloseStream"})

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
