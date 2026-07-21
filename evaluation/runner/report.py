"""Results-dir artifact writer (Track D).

Owns the committed on-disk contract for one run:
`evaluation/results/<UTC>__<sha>__<label>/` containing
  - `raw_responses.json` — untouched server JSON per question per repetition (D2),
  - `scores.json` — machine-diffable per-point/per-run scores + aggregate (D3;
    the file `compare.py` reads),
  - `report.md` — human table with a classification column and an empty triage
    column filled manually in Track H (D4/D5).

Consumes Track C's `RunResults`; independent of B/C internals (it reads their
output shapes). `now`/`git_sha`/`results_root` are injectable so D6 can write to a
tmp dir without touching real git or the committed results tree.
"""

from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from .classify import RunResults
from .config import EvalConfig
from .scoring import Aggregate, QuestionScore

# evaluation/results/ (this file lives in evaluation/runner/).
DEFAULT_RESULTS_ROOT = Path(__file__).resolve().parent.parent / "results"


def _utc_stamp(now: datetime | None) -> str:
    """Filesystem-safe compact UTC ISO, e.g. 2026-07-21T14-03-11Z."""
    dt = now or datetime.now(timezone.utc)
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H-%M-%SZ")


def _git_sha() -> str:
    """Short git sha, or 'nogit' if unavailable (D1)."""
    try:
        out = subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        return out.stdout.strip() or "nogit"
    except (subprocess.SubprocessError, OSError):
        return "nogit"


def _conflicts_count(raw: dict) -> int:
    c = raw.get("conflicts")
    return len(c) if isinstance(c, list) else 0


# --------------------------------------------------------------------------- #
# serialization helpers
# --------------------------------------------------------------------------- #
def _aggregate_dict(agg: Aggregate, worst_run_index: int) -> dict:
    return {
        "passed_questions": agg.passed_questions,
        "total_questions": agg.total_questions,
        "total_points": agg.total_points,
        "max_points": agg.max_points,
        "overall_pass_rate": round(agg.overall_pass_rate, 4),
        "overall_target": agg.overall_target,
        "overall_met": agg.overall_met,
        "worst_run_index": worst_run_index,
        "per_category": [
            {
                "category": cr.category,
                "passed": cr.passed,
                "total": cr.total,
                "rate": round(cr.rate, 4),
                "floor": cr.floor,
                "floor_met": cr.floor_met,  # None → N/A
            }
            for cr in agg.per_category
        ],
        "floor_breaches": agg.floor_breaches,
    }


def _per_run_entry(run_index: int, score: QuestionScore, raw: dict) -> dict:
    return {
        "run": run_index,
        "actual_route": score.actual_route,
        "route": score.route_point,
        "author": score.author_point,
        "content": score.content_point,
        "total": score.total,
        "passed": score.passed,
        "service_error": score.service_error,
        "conflicts_count": _conflicts_count(raw),
        "notes": list(score.notes),
    }


def _scores_dict(results: RunResults, stamp: str, sha: str) -> dict:
    classifications = {c.id: c for c in results.classifications}
    questions = []
    for q_idx, q in enumerate(results.questions):
        per_run = [
            _per_run_entry(run_idx, results.scores_by_run[run_idx][q_idx],
                           results.raw_by_run[run_idx][q_idx])
            for run_idx in range(results.runs)
        ]
        cls = classifications.get(q.id)
        questions.append({
            "id": q.id,
            "category": q.category,
            "expected_route": q.expected_route,
            "classification": cls.label if cls else "unknown",
            "worst_run_total": min((r["total"] for r in per_run), default=0),
            "per_run": per_run,
        })
    return {
        "label": results.label,
        "runs": results.runs,
        "base_url": results.base_url,
        "git_sha": sha,
        "timestamp": stamp,
        "flaky_ids": results.flaky_ids,
        "aggregate": _aggregate_dict(results.aggregate, results.worst_run_index),
        "questions": questions,
    }


# --------------------------------------------------------------------------- #
# report.md rendering
# --------------------------------------------------------------------------- #
def _cell(passed: bool) -> str:
    return "✓" if passed else "✗"


def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"


def _floor_note(cr) -> str:
    if cr.floor is None:
        return "floor n/a"
    return f"floor {_pct(cr.floor)} {'PASS' if cr.floor_met else 'BREACH'}"


def _render_md(results: RunResults, stamp: str, sha: str) -> str:
    agg = results.aggregate
    worst = results.worst_run_index
    lines: list[str] = []
    lines.append(f"# Evaluation Report — {results.label}")
    lines.append("")
    lines.append(f"- Run: `{stamp}` | sha: `{sha}` | label: `{results.label}` | runs: {results.runs}")
    lines.append(f"- Base URL: {results.base_url}")
    lines.append(
        f"- **Overall (pessimistic / worst-run #{worst})**: "
        f"{agg.passed_questions}/{agg.total_questions} full-score = **{_pct(agg.overall_pass_rate)}** "
        f"(target {_pct(agg.overall_target)}) — {'PASS' if agg.overall_met else 'BELOW TARGET'}"
    )
    lines.append("- Category pass rates:")
    for cr in agg.per_category:
        lines.append(f"  - {cr.category}: {cr.passed}/{cr.total} ({_pct(cr.rate)}) — {_floor_note(cr)}")
    lines.append(f"- Floor breaches: {', '.join(agg.floor_breaches) if agg.floor_breaches else 'none'}")
    lines.append(f"- Flaky questions: {results.flaky_ids if results.flaky_ids else 'none'}")
    lines.append("")
    lines.append(
        "Point cells and actual-route below are from the **worst run**; `class` is across all runs. "
        "Fill the **triage** column manually (Track H): one of "
        "`pipeline-bug` / `data-gap` / `corpus-gap` / `eval-bug`."
    )
    lines.append("")
    lines.append("| id | category | route exp | route act | route | author | content | total | class | triage |")
    lines.append("|---:|----------|-----------|-----------|:-----:|:------:|:-------:|:-----:|-------|--------|")

    classifications = {c.id: c for c in results.classifications}
    worst_scores = results.scores_by_run[worst]
    for q_idx, q in enumerate(results.questions):
        s = worst_scores[q_idx]
        cls = classifications.get(q.id)
        label = cls.label if cls else "unknown"
        lines.append(
            f"| {q.id} | {q.category} | {q.expected_route or '—'} | {s.actual_route or '—'} | "
            f"{_cell(s.route_point)} | {_cell(s.author_point)} | {_cell(s.content_point)} | "
            f"{s.total}/3 | {label} | |"
        )
    lines.append("")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# public entrypoint
# --------------------------------------------------------------------------- #
def write(
    results: RunResults,
    cfg: EvalConfig,
    results_root: Path | None = None,
    now: datetime | None = None,
    git_sha: str | None = None,
) -> Path:
    """Write the three artifacts to results/<UTC>__<sha>__<label>/ and return the dir."""
    root = results_root or DEFAULT_RESULTS_ROOT
    stamp = _utc_stamp(now)
    sha = git_sha if git_sha is not None else _git_sha()
    out_dir = root / f"{stamp}__{sha}__{results.label}"
    out_dir.mkdir(parents=True, exist_ok=True)

    # D2 — raw server JSON, per question per repetition (nothing lost).
    (out_dir / "raw_responses.json").write_text(
        json.dumps(
            {"label": results.label, "runs": results.runs, "responses_by_run": results.raw_by_run},
            indent=2, ensure_ascii=False,
        )
    )
    # D3 — machine-diffable scores.
    (out_dir / "scores.json").write_text(
        json.dumps(_scores_dict(results, stamp, sha), indent=2, ensure_ascii=False)
    )
    # D4/D5 — human report with an empty, manually-filled triage column.
    (out_dir / "report.md").write_text(_render_md(results, stamp, sha))

    return out_dir
