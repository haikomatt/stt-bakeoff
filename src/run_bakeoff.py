"""Run one or more STT adapters over an audio file; log every event.

Usage (from repo root, env vars DEEPGRAM_API_KEY / ELEVENLABS_API_KEY set,
or --env-file pointing at a dotenv):

  .venv/bin/python -m src.run_bakeoff --audio audio/sample.wav \
      --adapters deepgram,scribe --region us --out runs/first.jsonl

Channel modes: --channels mono (default) mixes everything down; --channels
legs splits a stereo file into two streams and runs the adapter once per leg.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import time
from pathlib import Path

from .adapters.base import STTAdapter
from .adapters.deepgram import DeepgramAdapter
from .adapters.scribe import ScribeAdapter
from .adapters.speechmatics import SpeechmaticsAdapter
from .channels import leg_sources, mono_source
from .events import EventLog


def build_adapter(name: str, region: str) -> STTAdapter:
    if name == "deepgram":
        return DeepgramAdapter(region=region)
    if name == "scribe":
        return ScribeAdapter(region=region)
    if name == "speechmatics":
        return SpeechmaticsAdapter()
    raise SystemExit(f"unknown adapter: {name}")


async def run_one(
    adapter: STTAdapter, audio, log: EventLog, *, sample_rate: int, channel: str
) -> dict[str, object]:
    started = time.monotonic()
    partials = finals = 0
    first_final: float | None = None
    try:
        async for event in adapter.stream(audio, sample_rate=sample_rate, channel=channel):
            if event.final:
                finals += 1
                if first_final is None:
                    first_final = round(time.monotonic() - started, 2)
            else:
                partials += 1
            log.append(
                "transcript",
                adapter=event.adapter,
                channel=event.channel,
                text=event.text,
                final=event.final,
            )
    except Exception as exc:  # a vendor failure is a finding, not a crash
        log.append("adapter_error", adapter=adapter.name, channel=channel, error=repr(exc))
        return {"adapter": adapter.name, "channel": channel, "error": repr(exc)}
    return {
        "adapter": adapter.name,
        "channel": channel,
        "partials": partials,
        "finals": finals,
        "first_final_s": first_final,
        "wall_s": round(time.monotonic() - started, 2),
    }


async def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--audio", required=True, type=Path)
    parser.add_argument("--adapters", default="deepgram")
    parser.add_argument("--region", default="us", choices=["us", "eu"])
    parser.add_argument("--channels", default="mono", choices=["mono", "legs"])
    parser.add_argument("--sample-rate", type=int, default=16_000)
    parser.add_argument("--realtime", action="store_true", help="pace at 1x")
    parser.add_argument("--out", type=Path, default=Path("runs/bakeoff.jsonl"))
    parser.add_argument("--env-file", type=Path, help="dotenv to load keys from")
    args = parser.parse_args()

    if args.env_file:
        for line in args.env_file.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, value = line.partition("=")
                os.environ.setdefault(key.strip(), value.strip().strip('"'))

    args.out.parent.mkdir(parents=True, exist_ok=True)
    log = EventLog(args.out)
    results = []
    for name in args.adapters.split(","):
        adapter = build_adapter(name.strip(), args.region)
        if args.channels == "legs":
            left, right = leg_sources(args.audio, args.sample_rate, realtime=args.realtime)
            results.append(
                await run_one(adapter, left, log, sample_rate=args.sample_rate, channel="leg-a")
            )
            adapter2 = build_adapter(name.strip(), args.region)
            results.append(
                await run_one(adapter2, right, log, sample_rate=args.sample_rate, channel="leg-b")
            )
        else:
            audio = mono_source(args.audio, args.sample_rate, realtime=args.realtime)
            results.append(
                await run_one(adapter, audio, log, sample_rate=args.sample_rate, channel="mono")
            )
    for r in results:
        print(r)


if __name__ == "__main__":
    asyncio.run(main())
