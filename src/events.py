"""Append-only event log and the commit policy for green.

The product rule this module pins (and the tests enforce):
- Only vendor-final segments may change field state. Interims never commit.
- Once a field is green it never silently reverts; a conflicting later value
  raises a change notice for the adviser instead of overwriting quietly.
- Corrections are first-class events: the correction corpus is a by-product
  of the log, not a separate exercise.

State is always derived by replaying the log, so when models change the
history re-scores for free.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


@dataclass
class EventLog:
    """Append-only JSONL sink; the single source of truth for a run."""

    path: Path
    _events: list[dict[str, Any]] = field(default_factory=list)

    def append(self, kind: str, **payload: Any) -> dict[str, Any]:
        event = {"at": time.time(), "kind": kind, **payload}
        self._events.append(event)
        with self.path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event) + "\n")
        return event

    @property
    def events(self) -> list[dict[str, Any]]:
        return list(self._events)


@dataclass
class FieldState:
    """Derived field state under the commit policy."""

    values: dict[str, Any] = field(default_factory=dict)
    notices: list[dict[str, Any]] = field(default_factory=list)

    def green(self, name: str) -> bool:
        return name in self.values

    def apply_extraction(
        self, fields: dict[str, Any], *, from_final: bool
    ) -> list[dict[str, Any]]:
        """Apply extracted fields; returns the change notices raised (if any).

        Interim-derived extractions are ignored entirely: green only ever
        comes from a finalised segment.
        """
        raised: list[dict[str, Any]] = []
        if not from_final:
            return raised
        for name, value in fields.items():
            if value is None:
                continue
            if name in self.values and self.values[name] != value:
                notice = {"field": name, "was": self.values[name], "now": value}
                self.notices.append(notice)
                raised.append(notice)
                # The new value is recorded, but never silently: the notice
                # is the adviser-facing signal the display must surface.
            self.values[name] = value
        return raised

    def apply_correction(self, name: str, value: Any) -> None:
        """An adviser correction always wins and is always recorded."""
        self.values[name] = value


def replay(log: EventLog) -> FieldState:
    """Derive current field state from the log alone."""
    state = FieldState()
    for event in log.events:
        if event["kind"] == "extraction":
            state.apply_extraction(event["fields"], from_final=event["from_final"])
        elif event["kind"] == "correction":
            state.apply_correction(event["field"], event["value"])
    return state
