"""Typed loader for `evaluation/gold-questions.json` (Track A4).

Normalizes the **optional** scoring keys to safe empty/None values so every
downstream scorer can read attributes without membership checks on missing keys.
Coded against the live fixture's key union (verified in the P1 checklist), not
the stale IMPLEMENTATION_PLAN.md §7 reference table.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_GOLD_PATH = Path(__file__).resolve().parent.parent / "gold-questions.json"

# Default distinct-claimValue floor for CONFLICT questions when the key is absent
# (checklist B2). Kept here so the scorer and gold loader share one source of truth.
DEFAULT_CONFLICTS_MIN_COUNT = 2


@dataclass(frozen=True)
class GoldQuestion:
    id: int
    category: str
    question: str
    expected_route: str | None
    # Optional scoring keys — always normalized to [] / None so downstream never
    # does a membership check on a missing key.
    required_authors: list[str] = field(default_factory=list)
    required_keywords: list[str] = field(default_factory=list)
    forbidden_patterns: list[str] = field(default_factory=list)
    sql_must_contain: list[str] = field(default_factory=list)
    conflicts_min_count: int | None = None
    min_row_count: int | None = None
    # REFUSAL questions land in P4 (Q16/Q17). The loader tolerates its absence today
    # and its presence later without any scorer change (the whole point of B4).
    refusal_criteria: dict | None = None

    @property
    def is_refusal(self) -> bool:
        """A REFUSAL question — by category, or by carrying refusal_criteria (P4-forward)."""
        return self.category == "REFUSAL" or self.refusal_criteria is not None

    @property
    def effective_conflicts_min_count(self) -> int:
        """conflicts_min_count with the documented default applied (B2)."""
        return (
            self.conflicts_min_count
            if self.conflicts_min_count is not None
            else DEFAULT_CONFLICTS_MIN_COUNT
        )


def _as_str_list(value) -> list[str]:
    """Coerce a possibly-missing JSON value into a list[str] (empty when absent)."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(v) for v in value]
    # Tolerate a scalar written where a list was expected rather than crashing.
    return [str(value)]


def _question_from_dict(d: dict) -> GoldQuestion:
    return GoldQuestion(
        id=int(d["id"]),
        category=str(d["category"]),
        question=str(d["question"]),
        expected_route=(d["expected_route"] if d.get("expected_route") is not None else None),
        required_authors=_as_str_list(d.get("required_authors")),
        required_keywords=_as_str_list(d.get("required_keywords")),
        forbidden_patterns=_as_str_list(d.get("forbidden_patterns")),
        sql_must_contain=_as_str_list(d.get("sql_must_contain")),
        conflicts_min_count=(
            int(d["conflicts_min_count"]) if d.get("conflicts_min_count") is not None else None
        ),
        min_row_count=(int(d["min_row_count"]) if d.get("min_row_count") is not None else None),
        refusal_criteria=(d.get("refusal_criteria") if isinstance(d.get("refusal_criteria"), dict) else None),
    )


def load_gold(path: str | Path = DEFAULT_GOLD_PATH) -> list[GoldQuestion]:
    """Load gold-questions.json (a flat JSON array) into typed GoldQuestion records.

    Raises FileNotFoundError if absent, ValueError if the top level is not a list.
    """
    path = Path(path)
    if not path.is_file():
        raise FileNotFoundError(f"gold-questions.json not found at {path}.")

    data = json.loads(path.read_text())
    if not isinstance(data, list):
        raise ValueError("gold-questions.json must be a flat JSON array of question objects.")

    return [_question_from_dict(d) for d in data]
