"""Baseline vs candidate diff (Track E): `python -m runner.compare <base> <cand>`.

Reads both runs' `scores.json` (Track D contract) and writes `diff.md` into the
candidate dir. Honours the **stable-only** rule (ADR-018 cross-cutting: never act
on a single-run delta): a PASS→FAIL is a *regression* only when both sides are
**stable** (stable-pass → stable-fail); any transition touching a `flaky`
classification is informational, never a regression. Exit is non-zero iff a stable
regression exists, so later stages can gate in a plain script without CI (E4).

`compute_diff`/`render_diff_md` are pure over the loaded dicts → unit-testable
without files (E5).
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path

STABLE_PASS = "stable-pass"
STABLE_FAIL = "stable-fail"
FLAKY = "flaky"


def load_scores(path: str | Path) -> dict:
    """Load a run's scores.json — accepts the results dir or the file itself."""
    p = Path(path)
    if p.is_dir():
        p = p / "scores.json"
    if not p.is_file():
        raise FileNotFoundError(f"scores.json not found at {p}")
    return json.loads(p.read_text())


def _questions_by_id(scores: dict) -> dict[int, dict]:
    return {q["id"]: q for q in scores.get("questions", [])}


def _worst_entry(scores: dict, q: dict) -> dict:
    """The worst run's per-question per_run entry (the pessimistic representative)."""
    idx = scores.get("aggregate", {}).get("worst_run_index", 0)
    per_run = q.get("per_run", [])
    if not per_run:
        return {}
    if 0 <= idx < len(per_run):
        return per_run[idx]
    return per_run[-1]


@dataclass(frozen=True)
class DiffResult:
    regressions: list[dict] = field(default_factory=list)   # stable-pass → stable-fail (gate-blocking)
    improvements: list[dict] = field(default_factory=list)  # stable-fail → stable-pass
    flaky_flips: list[dict] = field(default_factory=list)   # any transition touching flaky
    category_deltas: list[dict] = field(default_factory=list)
    route_changes: list[dict] = field(default_factory=list)
    conflict_count_changes: list[dict] = field(default_factory=list)
    added_ids: list[int] = field(default_factory=list)
    removed_ids: list[int] = field(default_factory=list)

    @property
    def has_regression(self) -> bool:
        return bool(self.regressions)


def compute_diff(baseline: dict, candidate: dict) -> DiffResult:
    b_by_id = _questions_by_id(baseline)
    c_by_id = _questions_by_id(candidate)

    regressions: list[dict] = []
    improvements: list[dict] = []
    flaky_flips: list[dict] = []
    route_changes: list[dict] = []
    conflict_changes: list[dict] = []

    # Iterate in candidate question order, over ids present on both sides.
    for cq in candidate.get("questions", []):
        qid = cq["id"]
        if qid not in b_by_id:
            continue
        bq = b_by_id[qid]
        bl = bq.get("classification")
        cl = cq.get("classification")
        entry = {"id": qid, "category": cq.get("category"), "from": bl, "to": cl}

        if bl == STABLE_PASS and cl == STABLE_FAIL:
            regressions.append(entry)
        elif bl == STABLE_FAIL and cl == STABLE_PASS:
            improvements.append(entry)
        elif bl != cl and (bl == FLAKY or cl == FLAKY):
            flaky_flips.append(entry)  # informational — never a regression (stable-only rule)

        b_entry = _worst_entry(baseline, bq)
        c_entry = _worst_entry(candidate, cq)
        b_route, c_route = b_entry.get("actual_route"), c_entry.get("actual_route")
        if b_route != c_route:
            route_changes.append({"id": qid, "from": b_route, "to": c_route})
        b_conf = b_entry.get("conflicts_count", 0)
        c_conf = c_entry.get("conflicts_count", 0)
        if b_conf != c_conf:
            conflict_changes.append({"id": qid, "from": b_conf, "to": c_conf})

    # Per-category rate deltas from the aggregates.
    b_cat = {c["category"]: c for c in baseline.get("aggregate", {}).get("per_category", [])}
    c_cat = {c["category"]: c for c in candidate.get("aggregate", {}).get("per_category", [])}
    category_deltas: list[dict] = []
    for cat in list(dict.fromkeys(list(b_cat) + list(c_cat))):
        br = b_cat.get(cat, {}).get("rate", 0.0)
        cr = c_cat.get(cat, {}).get("rate", 0.0)
        if br != cr:
            category_deltas.append({"category": cat, "from": br, "to": cr, "delta": round(cr - br, 4)})

    added = [q["id"] for q in candidate.get("questions", []) if q["id"] not in b_by_id]
    removed = [q["id"] for q in baseline.get("questions", []) if q["id"] not in c_by_id]

    return DiffResult(
        regressions=regressions,
        improvements=improvements,
        flaky_flips=flaky_flips,
        category_deltas=category_deltas,
        route_changes=route_changes,
        conflict_count_changes=conflict_changes,
        added_ids=added,
        removed_ids=removed,
    )


def _overall_line(scores: dict) -> str:
    agg = scores.get("aggregate", {})
    return (
        f"{agg.get('passed_questions', '?')}/{agg.get('total_questions', '?')} "
        f"({agg.get('overall_pass_rate', 0) * 100:.0f}%)"
    )


def render_diff_md(diff: DiffResult, baseline: dict, candidate: dict) -> str:
    lines: list[str] = []
    lines.append(f"# Diff — `{baseline.get('label')}` → `{candidate.get('label')}`")
    lines.append("")
    lines.append(f"- Baseline: `{baseline.get('label')}` @ `{baseline.get('git_sha')}` — overall {_overall_line(baseline)}")
    lines.append(f"- Candidate: `{candidate.get('label')}` @ `{candidate.get('git_sha')}` — overall {_overall_line(candidate)}")
    lines.append("")

    # 1. Regressions first — the gate-blocking set.
    lines.append("## ⛔ Stable PASS→FAIL regressions (gate-blocking)")
    if diff.regressions:
        for r in diff.regressions:
            lines.append(f"- **Q{r['id']}** ({r['category']}): {r['from']} → {r['to']}")
    else:
        lines.append("- none")
    lines.append("")

    # 2. Per-category deltas.
    lines.append("## Per-category rate deltas")
    if diff.category_deltas:
        for d in diff.category_deltas:
            sign = "+" if d["delta"] >= 0 else ""
            lines.append(f"- {d['category']}: {d['from'] * 100:.0f}% → {d['to'] * 100:.0f}% ({sign}{d['delta'] * 100:.0f} pts)")
    else:
        lines.append("- no category rate changes")
    lines.append("")

    # 3. Route changes.
    lines.append("## Route changes")
    if diff.route_changes:
        for rc in diff.route_changes:
            lines.append(f"- Q{rc['id']}: {rc['from']} → {rc['to']}")
    else:
        lines.append("- none")
    lines.append("")

    # 4. Conflict-count changes.
    lines.append("## Conflict-count changes (conflicts[] length)")
    if diff.conflict_count_changes:
        for cc in diff.conflict_count_changes:
            lines.append(f"- Q{cc['id']}: {cc['from']} → {cc['to']}")
    else:
        lines.append("- none")
    lines.append("")

    # Informational — improvements, flaky flips, added/removed (never gate-blocking).
    lines.append("## Informational (not gate-blocking)")
    if diff.improvements:
        for i in diff.improvements:
            lines.append(f"- ✅ improvement Q{i['id']} ({i['category']}): {i['from']} → {i['to']}")
    for f in diff.flaky_flips:
        lines.append(f"- 🌀 flaky flip Q{f['id']} ({f['category']}): {f['from']} → {f['to']} (single-run delta — ignored by the gate)")
    if diff.added_ids:
        lines.append(f"- added questions: {diff.added_ids}")
    if diff.removed_ids:
        lines.append(f"- removed questions: {diff.removed_ids}")
    if not (diff.improvements or diff.flaky_flips or diff.added_ids or diff.removed_ids):
        lines.append("- none")
    lines.append("")

    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m runner.compare", description="diff two evaluation runs")
    p.add_argument("baseline", help="baseline results dir (or its scores.json)")
    p.add_argument("candidate", help="candidate results dir (or its scores.json)")
    p.add_argument("--out", default=None, help="path to write diff.md (default: <candidate>/diff.md)")
    return p


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    baseline = load_scores(args.baseline)
    candidate = load_scores(args.candidate)
    diff = compute_diff(baseline, candidate)
    md = render_diff_md(diff, baseline, candidate)

    if args.out:
        out_path = Path(args.out)
    else:
        cand = Path(args.candidate)
        out_path = (cand if cand.is_dir() else cand.parent) / "diff.md"
    out_path.write_text(md)

    if diff.has_regression:
        print(f"REGRESSION: {len(diff.regressions)} stable PASS→FAIL — {[r['id'] for r in diff.regressions]}", file=sys.stderr)
    else:
        print("No stable regressions.")
    print(f"diff written to: {out_path}")
    return 1 if diff.has_regression else 0


if __name__ == "__main__":
    raise SystemExit(main())
