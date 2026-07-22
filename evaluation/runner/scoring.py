"""Pure §7 rubric scorer (Track B).

Implements `IMPLEMENTATION_PLAN.md §7` **verbatim** (3 pts/question) plus the
ADR-007 conflict carve-out and ADR-010 per-category aggregation. Every function
is pure over Track-A dataclasses (`GoldQuestion`, `ParsedResponse`) — no network,
no DB — so it is trivially unit-testable. The single external seam is
`row_count_fn`, a `(sql) -> int | None` callable that Track C wires to Track F's
read-only re-executor and tests stub.

Point structure (§7 step 3):
  1. Route match  — routeDecision == expected_route. CONFLICT category is scored
     on conflicts[] instead of route (ADR-007/DEV-014), so its point-1 is the
     conflicts-min check, never a route comparison.
  2. Author/conflict — FACT/MIXED: ≥1 required author in citations[]; CONFLICT:
     ≥ min distinct claimValues (+ per-author guard only when required_authors≥2,
     the Q14 trap); DATA/REFUSAL: auto-1 if route matched.
  3. Content — keyword word-boundary regex over answer (CONFLICT: over
     conflicts[].claimValue), forbidden_patterns any-match = fail, plus the
     per-question Q9 sql_must_contain and Q10 min_row_count guards; REFUSAL uses
     refusal_criteria.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable

from .gold import GoldQuestion
from .model import ParsedResponse

# A (sql) -> row_count callable; None return = the check could not run (fail + note).
RowCountFn = Callable[[str | None], int | None]

# Source-silence phrase list for REFUSAL `must_mention_source_limit` (§7). Seeded
# from §7's examples; kept as a module constant so P4 can extend it without a
# scorer change. Matched case-insensitively as substrings.
SOURCE_SILENCE_PHRASES: tuple[str, ...] = (
    "the texts do not",
    "does not describe",
    "does not give",
    "no surviving account",
    "not preserved",
    "not recorded",
    "do not describe",
    "do not say",
    "does not say",
    "no source",
    "the sources do not",
    "is not described",
    "are silent",
)


# --------------------------------------------------------------------------- #
# Low-level match helpers
# --------------------------------------------------------------------------- #
def _keyword_matches(keyword: str, text: str) -> bool:
    """Word-boundary, case-insensitive keyword match (§7 mandate)."""
    return re.search(r"\b" + re.escape(keyword) + r"\b", text, re.IGNORECASE) is not None


def _all_keywords_match(keywords: list[str], text: str) -> bool:
    """Every required keyword must match; an empty list auto-passes."""
    return all(_keyword_matches(kw, text) for kw in keywords)


def _forbidden_hit(patterns: list[str], text: str) -> bool:
    """True if ANY forbidden pattern appears (case-insensitive substring) in text."""
    lowered = text.lower()
    return any(p.lower() in lowered for p in patterns)


def _author_present(required_author: str, hay: str) -> bool:
    return required_author.lower() in hay.lower()


def _any_required_author_in_citations(required_authors: list[str], resp: ParsedResponse) -> bool:
    """≥1 required author appears (case-insensitive substring) in some citation author."""
    return any(
        _author_present(a, c.author) for a in required_authors for c in resp.citations
    )


def _all_required_authors_in_conflicts(required_authors: list[str], resp: ParsedResponse) -> bool:
    """Every required author appears in ≥1 conflict entry's sourceAuthor (Q13 guard)."""
    return all(
        any(_author_present(a, c.source_author) for c in resp.conflicts)
        for a in required_authors
    )


def _distinct_conflict_values(resp: ParsedResponse) -> int:
    """Count of distinct non-empty claimValues (a degenerate empty value is not a 'version')."""
    return len({c.claim_value.strip() for c in resp.conflicts if c.claim_value.strip()})


def _conflicts_meet_min(q: GoldQuestion, resp: ParsedResponse) -> bool:
    return _distinct_conflict_values(resp) >= q.effective_conflicts_min_count


# --------------------------------------------------------------------------- #
# The three points (§7)
# --------------------------------------------------------------------------- #
def score_route(q: GoldQuestion, resp: ParsedResponse) -> bool:
    """Point 1. CONFLICT is scored on conflicts[] (ADR-007), route ignored entirely."""
    if q.category == "CONFLICT":
        # DEV-014/ADR-007: no route comparison — point-1 is the conflicts-min check,
        # so a route mismatch can neither lose nor gain a point.
        return _conflicts_meet_min(q, resp)
    return resp.route_decision == q.expected_route


def score_author_or_conflict(q: GoldQuestion, resp: ParsedResponse, route_point: bool) -> bool:
    """Point 2, branching on category. DATA/REFUSAL read point-1 (route match)."""
    cat = q.category
    if cat in ("FACT", "MIXED"):
        if not q.required_authors:
            return True  # §7: the author check only applies when authors are specified.
        return _any_required_author_in_citations(q.required_authors, resp)
    if cat == "CONFLICT":
        if not _conflicts_meet_min(q, resp):
            return False
        # Per-author guard ONLY when ≥2 authors listed (the Q14 single-author trap).
        if len(q.required_authors) >= 2:
            return _all_required_authors_in_conflicts(q.required_authors, resp)
        return True
    if cat in ("DATA", "REFUSAL"):
        return route_point  # auto-1 if route matched (§7).
    return False  # unknown category — conservative.


def score_content(q: GoldQuestion, resp: ParsedResponse, row_count_fn: RowCountFn | None = None) -> tuple[bool, list[str]]:
    """Point 3. Returns (passed, notes) — notes surface Q10/Q9 failure reasons for the report."""
    notes: list[str] = []

    if q.category == "REFUSAL":
        return score_refusal(q, resp)

    # Scored text: CONFLICT scores over conflicts[].claimValue (§7); all others over answer.
    # Q18 negative-case exception (DEV-061, resolving the DEV-060-flagged edge at Track H with
    # live evidence): a CONFLICT with conflicts_min_count == 0 is the DEV-052 negative case that
    # correctly EXPECTS an empty conflicts[] (claim-type filtering surfaced no conflict). There is
    # no claimValue text to score against, so its content is scored over `answer` like a FACT
    # question — otherwise the scorer penalizes the exact correct behavior it means to verify.
    if q.category == "CONFLICT" and q.conflicts_min_count != 0:
        scored_text = " ".join(c.claim_value for c in resp.conflicts)
    else:
        scored_text = resp.answer

    # forbidden_patterns: any match anywhere in the scored text = automatic fail (all categories).
    if _forbidden_hit(q.forbidden_patterns, scored_text):
        notes.append("forbidden_pattern matched")
        return False, notes

    # Q10-style: min_row_count re-executes the generated SQL (Track F) — that count IS the point.
    if q.min_row_count is not None:
        if row_count_fn is None:
            notes.append("min_row_count check unavailable (no row_count_fn wired)")
            return False, notes
        count = row_count_fn(resp.sql_generated)
        if count is None:
            notes.append("min_row_count re-execution failed (null/bad sql or timeout)")
            return False, notes
        if count < q.min_row_count:
            notes.append(f"row_count {count} < required {q.min_row_count}")
            return False, notes

    # Keyword check (all must match) over the scored text.
    if not _all_keywords_match(q.required_keywords, scored_text):
        notes.append("required_keywords not all present")
        return False, notes

    # Q9-style: sql_must_contain — null-guard sql_generated FIRST (§7 Q9 note), then token check.
    if q.sql_must_contain:
        sql = resp.sql_generated
        if sql is None:
            notes.append("sql_must_contain: sqlGenerated is null")
            return False, notes
        sql_lower = sql.lower()
        for token in q.sql_must_contain:
            if token.lower() not in sql_lower:
                notes.append(f"sql_must_contain: '{token}' absent from sqlGenerated")
                return False, notes

    return True, notes


def score_refusal(q: GoldQuestion, resp: ParsedResponse) -> tuple[bool, list[str]]:
    """REFUSAL content point (B4) — implemented now though P4 authors the questions.

    All *enabled* refusal_criteria must pass AND no forbidden_patterns match. The
    Phase-1 heuristic for `must_not_fabricate_citation` is an empty citations[] (§2.2);
    the phrase-list + empty-citations shape is preserved so P4 needs no scorer change.
    """
    notes: list[str] = []
    criteria = q.refusal_criteria or {}

    # No forbidden hallucination signatures in the answer.
    if _forbidden_hit(q.forbidden_patterns, resp.answer):
        notes.append("refusal: forbidden_pattern (positive-claim signature) matched")
        return False, notes

    # must_not_assert_answer — reuse forbidden_patterns as the positive-claim signature (§7/B4).
    if criteria.get("must_not_assert_answer") and _forbidden_hit(q.forbidden_patterns, resp.answer):
        notes.append("refusal: asserted an answer (positive-claim signature)")
        return False, notes

    # must_mention_source_limit — a source-silence phrase must be present.
    if criteria.get("must_mention_source_limit"):
        low = resp.answer.lower()
        if not any(p in low for p in SOURCE_SILENCE_PHRASES):
            notes.append("refusal: no source-limit acknowledgement phrase")
            return False, notes

    # must_not_fabricate_citation — Phase-1 heuristic: citations[] must be empty.
    if criteria.get("must_not_fabricate_citation") and resp.citations:
        notes.append("refusal: fabricated citation (citations[] non-empty)")
        return False, notes

    return True, notes


# --------------------------------------------------------------------------- #
# Composition + aggregation
# --------------------------------------------------------------------------- #
@dataclass(frozen=True)
class QuestionScore:
    id: int
    category: str
    expected_route: str | None
    actual_route: str | None
    route_point: bool
    author_point: bool
    content_point: bool
    service_error: bool
    notes: list[str] = field(default_factory=list)

    @property
    def total(self) -> int:
        return int(self.route_point) + int(self.author_point) + int(self.content_point)

    @property
    def passed(self) -> bool:
        """A question 'passes' only at full 3/3 (§7/ADR-010 — full-score, not partial)."""
        return self.total == 3


def score_question(
    q: GoldQuestion, resp: ParsedResponse, row_count_fn: RowCountFn | None = None
) -> QuestionScore:
    """Compose the three points for one question × one response."""
    # serviceError:true → all three points 0, scored fail, no retry (ADR-018 §Decision 4).
    if resp.service_error:
        return QuestionScore(
            id=q.id,
            category=q.category,
            expected_route=q.expected_route,
            actual_route=resp.route_decision,
            route_point=False,
            author_point=False,
            content_point=False,
            service_error=True,
            notes=["serviceError=true → scored fail (all points 0)"],
        )

    route_point = score_route(q, resp)
    author_point = score_author_or_conflict(q, resp, route_point)
    content_point, notes = score_content(q, resp, row_count_fn)

    return QuestionScore(
        id=q.id,
        category=q.category,
        expected_route=q.expected_route,
        actual_route=resp.route_decision,
        route_point=route_point,
        author_point=author_point,
        content_point=content_point,
        service_error=False,
        notes=notes,
    )


@dataclass(frozen=True)
class CategoryRate:
    category: str
    passed: int
    total: int
    floor: float | None

    @property
    def rate(self) -> float:
        return self.passed / self.total if self.total else 0.0

    @property
    def floor_met(self) -> bool | None:
        """None (N/A) when no floor is configured for this category."""
        if self.floor is None:
            return None
        return self.rate >= self.floor


@dataclass(frozen=True)
class Aggregate:
    passed_questions: int
    total_questions: int
    total_points: int
    max_points: int
    overall_target: float
    per_category: list[CategoryRate]
    floor_breaches: list[str]

    @property
    def overall_pass_rate(self) -> float:
        return self.passed_questions / self.total_questions if self.total_questions else 0.0

    @property
    def overall_met(self) -> bool:
        return self.overall_pass_rate >= self.overall_target


def aggregate(
    scores: list[QuestionScore],
    category_floors: dict[str, float | None],
    overall_target: float,
) -> Aggregate:
    """Overall + per-category pass rates (full-3/3 definition) and floor breaches (B6)."""
    passed = sum(1 for s in scores if s.passed)
    total_points = sum(s.total for s in scores)

    # Stable category ordering: first appearance in the score list.
    categories: list[str] = []
    for s in scores:
        if s.category not in categories:
            categories.append(s.category)

    per_category: list[CategoryRate] = []
    breaches: list[str] = []
    for cat in categories:
        cat_scores = [s for s in scores if s.category == cat]
        cr = CategoryRate(
            category=cat,
            passed=sum(1 for s in cat_scores if s.passed),
            total=len(cat_scores),
            floor=category_floors.get(cat),
        )
        per_category.append(cr)
        if cr.floor_met is False:
            breaches.append(cat)

    return Aggregate(
        passed_questions=passed,
        total_questions=len(scores),
        total_points=total_points,
        max_points=3 * len(scores),
        overall_target=overall_target,
        per_category=per_category,
        floor_breaches=breaches,
    )
