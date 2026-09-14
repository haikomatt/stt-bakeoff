# stt-bakeoff

A small, vendor-neutral harness for **measuring** speech-to-text engines
against each other on your own audio, with results you can defend.

It exists because picking an STT vendor from marketing pages is guesswork.
Word error rate on a clean read-aloud corpus tells you very little about how
an engine copes with an elderly caller on a narrowband phone line, which is
the case that usually matters.

**No audio, transcripts or results are committed to this repository.**

## What it does

One shape for every vendor: an adapter turns PCM bytes into `TranscriptEvent`s.
Everything downstream is vendor-blind, so adding a fourth engine is a file
rather than a rewrite.

- `src/adapters/`: Deepgram (US and EU bases), ElevenLabs Scribe v2 Realtime
  (US and EU), Speechmatics (stub).
- `src/channels.py`: mixed-mono against separated legs, from any file ffmpeg
  can read, plus 300 to 3400Hz narrowband simulation for phone-quality audio.
- `src/events.py`: append-only event log and a commit policy: interim results
  never commit, a committed result never silently reverts, corrections are
  first-class events, and state derives by replay.
- `src/scorer.py`: **field-level** accuracy against a gold record. Pooled word
  error rate hides the fields you care about.
- `src/run_bakeoff.py`: the CLI. Audio times adapters times region, to a JSONL
  event log and a summary with partials, finals, first-final latency, and
  errors recorded as findings rather than swallowed.

## What it is not

Not a transcription service, not a benchmark leaderboard, and not a set of
published scores. It is the rig you run on your own audio, because the only
accuracy number worth having is the one measured on the calls you actually
take.

## Quick start

```bash
uv venv && uv pip install aiohttp pytest
.venv/bin/python -m pytest tests/ -q

.venv/bin/python -m src.run_bakeoff --audio audio/your-sample.wav \
    --adapters deepgram,scribe --region us --out runs/first.jsonl \
    --env-file path/to/.env
```

API keys are read from the environment (`DEEPGRAM_API_KEY`,
`ELEVENLABS_API_KEY`). Never commit them.

## Residency

Where audio is processed matters as much as how well it is transcribed. The
adapters carry explicit region selection because "which engine is best" and
"may we lawfully send this audio there" are different questions, and the
second one is usually the binding constraint.

Two practical notes, correct as at September 2026.

**ElevenLabs' EU endpoint is not available on a standard key.** It has to be
enabled on your account by someone in their sales or go-to-market team. Until
it is, a key that works perfectly well elsewhere returns an auth error against
the EU base, which looks like a bug in your code and is not.

**Deepgram's EU endpoint is early access** and has to be requested.

Neither is a base URL swap. Both take a conversation rather than a settings
change, so ask early if EU processing is a requirement rather than a
preference.

## Licence

Apache-2.0.
