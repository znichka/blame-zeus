# Stage P1 — Evaluation harness + baseline: Detailed Checklist

**Done when:** `python -m runner --runs 3 --label baseline` completes against a running, seeded
server and writes a **committed** `evaluation/results/<UTC>__<sha>__baseline/` (`raw_responses.json`
+ `scores.json` + `report.md`); the aggregate is the worst-run (pessimistic) score with per-category
pass rates and floors reported; every failing gold question is triaged in `report.md` as
**pipeline-bug / data-gap / corpus-gap / eval-bug**; `ADR-010`'s **Accepted** status is confirmed
(it was already flipped at documentation time — DEV-059 — so this is a verify, not an edit) and the
`TECH_GUARDRAILS.md` "No live LLM calls in tests" scoping clause (ADR-018 §Decision 2) is added;
`DEV-059` is recorded.

> **Design source of truth:** `IMPLEMENTATION_PLAN_PHASE2.md §2` (the *what/how*), `ADR-018` (the
> *why* — offline operator tool, N-run classification, committed artifacts), `ADR-010` (per-category
> floors), and `IMPLEMENTATION_PLAN.md §7` (the rubric, implemented **verbatim**). This checklist is
> the *granular task breakdown* — it does not re-justify the design.

> **This stage ships ZERO `core-api` code.** P1 is measurement-only: a standalone Python tool under
> `evaluation/runner/` plus a config file and doc edits. It does **not** touch `LangChain4jConfig.kt`,
> any `@AiService`, the Gradle build, or CI. It is invoked by an operator against an already-running
> server (`scripts/run-local.sh`). Any temptation to "fix" a failing question here is out of scope —
> P1 only *measures and triages*; fixes are P2+.

Before starting, re-read `DEVIATIONS.md` (deviation protocol). Relevant carry-overs:
- **DEV-059** — this program's documentation-first landing (ADR-017/018/019 + this plan) is already
  logged; P1 is its first implementation stage.
- **DEV-055** — the automated test suite mocks every `@AiService`. ADR-018 §Decision 2 explicitly
  scopes that guardrail to the **Gradle/CI suite**, *not* to this offline operator tool. Track G adds
  that scoping clause so the harness's live calls are sanctioned, not a violation.
- **DEV-054** — Q9/Q12 `WITH RECURSIVE` serviceError and the Q14 route-label ambiguity are *expected*
  baseline findings, triaged here (Track H), fixed in P2. Do **not** pre-fix them.
- **DEV-053 / DEV-056 / DEV-057** — Q13 is *expected to pass* at baseline; a Q13 failure is a signal
  to reopen, not the baseline expectation. Record whichever the run actually shows.
- **DEV-052** — the committed `gold-questions.json` already carries `conflicts_min_count` (Q13–15),
  `min_row_count` (Q10), `sql_must_contain` (Q9), and an id-18 negative case; the runner reads these
  keys — confirm against the live file, don't assume the §7 table.
- **DEV-048 / DEV-050** — `required_keywords` are live-verified; the runner only *reads* them. Any
  keyword edit provoked by triage is a logged **eval-bug** fix (Track H), never silent tuning.

**Deviation protocol:** if the shipped scoring/CLI diverges from `IMPLEMENTATION_PLAN.md §7` or
`IMPLEMENTATION_PLAN_PHASE2.md §2` in any way (extra CLI flag, different results-dir layout, a scoring
edge case §7 didn't specify), log it as the next `DEV-NNN` and annotate per the CLAUDE.md protocol.

---

## Gold-question schema (verified against the live fixture — code against these exact keys)

`evaluation/gold-questions.json` is a **flat JSON array of 16 objects today** (ids 1–15 all filled +
the id-18 negative case; only Q16/Q17 — the REFUSAL pair — remain deliberately unfilled, authored in
P4). Note Q11/Q12 (MIXED) are **filled** in the live fixture — they carry `required_authors`
(Q11 `["Homer"]`, Q12 `["Apollodorus"]`) and refined question text that diverge from the stale §7
reference table; code against the fixture, not §7. Union of keys actually
present: `id`, `category`, `question`, `expected_route`, `required_authors`, `required_keywords`,
`forbidden_patterns`, `conflicts_min_count`, `min_row_count`, `sql_must_contain`. REFUSAL questions
(land in P4) will additionally carry `refusal_criteria` — the runner must handle its absence today and
its presence later **without a scorer change** (that is the whole point of building refusal scoring now).

`QueryResponse` fields the runner reads (verified in `domain/dto/QueryResponse.kt`):
`answer: String`, `routeDecision: RouteDecision?` (`"RAG"|"SQL"|"MIXED"` — never `"CONFLICT"`),
`citations: List<Citation>`, `conflicts: List<ConflictEntry>`, `sqlGenerated: String?`,
`serviceError: Boolean`, `conflictsInProse: Boolean`.
`Citation` = `{author, work, passageRef, stance?}`. `ConflictEntry` = `{claimValue, sourceAuthor,
sourceWork, passageRef?}`. Request body: `POST /api/v1/query` with `{"question": "..."}`.

---

## Parallelization Guide

```
Track A  eval-config.json + shared I/O contracts  ─┐  (foundational — unblocks B,C,D,E)
                                                    │
Track B  scoring.py (pure rubric)          ────────┤  needs A's dataclasses/keys only
Track F  Q10 min_row_count re-executor      ───────┤  a scoring sub-module; parallel to B
Track C  __main__.py (HTTP + N-run + CLI)   ───────┤  needs A; mocks scoring during dev
Track D  report.py (artifact writer)        ───────┤  needs A; independent of B/C internals
Track E  compare.py (diff.md)               ───────┘  needs A + D's on-disk schema only

Track G  docs/ADR housekeeping             ─────────  fully independent, no code, do anytime

Track H  baseline run + triage + commit     ─────────  SERIAL — needs A–F merged + running server
```

**Rule of thumb:** A is the only hard blocker. B/C/D/E/F are independently ownable once A pins the
data contracts. G is pure prose. H is the integration point and must run last against a live stack.

---

## Track A — Config + shared contracts (foundational; do first)

Pins the interfaces every other track codes against. Small, fast, merge before B–F start in earnest.

- [x] **A1** — `evaluation/runner/__init__.py` (empty, makes the package importable as `runner`).
- [x] **A2** — `evaluation/eval-config.json`:
  - [x] `base_url` default (`"http://localhost:8080"`), `query_path` (`/api/v1/query`),
        `preflight_path` (`/api/v1/sources`), request `timeout_seconds`.
  - [x] `overall_target: 0.75`.
  - [x] `category_floors` object — per ADR-010, floors on **CONFLICT** and **REFUSAL** at minimum;
        include `DATA` too (§2.2). REFUSAL floor may be `null`/absent until P4 authors the questions —
        loader must tolerate a missing floor (report N/A, never crash).
        (Initial values: CONFLICT 0.5, DATA 0.5, REFUSAL null — config-adjustable; ADR-010 prescribes
        floors exist but no numbers, so these are defensible starting bars, not a plan deviation.)
  - [x] `db` block for the Q10 re-executor: DSN pieces for the **read-only `zeus_app`** user
        (host/port/db/user/password via env, `${VAR:-default}` placeholders), `statement_timeout_ms`.
        Documented as intentionally the read-only user (guardrail) in `config.py DbConfig` docstring.
- [x] **A3** — `runner/config.py`: `load_config(path)` → typed `EvalConfig` dataclass; resolves env
      placeholders; validates required keys; clear error if `eval-config.json` missing.
- [x] **A4** — `runner/gold.py`: `load_gold(path)` → `list[GoldQuestion]` dataclass. Normalizes the
      **optional** keys to `None`/`[]` so downstream code never does membership checks on missing
      keys. Expose `category`, `expected_route`, and every scoring key as attributes. Include an
      `is_refusal` helper (`category == "REFUSAL"` / presence of `refusal_criteria`).
- [x] **A5** — `runner/model.py`: dataclasses mirroring the response contract — `ParsedResponse`
      (`answer`, `route_decision`, `citations: list[Citation]`, `conflicts: list[ConflictEntry]`,
      `sql_generated`, `service_error`, `conflicts_in_prose`) + `Citation`/`ConflictEntry`; a
      `from_json(dict)` factory tolerant of nulls/missing fields (so a malformed/partial server
      response degrades to a scored fail, never a runner crash). This is the seam B and C share.
- [ ] **A6** — commit A as one unit; note in the PR that B–F may now branch.
      _(pending — left to the operator per repo convention of committing only on request; B–F may branch once committed.)_

---

## Track B — `scoring.py` (pure §7 rubric; no network, fully unit-testable)

One question × one `ParsedResponse` → a 3-point breakdown. **Implements `IMPLEMENTATION_PLAN.md §7`
verbatim** + ADR-010 per-category aggregation. Pure functions over Track-A dataclasses → trivially
testable with fixtures, no server. This is the correctness-critical track.

- [x] **B1** — `score_route(q, resp) -> bool` (1 pt): `resp.route_decision == q.expected_route`.
      **Guard:** CONFLICT-category questions are **not** scored on route (ADR-007/DEV-014). Note §7 is
      self-inconsistent here — its ADR-007 amendment banner says conflict questions are "scored on
      `conflicts[]` … **not** on a route match," but the §7 scoring rubric still lists a "Route match
      (1pt)" step whose only carve-out is REFUSAL/DATA, never CONFLICT. **Pin one rule (do not invent a
      "route point folded into the author check" — no such fold exists in §7):** for a CONFLICT
      question, point-1 is awarded by B2's `conflicts[]` check (≥2 distinct `claimValue`s) and route is
      ignored entirely, so a route mismatch can neither lose nor gain a point. Log the §7
      banner-vs-rubric mismatch as this stage's `DEV-NNN` (the deviation-protocol note above already
      anticipates it). **[implemented: CONFLICT `score_route` returns the conflicts-min check, route
      ignored. TWO pending DEV entries for Track G/H to record: (a) the §7 banner-vs-rubric mismatch;
      (b) the Q18 edge — a `conflicts_min_count:0` CONFLICT scores content over an intentionally-empty
      `claimValue` concat, so its keyword can't match; implemented §7-verbatim, no special-case (no
      silent tuning), flagged in a `score_content` comment for Track-H triage.]**
- [x] **B2** — `score_author_or_conflict(q, resp) -> bool` (1 pt), branch on category:
  - [x] FACT/MIXED → ≥1 of `q.required_authors` appears in `resp.citations[].author`
        (case-insensitive substring/`author` match). If `required_authors` empty → auto-pass (§7: the
        check only applies when authors are specified; Q4/Q5/Q8/Q15 have none — **not** Q11, which
        carries `["Homer"]` in the live fixture).
  - [x] CONFLICT → `resp.conflicts` has ≥ `q.conflicts_min_count` **distinct** `claimValue`s
        (default 2 when key absent, via `GoldQuestion.effective_conflicts_min_count`). **Plus** the
        per-author guard: **only when `len(q.required_authors) >= 2`**, assert each listed author
        appears in ≥1 `conflicts[].sourceAuthor` (Q13). Q14 (single author) → skip. `>= 2` guard baked in.
  - [x] DATA/REFUSAL → auto-1 **if route matched** (§7). `score_question` threads B1's `route_point` in.
- [x] **B3** — `score_content(q, resp) -> (bool, notes)` (1 pt):
  - [x] Keyword match helper: `re.search(r'\b' + re.escape(kw) + r'\b', text, re.IGNORECASE)` for
        **every** `required_keyword` (all must match). Word-boundary, as §7 mandates.
  - [x] FACT/DATA/MIXED → keywords over `resp.answer`. Q10 `min_row_count` → Track F's row count IS
        the content point (via injected `row_count_fn`); Q9 `sql_must_contain` → `sql_generated`
        null-guarded first (§7 Q9 note) then token-checked, in addition to keywords.
  - [x] CONFLICT → keywords over the concatenation of `resp.conflicts[].claimValue`, not `answer`.
  - [x] `forbidden_patterns` → **any** case-insensitive match in the scored text = automatic
        content-point **fail** (all categories incl. REFUSAL).
- [x] **B4** — `score_refusal(q, resp) -> (bool, notes)` (REFUSAL content point) — **implemented now**
      though no REFUSAL question exists until P4 (§2.2). All *enabled* `refusal_criteria` + no
      `forbidden_patterns`:
  - [x] `must_not_assert_answer` — reuse `forbidden_patterns` as the positive-claim signature.
  - [x] `must_mention_source_limit` — `SOURCE_SILENCE_PHRASES` module constant (seeded from §7,
        extendable in P4 without a scorer change).
  - [x] `must_not_fabricate_citation` — Phase-1 heuristic = **empty `citations[]`**; phrase-list +
        empty-citations shape preserved so P4 needs no scorer change.
- [x] **B5** — `score_question(q, resp, row_count_fn=None) -> QuestionScore` composing B1–B4: three
      booleans + `total`/`passed` + `notes` breakdown for `report.md`. `resp.service_error is True` →
      **all three points 0** with a `service_error` flag (ADR-018 §Decision 4).
- [x] **B6** — `aggregate(scores, category_floors, overall_target) -> Aggregate`: overall pass rate
      **and** per-category rate; a question "passes" at full 3/3 (§7/ADR-010 full-score intent).
      `CategoryRate.floor_met` compares to the floor (None ⇒ N/A, never a breach); `floor_breaches: list`.
- [x] **B7** — **TDD:** `evaluation/runner/tests/test_scoring.py` (pytest) — one pass + one fail **per
      category**, Q14 single-author skip, Q10-no-keyword row-count path, Q9 `sql_must_contain`
      null-guard, `serviceError` fail, `forbidden_patterns` trip, REFUSAL pass/fail pair, and aggregate
      floor-breach + None-floor N/A. **22 tests green** (run via `ingestion/.venv` pytest). No network, no DB.

---

## Track F — Q10 `min_row_count` SQL re-executor (scoring sub-module; parallel to B)

Isolated because it is the only scoring path that touches a DB. Ownable independently of the rest of B.

- [x] **F1** — `runner/sql_check.py`: `count_rows(sql, cfg, connect=None) -> RowCountCheck` opening a
      **read-only `zeus_app`** psycopg2 connection from the A2 `db` block. Returns a `RowCountCheck`
      (`count`/`ok`/`note`) so the failure reason surfaces in triage; `make_row_count_fn(cfg)` adapts
      it to Track B's `(sql) -> int | None` seam.
- [x] **F2** — statement-timeout via `options='-c statement_timeout=<ms>'` on the connection (from
      `DbConfig.psycopg2_kwargs()`, the 3s cap) **and** `set_session(readonly=True)`; a timeout/any
      failure → `ok=False` note, never a crash.
- [x] **F3** — executes the **model-generated** `resp.sql_generated` inside
      `SELECT count(*) FROM (<sql>) AS _rowcount_sub`, guarding null/non-SELECT `sql_generated` via
      `_sanitize_sql` (fail cleanly, no connect). Returns the count; B3 compares `>= q.min_row_count`.
- [x] **F4** — one short-lived connection per check, always `close()`d in `finally`; failures
      (auth/timeout/bad SQL) → `RowCountCheck(None, ok=False, note=...)`, surfaced in triage.
- [x] **F5** — **TDD:** `tests/test_sql_check.py` — pure guard/wrapping tests + injected-`connect`
      stub-cursor tests (no real DB), a connect-failure→note test, and a live-DB smoke test gated
      behind `RUN_DB_TESTS` (skipped by default; real check runs in H). No H2/mock-SQL. **30 passed,
      1 skipped** overall.

---

## Track C — `__main__.py` (HTTP client + N-run orchestration + CLI)

The operator entrypoint. Can be built against a stubbed `scoring.score_question` until B lands.

- [x] **C1** — CLI (argparse) flags per §2.1: `--runs` (default 1), `--label` (default `adhoc`),
      `--base-url` (override; default from config), `--questions` (default `gold-questions.json`),
      `--config` (path to eval-config.json), `--ids` (comma-list subset), `--debug` (sets
      `debug:true` in the body — no-op until P2, wired now). `--help` renders without Track D present.
- [x] **C2** — **Preflight:** `GET /api/v1/sources` before scoring; transport error / non-200 /
      empty-list → `(False, msg)` and `main()` exits 2 with a "start the stack + seed" hint. Never
      scores against a dead/unseeded server.
- [x] **C3** — HTTP `POST /api/v1/query` `{"question", "debug"}`; parsed via `ParsedResponse.from_json`.
      Injectable `transport`; `TransportError`/HTTP-5xx → **retry once**, then a synthetic
      `serviceError` raw+parsed (scored 0, no crash); 4xx → no retry; a 200 with `serviceError:true`
      → **no retry**, handed to scoring as a fail. Paths distinguished + unit-tested.
- [x] **C4** — **N-run loop** (`run_all`): runs the selected set `--runs` times; `raw_by_run` keeps
      every raw server JSON per question per repetition for Track D's `raw_responses.json`.
- [x] **C5** — **Classification** in `runner/classify.py` (pure, HTTP-free): `stable-pass` (N/N full),
      `stable-fail` (0/N), `flaky` (mixed); aligned by question **id**. Aggregate = **worst run**
      (fewest full passes, tie-broken by total points); `RunResults.flaky_ids` called out.
- [x] **C6** — `main()` orchestrates preflight → `run_all` (score B + Track F row-count) → classify →
      `report.write(results, cfg)` (imported lazily). Exit 2 if server unreachable/unseeded; exit 0
      on a completed run even with failing questions.
- [x] **C7** — **TDD:** `tests/test_classify.py` — stable/flaky/stable-fail, transpose-by-id +
      misalignment guard, worst-run aggregate (+ points tiebreak), and a `StubTransport` HTTP layer
      covering success/serviceError-no-retry/5xx-retry/transport-retry-recover/4xx-no-retry, preflight
      ok/empty/non-200/unreachable, and a `run_all` end-to-end (stub transport + stub row-counter,
      no server/DB). **45 passed, 1 skipped** overall.

---

## Track D — `report.py` (results-dir artifact writer)

Owns the committed on-disk contract. Independent of B/C internals — it consumes their output shapes.

- [x] **D1** — results dir `evaluation/results/<UTC>__<sha>__<label>/` via
      `report.write(results, cfg, results_root=?, now=?, git_sha=?)`. Compact filesystem-safe UTC
      (`2026-07-21T14-03-11Z`) + `git rev-parse --short HEAD` (degrades to `nogit`); `mkdir -p`.
      `now`/`git_sha`/`results_root` injectable so D6 writes to tmp without touching git/results tree.
- [x] **D2** — `raw_responses.json`: `{label, runs, responses_by_run: [[raw...]...]}` — the raw
      server JSON per question per repetition, preserved verbatim (parsed dataclass never substituted).
- [x] **D3** — `scores.json`: per-question `classification` + `worst_run_total` + `per_run`
      (per-point booleans, total, passed, service_error, `conflicts_count` [for E's conflict-delta],
      actual_route, notes) + the pessimistic `aggregate` (per-category rates, `floor_met`,
      `floor_breaches`, `worst_run_index`) + `flaky_ids`. Machine-diffable — the file `compare.py` reads.
- [x] **D4** — `report.md`: header block (overall pessimistic %, per-category rates with floor
      PASS/BREACH/n-a, flaky list, runs, sha, label) + one row per question (id, category, route
      exp/act, 3 point cells `✓`/`✗`, total, **classification**, empty **triage**). Point cells are the
      worst run; `class` is across all runs.
- [x] **D5** — triage column left empty & machine-writable, filled manually in Track H; the unique
      `id` column is the stable per-row anchor, with a legend naming the four triage labels.
- [x] **D6** — **TDD:** `tests/test_report.py` — synthetic RunResults → tmp dir (injected now/sha);
      asserts dir name, all three files exist, `scores.json` round-trips with flaky/worst-run/
      conflicts_count/notes fields, raw preserved verbatim, and `report.md` has header + every question
      row + triage column. **49 passed, 1 skipped** overall.

---

## Track E — `compare.py` (baseline vs candidate → `diff.md`)

Used at every *later* stage's gate; built now so P2 can diff against this baseline immediately.

- [x] **E1** — `python -m runner.compare <baseline> <candidate>` (`--out` optional); `load_scores`
      accepts a results dir or a `scores.json` path. Writes `diff.md` into the candidate dir by default.
- [x] **E2** — `diff.md` order per §2.3: **regressions first** (gate-blocking), then per-category
      rate deltas, then route changes, then conflict-count changes (`conflicts[]` length via D's
      per-run `conflicts_count`), then an Informational section (improvements/flaky flips/added/removed).
      Route + conflict deltas use each side's **worst-run** representative entry.
- [x] **E3** — **stable-only** contract: a regression is only stable-pass → stable-fail; any
      transition touching `flaky` is an informational flaky flip, never a regression (verified both
      directions: stable-pass→flaky and flaky→stable-fail).
- [x] **E4** — `main()` exits **1** iff a stable regression exists, else **0**; prints the regressed
      ids to stderr. Lets P2+ gate in a plain script, no CI.
- [x] **E5** — **TDD:** `tests/test_compare.py` — stable regression (listed + exit 1), flaky flip
      (informational, exit 0, both directions), improvement (exit 0), no-change, route change,
      conflict-count change, per-category delta, added/removed ids, render-ordering, and CLI
      exit-code + `diff.md` write. **61 passed, 1 skipped** overall.

---

## Track G — Docs / ADR housekeeping (no code; fully independent — do anytime)

- [ ] **G1** — `TECH_GUARDRAILS.md`: add the ADR-018 §Decision 2 **scoping clause** to the "No live
      LLM calls in tests" rule — it governs the **automated Gradle/CI suite** (all `@AiService`
      mocked), **not** developer-invoked offline operator tools (`evaluation/runner/`, `ingestion/`).
      Cross-reference ADR-018.
- [ ] **G2** — `docs/adr/adr-010-evaluation-set-expansion.md`: **confirm Status is already Accepted**
      (it was flipped at documentation time per §2.2 / DEV-059 — this is a verification, no edit is
      expected; if it still reads Proposed, flip it and note the discrepancy).
      **Do NOT author its ~8 new questions here** —
      that is deferred to P4 (don't change the yardstick and the data in the same stage). Leave a note
      that per-category floors land in `eval-config.json` (Track A2) now, questions in P4.
- [ ] **G3** — `docs/DEVIATIONS.md`: record the P1 deviation entry (next `DEV-NNN`) — the harness is
      built in Python under `evaluation/runner/` (not the Kotlin `EvaluationRunner` the MVP §7 text
      implies), per ADR-018. Mark the affected §7 "Evaluation Runner" lines
      `[DEVIATED - see DEVIATIONS.md #DEV-NNN]` and add the `IMPLEMENTATION_PLAN.md §7` stage-note
      banner pointer. (§7 already carries a forward "➕ Phase 2 builds the runner" note — extend, don't
      overwrite.)
- [ ] **G4** — `evaluation/README.md` (new, short): how to run — start the stack
      (`scripts/run-local.sh`), export `ZEUS_APP_URL`/keys, `python -m runner --runs 3 --label
      baseline`; where results land; the "results dirs are committed" convention; the Q10 read-only-DB
      requirement.

---

## Track H — Baseline run + triage + commit (SERIAL; needs A–F merged + a running, seeded server)

The integration gate. Everything above converges here.

- [ ] **H1** — bring up the stack: `scripts/run-local.sh` (or `docker-compose.full.yml`); confirm
      seeded via the C2 preflight (`/api/v1/sources` returns the 6 seed sources).
- [ ] **H2** — run `python -m runner --runs 3 --label baseline`; confirm a
      `evaluation/results/<UTC>__<sha>__baseline/` dir with all three artifacts is produced.
- [ ] **H3** — **triage every failing/flaky question** in `report.md`'s triage column as exactly one
      of **pipeline-bug / data-gap / corpus-gap / eval-bug**, with a one-line justification. Expected
      shape (record what the run *actually* shows, not these assumptions):
  - [ ] Q9/Q12 → likely **pipeline-bug** (`serviceError`, `WITH RECURSIVE` fragility, DEV-054) → P2.
  - [ ] Q13 → **expected PASS** (DEV-056/057). If it fails, triage it and note the reopen — do not fix
        here.
  - [ ] Q11 (MIXED, "died at Troy") → likely **data-gap** (no structured Trojan backing, DEV-054) → P5b.
- [ ] **H4** — **decide the Q14 route-label question** (DEV-054 "Watch" item): gold labels Q14 RAG-via-
      empty-SQL-fallback, but stronger schema grounding sometimes makes SQL return rows. Pick the
      authoritative label from the baseline evidence; if the **gold label changes**, that is a logged
      **eval-bug** fix — edit `gold-questions.json` and record the DEV/rationale (a keyword/label edit
      is never silent tuning).
- [ ] **H5** — any keyword correction surfaced by triage → treat as a logged **eval-bug** fix
      (DEV-048/050 rule), live-verified, with a DEV note — not silent tuning to make a run pass.
- [ ] **H6** — **commit** the baseline results dir + `eval-config.json` + the runner package + Track G
      doc edits together, so the committed number and the code that produced it move as one unit
      (ADR-018 §Decision 5 — results are the audit trail).
- [ ] **H7** — final gate check: re-read TODO2.md Stage P1 "Done when" and tick each clause; confirm
      P2 can now `compare.py <baseline> <candidate>` against this dir.

---

## Definition-of-done checklist (mirror of TODO2.md Stage P1)

- [ ] `evaluation/runner/` package complete: `__main__.py`, `scoring.py`, `report.py`, `compare.py`
      (+ `config.py`, `gold.py`, `model.py`, `classify.py`, `sql_check.py` helpers).
- [ ] `evaluation/eval-config.json` — per-category floors, overall ≥75% target, base-url default.
- [ ] 3-run stable/flaky/stable-fail classification; `serviceError:true` scored fail (no retry);
      transport errors retry once.
- [ ] Q10 `min_row_count` re-executes generated SQL via read-only `zeus_app` psycopg2 + statement timeout.
- [ ] `refusal_criteria` scoring implemented **now** (phrase-list + empty-`citations[]`), so P4's
      Q16/Q17 need no scorer change.
- [ ] ADR-010 Accepted status confirmed (already flipped at documentation time, DEV-059); its ~8
      questions **deferred to P4**.
- [ ] Baseline results dir committed; every failure triaged in `report.md`.
- [ ] Q14 route-label decided; recorded as an eval-bug fix if the gold label changed.
- [ ] `TECH_GUARDRAILS.md` scoping clause added; `DEV-059` (and the P1 harness-language DEV) recorded.
- [ ] `pytest evaluation/runner/tests/` green (scoring, classify, compare, report; sql_check gated).
