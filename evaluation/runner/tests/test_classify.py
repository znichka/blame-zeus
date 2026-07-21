"""Track C7 — pure classification/aggregate tests + stubbed-transport HTTP tests.

No live server: the transport is a recording stub, so retry/serviceError/preflight
logic is exercised without a network.
"""

from __future__ import annotations

import pytest

from runner import __main__ as cli
from runner.__main__ import TransportError, preflight, query_once
from runner.classify import (
    FLAKY,
    STABLE_FAIL,
    STABLE_PASS,
    classify_all,
    classify_question,
    worst_run_aggregate,
)
from runner.config import load_config
from runner.scoring import QuestionScore

CFG = load_config()


def qscore(qid, passed, category="FACT", total=None):
    pts = (3 if passed else 0) if total is None else total
    # spread the points across the three booleans deterministically
    bools = [pts >= 1, pts >= 2, pts >= 3]
    return QuestionScore(
        id=qid, category=category, expected_route="RAG", actual_route="RAG",
        route_point=bools[0], author_point=bools[1], content_point=bools[2],
        service_error=False,
    )


# --------------------------------------------------------------------------- #
# classification
# --------------------------------------------------------------------------- #
def test_classify_question_stable_pass_fail_flaky():
    assert classify_question([qscore(1, True), qscore(1, True)]).label == STABLE_PASS
    assert classify_question([qscore(1, False), qscore(1, False)]).label == STABLE_FAIL
    assert classify_question([qscore(1, True), qscore(1, False)]).label == FLAKY


def test_classify_all_transposes_by_id():
    run1 = [qscore(1, True), qscore(2, True)]
    run2 = [qscore(2, False), qscore(1, True)]  # reordered on purpose
    cls = classify_all([run1, run2])
    by_id = {c.id: c for c in cls}
    assert by_id[1].label == STABLE_PASS
    assert by_id[2].label == FLAKY
    # question order follows the first run
    assert [c.id for c in cls] == [1, 2]


def test_classify_all_misaligned_runs_raise():
    with pytest.raises(ValueError):
        classify_all([[qscore(1, True)], [qscore(2, True)]])


# --------------------------------------------------------------------------- #
# worst-run pessimistic aggregate
# --------------------------------------------------------------------------- #
def test_worst_run_picks_fewest_passes():
    good_run = [qscore(1, True), qscore(2, True)]
    bad_run = [qscore(1, True), qscore(2, False)]
    idx, agg = worst_run_aggregate([good_run, bad_run], category_floors={}, overall_target=0.75)
    assert idx == 1 and agg.passed_questions == 1


def test_worst_run_tiebreaks_on_total_points():
    # both runs pass 0 questions, but run B has fewer total points → worse
    run_a = [qscore(1, False, total=2)]  # 2 pts, not a full pass
    run_b = [qscore(1, False, total=0)]  # 0 pts
    idx, agg = worst_run_aggregate([run_a, run_b], category_floors={}, overall_target=0.75)
    assert idx == 1 and agg.total_points == 0


# --------------------------------------------------------------------------- #
# HTTP transport: retry / serviceError / status handling (C3)
# --------------------------------------------------------------------------- #
class StubTransport:
    """Returns programmed (status, parsed) per call, or raises TransportError."""

    def __init__(self, outcomes):
        self._outcomes = list(outcomes)
        self.calls = []

    def __call__(self, method, url, body, timeout):
        self.calls.append((method, url, body))
        outcome = self._outcomes.pop(0)
        if isinstance(outcome, Exception):
            raise outcome
        return outcome


def test_query_once_success_parses_response():
    t = StubTransport([(200, {"answer": "hi", "routeDecision": "RAG"})])
    raw, parsed = query_once(CFG, "q?", debug=False, transport=t)
    assert parsed.answer == "hi" and parsed.route_decision == "RAG"
    assert parsed.service_error is False and len(t.calls) == 1


def test_query_once_service_error_is_not_retried():
    t = StubTransport([(200, {"serviceError": True, "answer": ""})])
    raw, parsed = query_once(CFG, "q?", debug=False, transport=t)
    assert parsed.service_error is True and len(t.calls) == 1  # NO retry


def test_query_once_5xx_retries_once_then_synthetic_fail():
    t = StubTransport([(503, None), (503, None)])
    raw, parsed = query_once(CFG, "q?", debug=False, transport=t)
    assert parsed.service_error is True and len(t.calls) == 2  # one retry
    assert raw.get("_runnerNote", "").startswith("HTTP 503")


def test_query_once_transport_error_retries_then_recovers():
    t = StubTransport([TransportError("refused"), (200, {"answer": "ok", "routeDecision": "SQL"})])
    raw, parsed = query_once(CFG, "q?", debug=False, transport=t)
    assert parsed.answer == "ok" and len(t.calls) == 2


def test_query_once_4xx_not_retried():
    t = StubTransport([(400, {"error": "bad"})])
    raw, parsed = query_once(CFG, "q?", debug=False, transport=t)
    assert parsed.service_error is True and len(t.calls) == 1  # 4xx not retried


# --------------------------------------------------------------------------- #
# preflight (C2)
# --------------------------------------------------------------------------- #
def test_preflight_ok_with_seeded_sources():
    t = StubTransport([(200, [{"id": "hesiod-theogony"}, {"id": "homer-iliad"}])])
    ok, msg = preflight(CFG, t)
    assert ok is True and "2 sources" in msg


def test_preflight_fails_on_empty_source_list():
    t = StubTransport([(200, [])])
    ok, msg = preflight(CFG, t)
    assert ok is False and "not seeded" in msg


def test_preflight_fails_on_non_200():
    t = StubTransport([(500, None)])
    assert preflight(CFG, t)[0] is False


def test_preflight_fails_on_transport_error():
    t = StubTransport([TransportError("connection refused")])
    ok, msg = preflight(CFG, t)
    assert ok is False and "unreachable" in msg


# --------------------------------------------------------------------------- #
# run_all end-to-end with a stub transport + stub row-counter (no server, no DB)
# --------------------------------------------------------------------------- #
def test_run_all_produces_scored_classified_results():
    from runner.gold import GoldQuestion

    q = GoldQuestion(id=1, category="FACT", question="q?", expected_route="RAG",
                     required_authors=["Ovid"], required_keywords=["spider"],
                     forbidden_patterns=[])
    # same good answer every run → stable-pass
    t = StubTransport([
        (200, {"answer": "a spider", "routeDecision": "RAG",
               "citations": [{"author": "Ovid", "work": "Met", "passageRef": "1.1"}]}),
        (200, {"answer": "a spider", "routeDecision": "RAG",
               "citations": [{"author": "Ovid", "work": "Met", "passageRef": "1.1"}]}),
    ])
    results = cli.run_all(CFG, [q], runs=2, debug=False, transport=t, row_count_fn=lambda s: 0)
    assert results.runs == 2
    assert results.classifications[0].label == STABLE_PASS
    assert results.aggregate.passed_questions == 1
    assert len(results.raw_by_run) == 2 and len(results.scores_by_run) == 2
