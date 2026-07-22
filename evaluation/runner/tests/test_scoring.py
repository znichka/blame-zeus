"""Track B7 — pure unit tests for the §7 rubric scorer.

No network, no DB: Track F's row-count is injected as a stub. Covers one pass +
one fail per category, the Q14 single-author skip, the Q10 no-keyword row-count
path, the Q9 sql_must_contain null-guard, a serviceError fail, a forbidden_patterns
trip, and a REFUSAL pass/fail pair.
"""

from __future__ import annotations

from runner.gold import GoldQuestion
from runner.model import Citation, ConflictEntry, ParsedResponse
from runner import scoring
from runner.scoring import aggregate, score_question

FORBIDDEN = ["I don't know", "not in my corpus", "I cannot", "I'm not sure"]


# --------------------------------------------------------------------------- #
# builders
# --------------------------------------------------------------------------- #
def gq(**kw) -> GoldQuestion:
    base = dict(
        id=kw.pop("id", 1),
        category=kw.pop("category", "FACT"),
        question=kw.pop("question", "q?"),
        expected_route=kw.pop("expected_route", "RAG"),
    )
    return GoldQuestion(**base, **kw)


def resp(**kw) -> ParsedResponse:
    return ParsedResponse(
        answer=kw.pop("answer", ""),
        route_decision=kw.pop("route_decision", None),
        citations=kw.pop("citations", []),
        conflicts=kw.pop("conflicts", []),
        sql_generated=kw.pop("sql_generated", None),
        service_error=kw.pop("service_error", False),
        conflicts_in_prose=kw.pop("conflicts_in_prose", False),
    )


def cite(author, work="W", ref="1.1"):
    return Citation(author=author, work=work, passage_ref=ref)


def conf(value, author="A", work="W"):
    return ConflictEntry(claim_value=value, source_author=author, source_work=work)


# --------------------------------------------------------------------------- #
# FACT
# --------------------------------------------------------------------------- #
def test_fact_pass():
    q = gq(category="FACT", expected_route="RAG", required_authors=["Ovid"],
           required_keywords=["spider", "Arachne"], forbidden_patterns=FORBIDDEN)
    r = resp(route_decision="RAG", answer="Arachne became a spider by weaving.",
             citations=[cite("Ovid")])
    s = score_question(q, r)
    assert (s.route_point, s.author_point, s.content_point) == (True, True, True)
    assert s.passed and s.total == 3


def test_fact_fail_wrong_route_and_missing_keyword():
    q = gq(category="FACT", expected_route="RAG", required_authors=["Ovid"],
           required_keywords=["spider"], forbidden_patterns=FORBIDDEN)
    r = resp(route_decision="SQL", answer="A weaving tale.", citations=[cite("Homer")])
    s = score_question(q, r)
    assert (s.route_point, s.author_point, s.content_point) == (False, False, False)


def test_fact_empty_authors_autopass_author_point():
    q = gq(category="FACT", expected_route="RAG", required_authors=[],
           required_keywords=["apple"], forbidden_patterns=FORBIDDEN)
    r = resp(route_decision="RAG", answer="An apple of discord.", citations=[])
    assert score_question(q, r).author_point is True


# --------------------------------------------------------------------------- #
# DATA (incl. Q9 sql_must_contain + Q10 min_row_count via stubbed row counter)
# --------------------------------------------------------------------------- #
def test_data_pass_keywords_and_route():
    q = gq(category="DATA", expected_route="SQL",
           required_keywords=["Zeus", "Hera"], forbidden_patterns=FORBIDDEN)
    r = resp(route_decision="SQL", answer="Zeus, Hera, Poseidon.")
    s = score_question(q, r)
    assert s.passed  # DATA: route→point1+point2, keywords→point3


def test_data_fail_route_mismatch_costs_two_points():
    q = gq(category="DATA", expected_route="SQL", required_keywords=["Zeus"],
           forbidden_patterns=FORBIDDEN)
    r = resp(route_decision="RAG", answer="Zeus.")
    s = score_question(q, r)
    assert (s.route_point, s.author_point) == (False, False)  # author auto-1 only if route matched
    assert s.content_point is True and s.total == 1


def test_q9_sql_must_contain_null_guard():
    q = gq(id=9, category="DATA", expected_route="SQL",
           required_keywords=["Cronus", "Chaos"], sql_must_contain=["WITH RECURSIVE"],
           forbidden_patterns=FORBIDDEN)
    # sql_generated is None → null-guard fails content cleanly, no crash.
    r = resp(route_decision="SQL", answer="Cronus, then Chaos.", sql_generated=None)
    s = score_question(q, r)
    assert s.content_point is False
    assert any("sqlGenerated is null" in n for n in s.notes)
    # With the token present it passes.
    r2 = resp(route_decision="SQL", answer="Cronus, then Chaos.",
              sql_generated="WITH RECURSIVE anc AS (...) SELECT * FROM anc")
    assert score_question(q, r2).content_point is True


def test_q10_min_row_count_no_keywords_uses_row_counter():
    q = gq(id=10, category="DATA", expected_route="SQL", required_keywords=[],
           min_row_count=12, forbidden_patterns=FORBIDDEN)
    r = resp(route_decision="SQL", answer="(table omitted)",
             sql_generated="SELECT * FROM entities WHERE type='olympian'")
    assert score_question(q, r, row_count_fn=lambda sql: 14).content_point is True
    assert score_question(q, r, row_count_fn=lambda sql: 5).content_point is False
    # No counter wired → cannot verify → fail with a note (never a crash).
    s = score_question(q, r, row_count_fn=None)
    assert s.content_point is False and any("unavailable" in n for n in s.notes)


def test_q10_row_counter_failure_is_note_not_crash():
    q = gq(id=10, category="DATA", expected_route="SQL", required_keywords=[],
           min_row_count=12, forbidden_patterns=FORBIDDEN)
    r = resp(route_decision="SQL", answer="x", sql_generated="SELECT 1")
    s = score_question(q, r, row_count_fn=lambda sql: None)  # timeout/bad-sql sentinel
    assert s.content_point is False and any("re-execution failed" in n for n in s.notes)


# --------------------------------------------------------------------------- #
# MIXED
# --------------------------------------------------------------------------- #
def test_mixed_pass():
    q = gq(id=11, category="MIXED", expected_route="MIXED", required_authors=["Homer"],
           required_keywords=["Troy", "divine"], forbidden_patterns=FORBIDDEN)
    r = resp(route_decision="MIXED", answer="Heroes of divine parentage died at Troy.",
             citations=[cite("Homer")])
    assert score_question(q, r).passed


def test_mixed_fail_author_missing():
    q = gq(id=11, category="MIXED", expected_route="MIXED", required_authors=["Homer"],
           required_keywords=["Troy"], forbidden_patterns=FORBIDDEN)
    r = resp(route_decision="MIXED", answer="Troy.", citations=[cite("Ovid")])
    s = score_question(q, r)
    assert s.route_point is True and s.author_point is False


# --------------------------------------------------------------------------- #
# CONFLICT (route-independent; Q13 two-author guard; Q14 single-author skip)
# --------------------------------------------------------------------------- #
def test_conflict_pass_two_authors_q13():
    q = gq(id=13, category="CONFLICT", expected_route="SQL",
           required_authors=["Hesiod", "Homer"], required_keywords=["foam", "Dione"],
           conflicts_min_count=2, forbidden_patterns=FORBIDDEN)
    r = resp(route_decision="SQL",  # route is irrelevant for CONFLICT
             conflicts=[conf("born from sea foam", "Hesiod"), conf("daughter of Zeus and Dione", "Homer")])
    s = score_question(q, r)
    assert (s.route_point, s.author_point, s.content_point) == (True, True, True)


def test_conflict_route_ignored_even_when_wrong():
    q = gq(id=15, category="CONFLICT", expected_route="RAG", required_authors=[],
           required_keywords=["arrow"], conflicts_min_count=2, forbidden_patterns=FORBIDDEN)
    r = resp(route_decision="SQL",  # mismatches expected RAG, but must not cost a point
             conflicts=[conf("shot by an arrow"), conf("felled by Paris and Apollo")])
    assert score_question(q, r).route_point is True


def test_conflict_fail_too_few_distinct_values():
    q = gq(id=13, category="CONFLICT", expected_route="SQL",
           required_authors=["Hesiod", "Homer"], required_keywords=["foam"],
           conflicts_min_count=2, forbidden_patterns=FORBIDDEN)
    r = resp(conflicts=[conf("sea foam", "Hesiod")])  # only 1 distinct value
    s = score_question(q, r)
    assert s.route_point is False and s.author_point is False


def test_conflict_q13_author_guard_trips_when_one_author_absent():
    q = gq(id=13, category="CONFLICT", expected_route="SQL",
           required_authors=["Hesiod", "Homer"], required_keywords=["foam"],
           conflicts_min_count=2, forbidden_patterns=FORBIDDEN)
    # Two distinct values but both by Hesiod → route_point yes, author_point no (Homer absent).
    r = resp(conflicts=[conf("sea foam", "Hesiod"), conf("Zeus and Dione", "Hesiod")])
    s = score_question(q, r)
    assert s.route_point is True and s.author_point is False


def test_conflict_q14_single_author_skips_per_author_guard():
    q = gq(id=14, category="CONFLICT", expected_route="RAG",
           required_authors=["Apollodorus"], required_keywords=["Inachus", "Piren"],
           conflicts_min_count=2, forbidden_patterns=FORBIDDEN)
    # Both variants by Apollodorus; single-author → per-author guard skipped, still passes.
    r = resp(conflicts=[conf("son of Inachus", "Apollodorus"), conf("son of Piren", "Apollodorus")])
    s = score_question(q, r)
    assert (s.route_point, s.author_point, s.content_point) == (True, True, True)


def test_conflict_negative_case_min0_scores_content_over_answer():
    # DEV-061: a conflicts_min_count:0 CONFLICT (Q18 negative case) expects EMPTY conflicts[];
    # its content point is scored over `answer`, not the empty claimValue concat.
    q = gq(id=18, category="CONFLICT", expected_route="RAG", required_authors=["Homer"],
           required_keywords=["Agamemnon"], conflicts_min_count=0, forbidden_patterns=FORBIDDEN)
    r = resp(route_decision="RAG", answer="Achilles withdrew after Agamemnon took Briseis.",
             citations=[cite("Homer")], conflicts=[])
    s = score_question(q, r)
    assert (s.route_point, s.author_point, s.content_point) == (True, True, True)
    assert s.passed


def test_conflict_content_scored_over_claimvalues_not_answer():
    q = gq(id=15, category="CONFLICT", expected_route="RAG", required_authors=[],
           required_keywords=["heel"], conflicts_min_count=2, forbidden_patterns=FORBIDDEN)
    # keyword lives only in a claimValue, answer is empty → still passes.
    r = resp(answer="", conflicts=[conf("arrow to the heel"), conf("killed by Paris")])
    assert score_question(q, r).content_point is True


# --------------------------------------------------------------------------- #
# serviceError + forbidden_patterns
# --------------------------------------------------------------------------- #
def test_service_error_zeroes_all_points():
    q = gq(category="FACT", expected_route="RAG", required_keywords=["x"])
    r = resp(route_decision="RAG", answer="x", service_error=True)
    s = score_question(q, r)
    assert s.service_error and s.total == 0
    assert (s.route_point, s.author_point, s.content_point) == (False, False, False)


def test_forbidden_pattern_trips_content_fail():
    q = gq(category="FACT", expected_route="RAG", required_authors=["Ovid"],
           required_keywords=["spider"], forbidden_patterns=FORBIDDEN)
    r = resp(route_decision="RAG", answer="I don't know, but a spider maybe.",
             citations=[cite("Ovid")])
    s = score_question(q, r)
    assert s.content_point is False and any("forbidden" in n for n in s.notes)


# --------------------------------------------------------------------------- #
# REFUSAL pass/fail pair (authored in P4, scored now)
# --------------------------------------------------------------------------- #
REFUSAL_CRITERIA = {
    "must_not_assert_answer": True,
    "must_mention_source_limit": True,
    "must_not_fabricate_citation": True,
}


def test_refusal_pass():
    q = gq(id=16, category="REFUSAL", expected_route="RAG",
           refusal_criteria=REFUSAL_CRITERIA,
           forbidden_patterns=["his hair was", "he had", "described as"])
    r = resp(route_decision="RAG",
             answer="The texts do not describe his physical appearance.", citations=[])
    s = score_question(q, r)
    assert s.route_point is True   # route matches RAG
    assert s.author_point is True  # REFUSAL author = route matched
    assert s.content_point is True


def test_refusal_fail_fabricated_citation_and_no_source_limit():
    q = gq(id=16, category="REFUSAL", expected_route="RAG",
           refusal_criteria=REFUSAL_CRITERIA,
           forbidden_patterns=["his hair was", "he had", "described as"])
    r = resp(route_decision="RAG",
             answer="He had golden hair.", citations=[cite("Homer")])
    s = score_question(q, r)
    # forbidden 'he had' + fabricated citation + no source-limit phrase → content fail.
    assert s.content_point is False


# --------------------------------------------------------------------------- #
# aggregate: overall + per-category floors
# --------------------------------------------------------------------------- #
def test_aggregate_pass_rates_and_floor_breach():
    def qs(cat, passed):
        return scoring.QuestionScore(
            id=0, category=cat, expected_route="RAG", actual_route="RAG",
            route_point=passed, author_point=passed, content_point=passed,
            service_error=False,
        )
    scores = [qs("FACT", True), qs("FACT", False),
              qs("CONFLICT", True), qs("CONFLICT", False)]
    agg = aggregate(scores, category_floors={"CONFLICT": 0.75, "DATA": None}, overall_target=0.75)
    assert agg.passed_questions == 2 and agg.total_questions == 4
    assert abs(agg.overall_pass_rate - 0.5) < 1e-9 and agg.overall_met is False
    conflict = next(c for c in agg.per_category if c.category == "CONFLICT")
    assert conflict.rate == 0.5 and conflict.floor_met is False
    assert "CONFLICT" in agg.floor_breaches


def test_aggregate_none_floor_is_na_never_breach():
    def qs(cat, passed):
        return scoring.QuestionScore(
            id=0, category=cat, expected_route="RAG", actual_route="RAG",
            route_point=passed, author_point=passed, content_point=passed,
            service_error=False,
        )
    agg = aggregate([qs("REFUSAL", False)], category_floors={"REFUSAL": None}, overall_target=0.75)
    ref = next(c for c in agg.per_category if c.category == "REFUSAL")
    assert ref.floor_met is None and agg.floor_breaches == []
