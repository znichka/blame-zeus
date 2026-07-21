"""Track D6 — artifact writer tests (no server, no DB).

Builds a synthetic RunResults, writes to a tmp dir with injected timestamp/sha,
and asserts the three files exist, scores.json round-trips, and report.md carries
the header + every question row + the triage column.
"""

from __future__ import annotations

import json
from datetime import datetime, timezone

from runner import report
from runner.classify import RunResults, classify_all, worst_run_aggregate
from runner.config import load_config
from runner.gold import GoldQuestion
from runner.scoring import QuestionScore

CFG = load_config()


def _score(qid, category, expected, actual, r, a, c, service_error=False, notes=None):
    return QuestionScore(
        id=qid, category=category, expected_route=expected, actual_route=actual,
        route_point=r, author_point=a, content_point=c, service_error=service_error,
        notes=notes or [],
    )


def _build_results(label="baseline"):
    questions = [
        GoldQuestion(id=1, category="FACT", question="Q1?", expected_route="RAG"),
        GoldQuestion(id=13, category="CONFLICT", question="Q13?", expected_route="SQL"),
    ]
    # run 0: Q1 pass, Q13 pass ; run 1: Q1 pass, Q13 fail  → Q13 flaky, worst run = run 1
    run0 = [
        _score(1, "FACT", "RAG", "RAG", True, True, True),
        _score(13, "CONFLICT", "SQL", "SQL", True, True, True),
    ]
    run1 = [
        _score(1, "FACT", "RAG", "RAG", True, True, True),
        _score(13, "CONFLICT", "SQL", "RAG", False, False, False, notes=["too few conflicts"]),
    ]
    scores_by_run = [run0, run1]
    raw_by_run = [
        [{"answer": "a", "conflicts": [{"claimValue": "x"}, {"claimValue": "y"}]},
         {"answer": "b", "conflicts": [{"claimValue": "p"}, {"claimValue": "q"}]}],
        [{"answer": "a", "conflicts": []},
         {"answer": "b", "conflicts": [{"claimValue": "p"}]}],
    ]
    classifications = classify_all(scores_by_run)
    worst_idx, worst_agg = worst_run_aggregate(scores_by_run, CFG.category_floors, CFG.overall_target)
    return RunResults(
        label=label, runs=2, base_url="http://localhost:8080",
        questions=questions, raw_by_run=raw_by_run, scores_by_run=scores_by_run,
        classifications=classifications, worst_run_index=worst_idx, aggregate=worst_agg,
    )


def test_write_produces_three_files(tmp_path):
    results = _build_results()
    out = report.write(
        results, CFG, results_root=tmp_path,
        now=datetime(2026, 7, 21, 14, 3, 11, tzinfo=timezone.utc), git_sha="abc1234",
    )
    assert out.name == "2026-07-21T14-03-11Z__abc1234__baseline"
    assert (out / "raw_responses.json").is_file()
    assert (out / "scores.json").is_file()
    assert (out / "report.md").is_file()


def test_scores_json_round_trips_and_carries_key_fields(tmp_path):
    results = _build_results()
    out = report.write(results, CFG, results_root=tmp_path, git_sha="deadbee")
    data = json.loads((out / "scores.json").read_text())  # round-trips (valid JSON)

    assert data["label"] == "baseline" and data["runs"] == 2 and data["git_sha"] == "deadbee"
    assert data["flaky_ids"] == [13]
    agg = data["aggregate"]
    # worst run (#1) passes only Q1 → 1/2
    assert agg["passed_questions"] == 1 and agg["total_questions"] == 2
    assert agg["worst_run_index"] == 1
    q13 = next(q for q in data["questions"] if q["id"] == 13)
    assert q13["classification"] == "flaky"
    assert [r["conflicts_count"] for r in q13["per_run"]] == [2, 1]  # from raw, per run
    assert q13["per_run"][1]["notes"] == ["too few conflicts"]


def test_raw_responses_preserved_verbatim(tmp_path):
    results = _build_results()
    out = report.write(results, CFG, results_root=tmp_path, git_sha="x")
    raw = json.loads((out / "raw_responses.json").read_text())
    assert raw["runs"] == 2
    # run 0 Q1 conflicts preserved exactly
    assert raw["responses_by_run"][0][0]["conflicts"] == [{"claimValue": "x"}, {"claimValue": "y"}]


def test_report_md_has_header_rows_and_triage_column(tmp_path):
    results = _build_results()
    out = report.write(results, CFG, results_root=tmp_path, git_sha="abc1234")
    md = (out / "report.md").read_text()

    assert "# Evaluation Report — baseline" in md
    assert "Overall (pessimistic" in md
    assert "triage" in md  # the triage column header
    # a row per question, anchored by id
    assert "| 1 | FACT |" in md
    assert "| 13 | CONFLICT |" in md
    # worst-run actual route for Q13 was RAG (the failing run)
    assert "| SQL | RAG |" in md
    # class column shows flaky for Q13
    assert "flaky" in md
