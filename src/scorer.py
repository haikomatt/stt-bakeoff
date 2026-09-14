"""Field-level scorer: accuracy per field, not pooled.

Given a field spec (what kind of comparison each field deserves), a gold
record (what an adviser captured) and an extracted record, score per field.
A transcript can be scruffy and still populate every field correctly; word
error rate is not the metric. This is D5's instrument in miniature and it
outlives every vendor and model change.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

Kind = str  # "exact" | "bool" | "text" | "list" | "number"


def _norm(s: Any) -> str:
    return " ".join(str(s).lower().split())


def _match(kind: Kind, gold: Any, got: Any) -> bool:
    if gold is None and got is None:
        return True
    if gold is None or got is None:
        return False
    if kind == "exact":
        return gold == got
    if kind == "bool":
        return bool(gold) is bool(got)
    if kind == "number":
        try:
            return float(gold) == float(got)
        except (TypeError, ValueError):
            return False
    if kind == "text":
        return _norm(gold) == _norm(got)
    if kind == "list":
        gold_set = {_norm(x) for x in gold}
        got_set = {_norm(x) for x in got}
        if not gold_set and not got_set:
            return True
        union = gold_set | got_set
        return len(gold_set & got_set) / len(union) >= 0.5
    raise ValueError(f"unknown field kind: {kind}")


@dataclass
class FieldScore:
    field: str
    match: bool
    gold: Any
    got: Any


def score_record(
    spec: dict[str, Kind], gold: dict[str, Any], extracted: dict[str, Any]
) -> list[FieldScore]:
    """Score every field in the spec. Fields absent from both count as match
    (not-asked agrees with not-asked); absent from one side is a miss."""
    return [
        FieldScore(
            field=name,
            match=_match(kind, gold.get(name), extracted.get(name)),
            gold=gold.get(name),
            got=extracted.get(name),
        )
        for name, kind in spec.items()
    ]


def summarise(scores: list[FieldScore]) -> dict[str, Any]:
    matched = sum(1 for s in scores if s.match)
    return {
        "fields": len(scores),
        "matched": matched,
        "accuracy": round(matched / len(scores), 3) if scores else None,
        "misses": [s.field for s in scores if not s.match],
    }
