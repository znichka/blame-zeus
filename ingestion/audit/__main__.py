"""Stage P3 Track A [DEVIATED - see DEVIATIONS.md #DEV-070]: `python -m audit`, the
aggregate runner every check (A1-A5) registers into by conforming to the
`audit.contract` shape (`NAME` + `run(candidates_dir, db_conn) -> CheckResult`).
Read-only over candidate JSON + the live DB -- no check here mutates a file or
table (`ingestion/audit/README.md`'s standing invariant). Auto-discovers every
sibling module that exposes the contract, runs it, aggregates findings, applies
waivers, and writes both a machine-readable findings JSON and a human report.

This is the standing pre-seedgen gate (`docs/TODO-phase2-stage-p3.md` Track I):
exits non-zero if any un-waived finding survives, so a fix loop can gate `seedgen`
on a clean (or explicitly waived) run.
"""

from __future__ import annotations

import argparse
import datetime as _dt
import importlib
import json
import pkgutil
import sys
from pathlib import Path
from typing import Iterable

from audit.contract import CheckResult, Finding

AUDIT_DIR = Path(__file__).resolve().parent
DEFAULT_CANDIDATES_DIR = AUDIT_DIR.parent / "extraction" / "output"
DEFAULT_REPORTS_DIR = AUDIT_DIR / "reports"
DEFAULT_WAIVERS_PATH = AUDIT_DIR / "audit-waivers.json"
DEFAULT_BACKLOG_PATH = AUDIT_DIR / "backlog.json"

# Stage P5 Track A7a: checks whose waivers include the P4 F0a subject-tranche
# scoping decision (DEV-109) that Track E5/A6 relocate to backlog.json. Scoped
# to these two checks, not a blind reason-prefix scan -- A1/A4/A10 also cite
# "F0b/F0c (Stage P4 Track F0, DEV-109)" for unrelated, genuinely permanent
# waivers (82/9/1 entries, verified live), and a blind scan would wrongly
# reject those too `[DEVIATED - see DEVIATIONS.md #DEV-133]`.
SCOPE_SHAPED_WAIVER_CHECKS = ("A2", "A6")


def discover_checks() -> list:
    """Walks the `audit` package for sibling modules exposing the A2r contract
    (`NAME` + a callable `run`). Modules that don't conform -- `contract` itself,
    `__main__`, the `tests` subpackage, any leading-underscore helper -- are
    skipped by the attribute check, not a hardcoded exclude list, so a new check
    module needs no separate registration step beyond existing."""
    import audit as audit_pkg

    checks = []
    for module_info in pkgutil.iter_modules(audit_pkg.__path__):
        name = module_info.name
        if name.startswith("_"):
            continue
        module = importlib.import_module(f"audit.{name}")
        if hasattr(module, "NAME") and callable(getattr(module, "run", None)):
            checks.append(module)
    return sorted(checks, key=lambda m: m.NAME)


def _load_entries(path: Path, kind: str) -> list[dict]:
    """Shared loader for both disposition files: each is a list of
    `{"check", "subject", "reason"}` objects, and an entry without a
    non-empty `reason` is rejected at load time -- "clean, waived, or
    deferred, always with a note" means the note is mandatory, not optional,
    in either file."""
    if not path.exists():
        return []
    raw = json.loads(path.read_text(encoding="utf-8"))
    for entry in raw:
        if not entry.get("reason", "").strip():
            raise ValueError(
                f"{kind} for check={entry.get('check')!r} subject={entry.get('subject')!r}"
                " is missing a written reason"
            )
    return raw


def _reject_scope_shaped(waivers: list[dict]) -> None:
    """A7a: guards against a scope-shaped waiver re-entering `audit-waivers.json`
    once the E5/A6 relocation has landed. Fires only for `SCOPE_SHAPED_WAIVER_CHECKS`
    (A2, A6) whose reason still carries the F0b/F0c scope-shaped prefix -- see that
    constant's docstring for why the match is check-scoped rather than a blind
    reason-prefix scan."""
    for waiver in waivers:
        if waiver.get("check") in SCOPE_SHAPED_WAIVER_CHECKS and waiver.get("reason", "").startswith(("F0b", "F0c")):
            raise ValueError(
                f"waiver for check={waiver.get('check')!r} subject={waiver.get('subject')!r} still carries a"
                " scope-shaped F0b/F0c reason -- move it to backlog.json instead of waiving it (A7a)"
            )


def load_waivers(path: Path) -> list[dict]:
    """A5r waiver mechanism: `audit-waivers.json` is a list of
    `{"check", "subject", "reason"}` objects. A waiver without a non-empty
    `reason` is rejected at load time -- "clean or waived with a note" (the P3
    exit) means the note is mandatory, not optional. A7a additionally rejects
    any remaining scope-shaped A2/A6 waiver -- that content belongs in
    `backlog.json`, loaded separately via `load_backlog`."""
    waivers = _load_entries(path, "waiver")
    _reject_scope_shaped(waivers)
    return waivers


def load_backlog(path: Path) -> list[dict]:
    """Stage P5 Track E5: `backlog.json` holds relocated scope-shaped findings --
    a queue position, not a permanent judgement (see `Finding.defer`'s docstring).
    Same shape and same mandatory-reason discipline as `audit-waivers.json`."""
    return _load_entries(path, "backlog entry")


def _apply_waiver(finding: Finding, waivers: Iterable[dict]) -> Finding:
    for waiver in waivers:
        if waiver.get("check") == finding.check and waiver.get("subject") == finding.subject:
            return finding.waive(waiver["reason"])
    return finding


def _apply_backlog(finding: Finding, backlog: Iterable[dict]) -> Finding:
    for entry in backlog:
        if entry.get("check") == finding.check and entry.get("subject") == finding.subject:
            return finding.defer(entry["reason"])
    return finding


def run_checks(
    checks: list,
    candidates_dir: Path | None,
    db_conn: object | None,
    waivers: Iterable[dict] = (),
    backlog: Iterable[dict] = (),
) -> "AuditRun":
    """The pure aggregation core -- takes already-resolved check modules (or
    fixtures conforming to the same shape) plus already-opened sources, so it's
    testable with fakes and needs neither discovery nor a live DB. Backlog is
    only consulted for a finding a waiver didn't already cover -- the two files
    are disjoint by construction (E5/A6 moved rows between them), but a finding
    can only carry one disposition."""
    waivers = list(waivers)
    backlog = list(backlog)
    results: list[tuple[str, CheckResult]] = []
    for check in checks:
        result = check.run(candidates_dir, db_conn)
        processed = []
        for f in result.findings:
            f = _apply_waiver(f, waivers)
            if not f.waived:
                f = _apply_backlog(f, backlog)
            processed.append(f)
        results.append((check.NAME, CheckResult(findings=tuple(processed), summary=result.summary)))
    return AuditRun(checks=tuple(results), generated_at=_dt.datetime.now(_dt.timezone.utc).isoformat())


class AuditRun:
    def __init__(self, checks: tuple[tuple[str, CheckResult], ...], generated_at: str):
        self.checks = checks
        self.generated_at = generated_at

    @property
    def all_findings(self) -> list[Finding]:
        return [f for _, result in self.checks for f in result.findings]

    @property
    def exit_code(self) -> int:
        return 1 if any(not f.waived and not f.deferred for f in self.all_findings) else 0

    @property
    def deferred_count(self) -> int:
        return sum(1 for f in self.all_findings if f.deferred)


def write_findings_json(run: AuditRun, out_dir: Path, date_str: str) -> Path:
    path = out_dir / f"{date_str}-findings.json"
    payload = {
        "generatedAt": run.generated_at,
        "checks": [
            {"name": name, "summary": result.summary, "findings": [f.to_dict() for f in result.findings]}
            for name, result in run.checks
        ],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
    return path


def _check_badge(result: CheckResult) -> str:
    if not result.findings:
        return "PASS"
    if any(not f.waived and not f.deferred for f in result.findings):
        return "FINDINGS"
    if any(f.deferred for f in result.findings):
        return "DEFERRED"
    return "WAIVED"


def _deferred_count(result: CheckResult) -> int:
    return sum(1 for f in result.findings if f.deferred)


def write_report_md(run: AuditRun, out_dir: Path, date_str: str) -> Path:
    total = len(run.all_findings)
    unwaived = sum(1 for f in run.all_findings if not f.waived and not f.deferred)
    deferred = run.deferred_count
    lines = [
        f"# Audit report — {date_str}",
        "",
        f"**Summary:** {total} finding(s) across {len(run.checks)} check(s), {unwaived} unwaived, {deferred} deferred.",
        "",
    ]
    for name, result in run.checks:
        badge = _check_badge(result)
        deferred_n = _deferred_count(result)
        header = f"## {name} — {badge}"
        if deferred_n and badge != "DEFERRED":
            header += f" ({deferred_n} deferred)"
        lines.append(header)
        lines.append("")
        if result.summary:
            lines.append(result.summary)
            lines.append("")
        if result.findings:
            lines.append("| Severity | Subject | Detail | Suggested fix | Disposition |")
            lines.append("|---|---|---|---|---|")
            for f in result.findings:
                if f.deferred:
                    disposition_cell = f"deferred — {f.deferred_reason}"
                elif f.waived:
                    disposition_cell = f"waived — {f.waiver_reason}"
                else:
                    disposition_cell = "no"
                lines.append(f"| {f.severity} | {f.subject} | {f.detail} | {f.suggested_fix} | {disposition_cell} |")
            lines.append("")
    path = out_dir / f"{date_str}.md"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path


def _connect_db():
    """Opens the one connection every check shares for this run -- read-only
    `zeus_app` credentials under the same `statement_timeout` guardrail
    `core-api` runs under, mirroring `cycle_check._db_dsn()` (reused here, not
    re-derived, so there's one source of truth for the DSN)."""
    import psycopg2

    from audit.cycle_check import _db_dsn

    conn = psycopg2.connect(**_db_dsn())
    conn.set_session(readonly=True)
    return conn


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="python -m audit",
        description="Read-only data-quality checks over candidate JSON + the live DB (the pre-seedgen gate).",
    )
    parser.add_argument("--candidates", action="store_true", help="check candidate JSON only (skip the live DB)")
    parser.add_argument("--db", action="store_true", help="check the live DB only (skip candidate JSON)")
    parser.add_argument("--only", metavar="CHECK", help="run exactly one check by NAME (e.g. A3)")
    parser.add_argument(
        "--candidates-dir", type=Path, default=DEFAULT_CANDIDATES_DIR, help="ingestion/extraction/output/ override"
    )
    parser.add_argument("--out", type=Path, default=DEFAULT_REPORTS_DIR, help="reports output directory")
    parser.add_argument("--waivers", type=Path, default=DEFAULT_WAIVERS_PATH, help="audit-waivers.json override")
    parser.add_argument("--backlog", type=Path, default=DEFAULT_BACKLOG_PATH, help="backlog.json override")
    args = parser.parse_args(argv)

    use_candidates = not args.db or args.candidates
    use_db = not args.candidates or args.db

    candidates_dir = args.candidates_dir if use_candidates else None
    db_conn = _connect_db() if use_db else None

    try:
        checks = discover_checks()
        if args.only:
            checks = [c for c in checks if c.NAME == args.only]
            if not checks:
                print(f"no check named {args.only!r} found", file=sys.stderr)
                return 2
        waivers = load_waivers(args.waivers)
        backlog = load_backlog(args.backlog)
        run = run_checks(checks, candidates_dir, db_conn, waivers, backlog)
    finally:
        if db_conn is not None:
            db_conn.close()

    date_str = _dt.date.today().isoformat()
    findings_path = write_findings_json(run, args.out, date_str)
    report_path = write_report_md(run, args.out, date_str)

    for name, result in run.checks:
        deferred_n = _deferred_count(result)
        suffix = f" ({deferred_n} deferred)" if deferred_n else ""
        print(f"{name}: {_check_badge(result)} -- {result.summary}{suffix}")
    print(f"\nfindings: {findings_path}")
    print(f"report:   {report_path}")
    if run.deferred_count:
        print(f"backlog:  {run.deferred_count} finding(s) deferred (see {args.backlog})")

    return run.exit_code


if __name__ == "__main__":
    raise SystemExit(main())
