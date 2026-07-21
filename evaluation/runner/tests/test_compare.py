"""Track E5 — compare/diff tests.

Synthetic baseline/candidate scores dicts (Track D's schema) covering: a stable
regression (listed + nonzero exit), a flaky flip (informational only), an
improvement, per-category delta, route change, and conflict-count change.
"""

from __future__ import annotations

import json

from runner import compare
from runner.compare import compute_diff, main, render_diff_md


def q(qid, classification, route="RAG", conflicts=0, category="FACT"):
    return {
        "id": qid,
        "category": category,
        "classification": classification,
        "per_run": [{"actual_route": route, "conflicts_count": conflicts}],
    }


def scores(questions, worst_idx=0, per_category=None, label="run", sha="abc"):
    return {
        "label": label,
        "git_sha": sha,
        "aggregate": {
            "worst_run_index": worst_idx,
            "passed_questions": sum(1 for x in questions if x["classification"] == "stable-pass"),
            "total_questions": len(questions),
            "overall_pass_rate": 0.0,
            "per_category": per_category or [],
        },
        "questions": questions,
    }


# --------------------------------------------------------------------------- #
# classification transitions
# --------------------------------------------------------------------------- #
def test_stable_regression_is_flagged():
    base = scores([q(1, "stable-pass")])
    cand = scores([q(1, "stable-fail")])
    diff = compute_diff(base, cand)
    assert diff.has_regression
    assert diff.regressions[0]["id"] == 1
    assert diff.improvements == [] and diff.flaky_flips == []


def test_flaky_flip_is_informational_not_regression():
    base = scores([q(1, "stable-pass")])
    cand = scores([q(1, "flaky")])
    diff = compute_diff(base, cand)
    assert not diff.has_regression
    assert diff.flaky_flips[0]["id"] == 1
    # the reverse (flaky → stable-fail) is also not a regression
    diff2 = compute_diff(scores([q(1, "flaky")]), scores([q(1, "stable-fail")]))
    assert not diff2.has_regression and diff2.flaky_flips[0]["id"] == 1


def test_improvement_detected():
    diff = compute_diff(scores([q(1, "stable-fail")]), scores([q(1, "stable-pass")]))
    assert not diff.has_regression and diff.improvements[0]["id"] == 1


def test_no_change_when_both_stable_pass():
    diff = compute_diff(scores([q(1, "stable-pass")]), scores([q(1, "stable-pass")]))
    assert not diff.has_regression and diff.improvements == [] and diff.flaky_flips == []


# --------------------------------------------------------------------------- #
# route / conflict-count / category deltas
# --------------------------------------------------------------------------- #
def test_route_change_detected():
    base = scores([q(1, "stable-pass", route="SQL")])
    cand = scores([q(1, "stable-pass", route="RAG")])
    diff = compute_diff(base, cand)
    assert diff.route_changes == [{"id": 1, "from": "SQL", "to": "RAG"}]


def test_conflict_count_change_detected():
    base = scores([q(1, "stable-pass", conflicts=2)])
    cand = scores([q(1, "stable-pass", conflicts=0)])
    diff = compute_diff(base, cand)
    assert diff.conflict_count_changes == [{"id": 1, "from": 2, "to": 0}]


def test_category_delta_detected():
    base = scores([q(1, "stable-pass", category="CONFLICT")],
                  per_category=[{"category": "CONFLICT", "rate": 0.5}])
    cand = scores([q(1, "stable-pass", category="CONFLICT")],
                  per_category=[{"category": "CONFLICT", "rate": 1.0}])
    diff = compute_diff(base, cand)
    assert diff.category_deltas[0]["category"] == "CONFLICT"
    assert abs(diff.category_deltas[0]["delta"] - 0.5) < 1e-9


def test_added_and_removed_questions():
    base = scores([q(1, "stable-pass"), q(2, "stable-pass")])
    cand = scores([q(1, "stable-pass"), q(3, "stable-pass")])
    diff = compute_diff(base, cand)
    assert diff.added_ids == [3] and diff.removed_ids == [2]


# --------------------------------------------------------------------------- #
# render + CLI exit codes (E4)
# --------------------------------------------------------------------------- #
def test_render_lists_regressions_first():
    diff = compute_diff(scores([q(1, "stable-pass")]), scores([q(1, "stable-fail")]))
    md = render_diff_md(diff, scores([q(1, "stable-pass")]), scores([q(1, "stable-fail")]))
    assert "gate-blocking" in md
    assert md.index("regressions") < md.index("Route changes")  # ordering
    assert "**Q1**" in md


def _write_run(tmp_path, name, questions, **kw):
    d = tmp_path / name
    d.mkdir()
    (d / "scores.json").write_text(json.dumps(scores(questions, label=name, **kw)))
    return d


def test_main_nonzero_exit_on_regression_and_writes_diff(tmp_path):
    base = _write_run(tmp_path, "baseline", [q(1, "stable-pass")])
    cand = _write_run(tmp_path, "candidate", [q(1, "stable-fail")])
    code = main([str(base), str(cand)])
    assert code == 1
    assert (cand / "diff.md").is_file()


def test_main_zero_exit_when_only_flaky_flip(tmp_path):
    base = _write_run(tmp_path, "baseline", [q(1, "stable-pass")])
    cand = _write_run(tmp_path, "candidate", [q(1, "flaky")])
    assert main([str(base), str(cand)]) == 0


def test_main_zero_exit_on_improvement(tmp_path):
    base = _write_run(tmp_path, "baseline", [q(1, "stable-fail")])
    cand = _write_run(tmp_path, "candidate", [q(1, "stable-pass")])
    assert main([str(base), str(cand)]) == 0
