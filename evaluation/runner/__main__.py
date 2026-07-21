"""Operator entrypoint (Track C): `python -m runner --runs 3 --label baseline`.

Preflight → N-run loop over the gold set → score (Track B) → classify (Track C5)
→ hand to `report.write` (Track D). Live LLM calls happen here and are sanctioned
(ADR-018 §Decision 2 / DEV-055) — this is an offline operator tool, not the
mocked Gradle/CI suite.

The HTTP transport is injectable (`transport=`) so the retry/serviceError logic is
unit-testable without a live server (C7). `report` is imported lazily inside
`main()` so this module (and its HTTP helpers) import cleanly before Track D lands.
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable

from .classify import RunResults, classify_all, worst_run_aggregate
from .config import DEFAULT_CONFIG_PATH, EvalConfig, load_config
from .gold import DEFAULT_GOLD_PATH, GoldQuestion, load_gold
from .model import ParsedResponse
from .scoring import QuestionScore, score_question
from .sql_check import make_row_count_fn

# transport(method, url, body_or_None, timeout_seconds) -> (status_code, parsed_json_or_None)
Transport = Callable[[str, str, dict | None, float], "tuple[int, dict | None]"]


class TransportError(Exception):
    """Connection-level failure (refused/DNS/timeout) — distinct from an HTTP status."""


# --------------------------------------------------------------------------- #
# default HTTP transport (stdlib urllib; no third-party dependency)
# --------------------------------------------------------------------------- #
def default_transport(method: str, url: str, body: dict | None, timeout: float) -> tuple[int, dict | None]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            status = resp.status
            raw = resp.read()
    except urllib.error.HTTPError as e:
        # A 4xx/5xx response — return the status so the caller can decide (5xx retries).
        status = e.code
        raw = e.read()
    except (urllib.error.URLError, TimeoutError, ConnectionError) as e:
        raise TransportError(str(e)) from e
    try:
        parsed = json.loads(raw) if raw else None
    except json.JSONDecodeError:
        parsed = None
    return status, parsed


# --------------------------------------------------------------------------- #
# preflight (C2)
# --------------------------------------------------------------------------- #
def preflight(cfg: EvalConfig, transport: Transport) -> tuple[bool, str]:
    """GET /api/v1/sources — server must be up AND seeded (non-empty). Returns (ok, message)."""
    try:
        status, parsed = transport("GET", cfg.preflight_url(), None, cfg.timeout_seconds)
    except TransportError as e:
        return False, f"server unreachable at {cfg.preflight_url()} ({e})"
    if status != 200:
        return False, f"preflight got HTTP {status} from {cfg.preflight_url()} (server up but not ready?)"
    if not parsed:
        return False, "preflight returned an empty source list — DB not seeded (run ingestion first)"
    count = len(parsed) if isinstance(parsed, list) else 0
    if count == 0:
        return False, "preflight returned no sources — DB not seeded"
    return True, f"server up, {count} sources seeded"


# --------------------------------------------------------------------------- #
# per-question query with retry semantics (C3)
# --------------------------------------------------------------------------- #
def query_once(
    cfg: EvalConfig,
    question: str,
    debug: bool,
    transport: Transport,
    retries: int = 1,
) -> tuple[dict, ParsedResponse]:
    """POST one question; retry transport/5xx ONCE (ADR-018 §Decision 4).

    A 200 with serviceError:true is **not** retried — it is handed to scoring as a
    fail. Returns (raw_json_for_artifacts, parsed_response). On exhausted retries a
    synthetic serviceError raw + parsed is returned so the run continues and the
    question scores 0 (never a crash).
    """
    url = cfg.query_url()
    body = {"question": question, "debug": debug}
    last_note = "unknown transport failure"
    attempt = 0
    while attempt <= retries:
        try:
            status, parsed = transport("POST", url, body, cfg.timeout_seconds)
        except TransportError as e:
            last_note = f"transport error: {e}"
            attempt += 1
            continue
        if status >= 500:
            last_note = f"HTTP {status}"
            attempt += 1
            continue  # retry server errors
        if status != 200:
            # 4xx — client error, not retried; scored as a serviceError fail.
            return _synthetic_error(f"HTTP {status}")
        raw = parsed if isinstance(parsed, dict) else {}
        return raw, ParsedResponse.from_json(raw)
    return _synthetic_error(last_note)


def _synthetic_error(note: str) -> tuple[dict, ParsedResponse]:
    raw = {"serviceError": True, "answer": "", "routeDecision": None, "_runnerNote": note}
    return raw, ParsedResponse.from_json(raw)


# --------------------------------------------------------------------------- #
# N-run loop (C4) + orchestration (C6)
# --------------------------------------------------------------------------- #
def run_all(
    cfg: EvalConfig,
    questions: list[GoldQuestion],
    runs: int,
    debug: bool,
    transport: Transport,
    row_count_fn: Callable[[str | None], int | None] | None,
) -> RunResults:
    """Run the selected set `runs` times, scoring each response; classify across runs."""
    raw_by_run: list[list[dict]] = []
    scores_by_run: list[list[QuestionScore]] = []

    for _ in range(runs):
        raw_this_run: list[dict] = []
        scores_this_run: list[QuestionScore] = []
        for q in questions:
            raw, parsed = query_once(cfg, q.question, debug, transport)
            raw_this_run.append(raw)
            scores_this_run.append(score_question(q, parsed, row_count_fn))
        raw_by_run.append(raw_this_run)
        scores_by_run.append(scores_this_run)

    classifications = classify_all(scores_by_run)
    from .scoring import aggregate

    per_run_aggregates = [
        aggregate(run, cfg.category_floors, cfg.overall_target) for run in scores_by_run
    ]
    worst_idx, worst_agg = worst_run_aggregate(scores_by_run, cfg.category_floors, cfg.overall_target)

    return RunResults(
        label="",  # filled by caller
        runs=runs,
        base_url=cfg.base_url,
        questions=questions,
        raw_by_run=raw_by_run,
        scores_by_run=scores_by_run,
        classifications=classifications,
        worst_run_index=worst_idx,
        aggregate=worst_agg,
        per_run_aggregates=per_run_aggregates,
    )


# --------------------------------------------------------------------------- #
# CLI (C1)
# --------------------------------------------------------------------------- #
def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m runner", description="blame-zeus evaluation harness")
    p.add_argument("--runs", type=int, default=1, help="number of repetitions of the full set (default 1)")
    p.add_argument("--label", default="adhoc", help="label for the results dir (default 'adhoc')")
    p.add_argument("--base-url", default=None, help="override server base URL (default from eval-config.json)")
    p.add_argument("--questions", default=str(DEFAULT_GOLD_PATH), help="path to gold-questions.json")
    p.add_argument("--config", default=str(DEFAULT_CONFIG_PATH), help="path to eval-config.json")
    p.add_argument("--ids", default=None, help="comma-separated question ids to run a subset (e.g. 9,10,14)")
    p.add_argument("--debug", action="store_true", help="set debug:true in the request body (no-op until P2)")
    return p


def _parse_ids(ids_arg: str | None) -> set[int] | None:
    if not ids_arg:
        return None
    return {int(x.strip()) for x in ids_arg.split(",") if x.strip()}


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)

    cfg = load_config(args.config)
    if args.base_url:
        cfg = replace_base_url(cfg, args.base_url)

    questions = load_gold(args.questions)
    id_filter = _parse_ids(args.ids)
    if id_filter is not None:
        questions = [q for q in questions if q.id in id_filter]
        if not questions:
            print(f"ERROR: --ids {args.ids} matched no questions", file=sys.stderr)
            return 2

    transport = default_transport

    ok, msg = preflight(cfg, transport)
    if not ok:
        print(f"ERROR: preflight failed — {msg}", file=sys.stderr)
        print("Start the stack (scripts/run-local.sh) and confirm ingestion has seeded the DB.", file=sys.stderr)
        return 2
    print(f"Preflight OK: {msg}")

    row_count_fn = make_row_count_fn(cfg)

    print(f"Running {len(questions)} question(s) x {args.runs} run(s) against {cfg.base_url} ...")
    results = run_all(cfg, questions, args.runs, args.debug, transport, row_count_fn)
    results = replace_label(results, args.label)

    # Track D — imported lazily so this module imports cleanly before report.py exists.
    from . import report

    out_dir = report.write(results, cfg)

    agg = results.aggregate
    print(
        f"\nPessimistic (worst-run) aggregate: {agg.passed_questions}/{agg.total_questions} "
        f"full-score = {agg.overall_pass_rate:.0%} (target {agg.overall_target:.0%}) "
        f"{'PASS' if agg.overall_met else 'BELOW TARGET'}"
    )
    if results.flaky_ids:
        print(f"Flaky questions: {results.flaky_ids}")
    if agg.floor_breaches:
        print(f"Category floor breaches: {agg.floor_breaches}")
    print(f"Results written to: {out_dir}")

    # A completed run with failing questions is still a successful run (C6) → exit 0.
    return 0


# small immutable-replace helpers (EvalConfig/RunResults are frozen dataclasses)
def replace_base_url(cfg: EvalConfig, base_url: str) -> EvalConfig:
    import dataclasses

    return dataclasses.replace(cfg, base_url=base_url)


def replace_label(results: RunResults, label: str) -> RunResults:
    import dataclasses

    return dataclasses.replace(results, label=label)


if __name__ == "__main__":
    raise SystemExit(main())
