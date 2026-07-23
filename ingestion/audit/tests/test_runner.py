import json
import types

import pytest

from audit import __main__ as runner
from audit.contract import CheckResult, Finding


def _fake_check(name, findings=(), summary=""):
    """A minimal stand-in for a check module: anything exposing NAME + a
    run(candidates_dir, db_conn) callable conforms to the A2r contract, so a
    SimpleNamespace works exactly like a real module here."""

    def run(candidates_dir, db_conn):
        return CheckResult(findings=tuple(findings), summary=summary)

    return types.SimpleNamespace(NAME=name, run=run)


def _finding(check="AX", subject="subject", severity="error"):
    return Finding(check=check, severity=severity, subject=subject, detail="detail", suggested_fix="fix it")


def test_run_checks_aggregates_findings_across_checks():
    checks = [
        _fake_check("A1", findings=[_finding(check="A1"), _finding(check="A1", subject="s2")]),
        _fake_check("A2", findings=[_finding(check="A2")]),
    ]

    run = runner.run_checks(checks, candidates_dir=None, db_conn=None)

    assert [name for name, _ in run.checks] == ["A1", "A2"]
    assert len(run.all_findings) == 3
    assert run.exit_code == 1


def test_run_checks_with_no_findings_exits_zero():
    checks = [_fake_check("A1", findings=[], summary="clean")]

    run = runner.run_checks(checks, candidates_dir=None, db_conn=None)

    assert run.all_findings == []
    assert run.exit_code == 0


def test_waived_finding_does_not_fail_the_run():
    checks = [_fake_check("A1", findings=[_finding(check="A1", subject="known-issue")])]
    waivers = [{"check": "A1", "subject": "known-issue", "reason": "tracked in DEV-999, deferred to P5b"}]

    run = runner.run_checks(checks, candidates_dir=None, db_conn=None, waivers=waivers)

    assert len(run.all_findings) == 1
    assert run.all_findings[0].waived is True
    assert run.all_findings[0].waiver_reason == "tracked in DEV-999, deferred to P5b"
    assert run.exit_code == 0


def test_unmatched_waiver_leaves_other_findings_unwaived():
    checks = [_fake_check("A1", findings=[_finding(check="A1", subject="real-issue")])]
    waivers = [{"check": "A1", "subject": "some-other-issue", "reason": "not relevant here"}]

    run = runner.run_checks(checks, candidates_dir=None, db_conn=None, waivers=waivers)

    assert run.all_findings[0].waived is False
    assert run.exit_code == 1


def test_load_waivers_rejects_missing_reason(tmp_path):
    path = tmp_path / "audit-waivers.json"
    path.write_text(json.dumps([{"check": "A1", "subject": "x", "reason": "  "}]))

    with pytest.raises(ValueError, match="missing a written reason"):
        runner.load_waivers(path)


def test_load_waivers_missing_file_returns_empty_list(tmp_path):
    assert runner.load_waivers(tmp_path / "does-not-exist.json") == []


def test_write_findings_json_and_report_md(tmp_path):
    checks = [
        _fake_check("A1", findings=[_finding(check="A1")], summary="1 issue"),
        _fake_check("A2", findings=[], summary="clean"),
    ]
    run = runner.run_checks(checks, candidates_dir=None, db_conn=None)

    findings_path = runner.write_findings_json(run, tmp_path, "2026-07-23")
    report_path = runner.write_report_md(run, tmp_path, "2026-07-23")

    payload = json.loads(findings_path.read_text())
    assert payload["checks"][0]["name"] == "A1"
    assert payload["checks"][0]["findings"][0]["subject"] == "subject"
    assert payload["checks"][1]["findings"] == []

    report = report_path.read_text()
    assert "## A1 — FINDINGS" in report
    assert "## A2 — PASS" in report


def test_report_badge_is_waived_when_every_finding_is_waived(tmp_path):
    checks = [_fake_check("A1", findings=[_finding(check="A1", subject="known")])]
    waivers = [{"check": "A1", "subject": "known", "reason": "deferred, see DEV-999"}]
    run = runner.run_checks(checks, candidates_dir=None, db_conn=None, waivers=waivers)

    report = runner.write_report_md(run, tmp_path, "2026-07-23").read_text()

    assert "## A1 — WAIVED" in report


def test_discover_checks_finds_the_real_cycle_check_adapter():
    checks = runner.discover_checks()

    names = [c.NAME for c in checks]
    assert "A3" in names


def test_main_only_flag_runs_exactly_one_check(tmp_path, monkeypatch):
    checks = [
        _fake_check("A1", findings=[_finding(check="A1")]),
        _fake_check("A2", findings=[_finding(check="A2")]),
    ]
    monkeypatch.setattr(runner, "discover_checks", lambda: checks)
    monkeypatch.setattr(runner, "_connect_db", lambda: None)

    exit_code = runner.main(
        ["--candidates", "--only", "A2", "--out", str(tmp_path), "--waivers", str(tmp_path / "missing.json")]
    )

    payload = json.loads((tmp_path / f"{__import__('datetime').date.today().isoformat()}-findings.json").read_text())
    assert [c["name"] for c in payload["checks"]] == ["A2"]
    assert exit_code == 1


def test_main_unknown_only_check_returns_error_code(monkeypatch, tmp_path):
    monkeypatch.setattr(runner, "discover_checks", lambda: [_fake_check("A1")])

    exit_code = runner.main(["--candidates", "--only", "NOPE", "--out", str(tmp_path)])

    assert exit_code == 2


def test_main_candidates_flag_skips_db_connection(tmp_path, monkeypatch):
    connect_calls = []
    monkeypatch.setattr(runner, "discover_checks", lambda: [_fake_check("A1")])
    monkeypatch.setattr(runner, "_connect_db", lambda: connect_calls.append(1) or object())

    runner.main(["--candidates", "--out", str(tmp_path)])

    assert connect_calls == []
