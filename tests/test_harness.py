"""Offline behaviour contracts: adapter parsing, commit policy, scorer."""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from src.adapters.deepgram import parse_message as dg_parse
from src.adapters.scribe import parse_message as sc_parse
from src.events import EventLog, replay
from src.scorer import score_record, summarise


# --- adapter message parsing -------------------------------------------------

def test_deepgram_final_and_interim() -> None:
    msg = {
        "type": "Results",
        "is_final": True,
        "channel": {"alternatives": [{"transcript": "she is eighty four"}]},
    }
    e = dg_parse(msg, adapter="deepgram/nova-2/us", channel="mono")
    assert e and e.final and e.text == "she is eighty four"
    msg["is_final"] = False
    e = dg_parse(msg, adapter="deepgram/nova-2/us", channel="mono")
    assert e and not e.final


def test_deepgram_ignores_metadata_and_empty() -> None:
    assert dg_parse({"type": "Metadata"}, adapter="a", channel="m") is None
    empty = {"type": "Results", "channel": {"alternatives": [{"transcript": ""}]}}
    assert dg_parse(empty, adapter="a", channel="m") is None


def test_scribe_partial_vs_committed() -> None:
    partial = {"message_type": "partial_transcript", "text": "she strug"}
    committed = {"message_type": "committed_transcript", "text": "she struggles"}
    with_ts = {
        "message_type": "committed_transcript_with_timestamps",
        "text": "she struggles",
        "words": [],
    }
    assert sc_parse(partial, adapter="s", channel="m").final is False
    assert sc_parse(committed, adapter="s", channel="m").final is True
    assert sc_parse(with_ts, adapter="s", channel="m").final is True
    assert sc_parse({"message_type": "session_started"}, adapter="s", channel="m") is None


# --- commit policy -----------------------------------------------------------

def test_interims_never_commit(tmp_path: Path) -> None:
    log = EventLog(tmp_path / "e.jsonl")
    log.append("extraction", fields={"name": "Margaret"}, from_final=False)
    assert not replay(log).green("name")


def test_green_never_silently_reverts(tmp_path: Path) -> None:
    log = EventLog(tmp_path / "e.jsonl")
    log.append("extraction", fields={"name": "Margaret"}, from_final=True)
    log.append("extraction", fields={"name": "Marguerite"}, from_final=True)
    state = replay(log)
    assert state.values["name"] == "Marguerite"  # newest value recorded...
    assert state.notices == [{"field": "name", "was": "Margaret", "now": "Marguerite"}]
    # ...but never silently: the change notice is the adviser-facing signal.


def test_corrections_win_and_are_events(tmp_path: Path) -> None:
    log = EventLog(tmp_path / "e.jsonl")
    log.append("extraction", fields={"age_66_plus": False}, from_final=True)
    log.append("correction", field="age_66_plus", value=True)
    assert replay(log).values["age_66_plus"] is True


# --- field scorer ------------------------------------------------------------

SPEC = {"name": "text", "age_66_plus": "bool", "conditions": "list", "duration": "number"}


def test_scorer_field_level() -> None:
    gold = {"name": "Margaret Hale", "age_66_plus": True, "conditions": ["arthritis", "dementia"], "duration": 12}
    got = {"name": "margaret  hale", "age_66_plus": True, "conditions": ["dementia", "arthritis in both hips"], "duration": "12"}
    scores = score_record(SPEC, gold, got)
    by = {s.field: s.match for s in scores}
    assert by["name"] is True          # normalised text
    assert by["age_66_plus"] is True
    assert by["duration"] is True      # "12" == 12
    assert by["conditions"] is False   # jaccard below 0.5 (1 of 3)
    assert summarise(scores)["misses"] == ["conditions"]


def test_scorer_not_asked_agrees() -> None:
    scores = score_record({"duration": "number"}, {}, {})
    assert scores[0].match is True
    scores = score_record({"duration": "number"}, {"duration": 6}, {})
    assert scores[0].match is False
