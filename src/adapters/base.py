"""The adapter interface: one shape for every STT vendor.

An adapter turns a stream of raw PCM bytes into a stream of TranscriptEvents.
Everything downstream (event log, commit policy, scorer) sees only this shape,
so a fourth vendor is a new file, not a rewrite — the design requirement the
harness exists to prove.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from collections.abc import AsyncIterator
from dataclasses import dataclass, field


@dataclass
class TranscriptEvent:
    """One transcript message from a vendor, normalised.

    final=False is an interim/partial (display-only downstream; the commit
    policy ignores them by design). final=True is a vendor-committed segment.
    """

    adapter: str
    text: str
    final: bool
    channel: str = "mono"
    at: float = field(default_factory=time.monotonic)
    raw: dict[str, object] | None = None


class STTAdapter(ABC):
    """Streams PCM in, yields TranscriptEvents out."""

    name: str = "base"

    @abstractmethod
    def stream(
        self,
        audio: AsyncIterator[bytes],
        *,
        sample_rate: int = 16_000,
        channel: str = "mono",
        keyterms: list[str] | None = None,
    ) -> AsyncIterator[TranscriptEvent]:
        """Consume s16le mono PCM at sample_rate; yield events as they arrive."""
        raise NotImplementedError
