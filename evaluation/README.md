# Evaluation harness (`runner/`)

An **offline operator tool** (ADR-018) that scores the running `core-api` against the
16 gold questions in `gold-questions.json`, implementing the `IMPLEMENTATION_PLAN.md §7`
rubric verbatim plus ADR-010 per-category floors. It makes **live LLM calls** by design —
that is sanctioned here (it is not part of the Gradle/CI suite; see the scoping clause in
`docs/TECH_GUARDRAILS.md` and DEV-055/DEV-060). Built in Phase 2 Stage P1.

## Prerequisites

1. **Start the stack** and let ingestion seed the DB (RAG/MIXED/conflict questions need
   `narrative_chunks` and `variant_claims` populated):
   ```bash
   scripts/run-local.sh            # Postgres + core-api on :8080
   # in ingestion/, one-time: python main.py   (if the DB is unseeded)
   ```
2. **Export the read-only DB creds** for the Q10 row-count re-executor (uses the read-only
   `zeus_app` user by guardrail — never the superuser):
   ```bash
   export POSTGRES_APP_USER=zeus_app POSTGRES_APP_PASSWORD=app_password
   export POSTGRES_HOST=localhost POSTGRES_PORT=5432 POSTGRES_DB=blamezeus
   ```
   Defaults in `eval-config.json` match `docker-compose`, so this is only needed if you
   changed them.
3. **Python env** — there is no system pytest; use the `ingestion` venv (Python 3.12+):
   ```bash
   ../ingestion/.venv/bin/python -m pytest runner/tests/     # from evaluation/
   ```

## Run a baseline

From the repo root (or `evaluation/`), with the server up:

```bash
cd evaluation
../ingestion/.venv/bin/python -m runner --runs 3 --label baseline
```

- `--runs N` runs the whole set N times; each question is classified **stable-pass** /
  **flaky** / **stable-fail**, and the reported aggregate is the **worst run** (pessimistic).
- `--label` names the results dir. Other flags: `--ids 9,10,14` (subset), `--base-url`,
  `--questions`, `--config`, `--debug` (no-op until P2).

The runner **preflights** `GET /api/v1/sources` and aborts (exit 2) if the server is down or
unseeded — it never scores against a dead server.

## Results (committed)

Each run writes `results/<UTC>__<git-sha>__<label>/`:

| file | contents |
|---|---|
| `raw_responses.json` | full server JSON per question per repetition (forensic record) |
| `scores.json` | per-point / per-run scores, classification, pessimistic aggregate, per-category rates + floor breaches — machine-diffable |
| `report.md` | human table (route exp/act, 3 point cells, total, classification) + a **triage** column filled in manually |

**Results dirs are committed** — they are the quality audit trail (ADR-018 §Decision 5): the
scored number and the code that produced it move together.

## Compare two runs

```bash
../ingestion/.venv/bin/python -m runner.compare <baseline_dir> <candidate_dir>
```

Writes `diff.md` into the candidate dir: **stable PASS→FAIL regressions first** (the
gate-blocking set), then per-category deltas, route changes, and conflict-count changes.
Exit is non-zero **only** on a *stable* regression (flaky flips are informational — never act
on a single-run delta), so later stages can gate in a plain script.

## Layout

```
evaluation/
├── gold-questions.json      # 16 gold questions (REFUSAL pair authored in P4)
├── eval-config.json         # base-url, overall target, per-category floors, read-only DB block
├── runner/
│   ├── config.py  gold.py  model.py     # loaders + response contract (Track A)
│   ├── scoring.py                        # §7 rubric, pure (Track B)
│   ├── sql_check.py                      # Q10 row-count re-executor (Track F)
│   ├── __main__.py  classify.py          # CLI + HTTP + N-run + classification (Track C)
│   ├── report.py                         # results-dir writer (Track D)
│   ├── compare.py                        # baseline vs candidate diff (Track E)
│   └── tests/                            # pytest (scoring, classify, compare, report; sql_check DB-gated)
└── results/                 # committed run artifacts
```
