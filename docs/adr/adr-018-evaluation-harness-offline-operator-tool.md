# ADR-018: Evaluation Harness as an Offline Python Operator Tool

| Field        | Value       |
|--------------|-------------|
| **Date**     | 2026-07-21  |
| **Status**   | Accepted    |
| **Amends**   | TECH_GUARDRAILS.md ("No live LLM calls in tests" — scoping clause); IMPLEMENTATION_PLAN.md §7 (Evaluation runner implementation) |
| **Amended by** | —         |
| **Supersedes** | —         |

---

## Context

`IMPLEMENTATION_PLAN.md §7` specifies an `EvaluationRunner`: load `gold-questions.json`, POST each
question to `/api/v1/query`, score 3 pts/question (route match + author/conflict check + content
check), and report an aggregate against the ≥75% target. It was never built (Stage 10 unstarted);
ADR-017 makes building it the first Phase 2 stage.

Two constraints shape *how* it is built:

1. **Real end-to-end scoring must call live LLMs.** The whole point is to measure the actual
   answering pipeline: `QueryRouter`, `TextToSqlAgent`, `RagAgent`, `ConflictProbe`, `AnswerComposer`
   — all `@AiService` beans backed by a real chat model. There is no way to score the real system
   without live calls.
2. **`TECH_GUARDRAILS.md` says "No live LLM calls in tests."** The guardrail requires every
   `@AiService` to be mocked — `mockk<T>()` for unit tests, `@MockkBean` for Spring-context tests
   (re-confirmed by DEV-055). A Kotlin `EvaluationRunner` living in `:core-api`'s test sourceset
   would either violate this guardrail outright or need an awkward opt-out tag to keep it out of the
   normal `:core-api:test` run and CI.

The guardrail's purpose is to keep the **automated Gradle/CI test suite** deterministic, free, and
network-independent — so `./gradlew :core-api:test` is fast and reproducible. An evaluation harness
is a categorically different thing: a developer-invoked, offline tool whose *entire job* is to
exercise the live model, run occasionally (per data batch), and produce a score. It is the same
category as the `ingestion` job, which is explicitly permitted to call provider SDKs directly
because it is offline corpus-prep tooling, never part of the runtime or the test suite.

## Decision

1. **Build the harness as a standalone Python operator tool in `evaluation/runner/`**, invoked as
   `python -m runner` against a **running** server (`POST /api/v1/query`). Python because the §7
   scoring spec is already written in Python idiom (word-boundary keyword regex), the tooling
   ecosystem (`psycopg2` for the Q10 `min_row_count` check, `dotenv`) is already used by
   `ingestion`, and iteration on scoring rules is faster outside Gradle.

2. **Reinterpret the "No live LLM calls in tests" guardrail with an explicit scoping clause:** it
   governs the **automated Gradle/CI test suite** (all `@AiService` mocked), **not** developer-invoked
   **offline operator tools** such as `evaluation/runner/` or `ingestion/`. The harness never runs
   in `:core-api:test` and never runs in CI; it is run by an operator against a live server. The
   clause is added to `TECH_GUARDRAILS.md`.

3. **Deterministic scoring per §7 first.** Implement the §7 rubric verbatim (route match;
   author/conflict check including `conflicts_min_count`; content check with word-boundary keywords,
   `forbidden_patterns`, `sql_must_contain`, `min_row_count`) plus ADR-010's per-category pass rates
   with floors. An **optional LLM-judge column** may be added in a later stage (P4) for semantic
   scoring — deterministic remains the primary, reproducible signal.

4. **Handle LLM nondeterminism with N-run classification, not retry-until-pass.** `--runs N`
   executes the whole set N times and classifies each question `stable-pass` / `flaky` /
   `stable-fail`; the aggregate is the pessimistic (worst-run) score with the flaky list called out.
   A `serviceError:true` is a scored failure, never retried; only transport/HTTP errors retry once.
   Retry-until-pass is rejected because it hides the flakiness that is itself a quality signal.

5. **Persist committed, diffable artifacts.** Each run writes
   `evaluation/results/<UTC-ISO>__<git-sha>__<label>/` with `raw_responses.json` (the full
   `QueryResponse` per question per repetition — the poor-man's query history), `scores.json`, and a
   human-readable `report.md`; a `compare.py` produces a `diff.md` between two runs. Results dirs are
   committed so regressions are visible in git history.

## Alternatives considered

- **Kotlin `EvaluationRunner` in `:core-api` test sourceset.** Rejected: it either violates the
  no-live-LLM guardrail or needs a fragile opt-out tag to stay out of CI; and it drags the scoring
  logic into the JVM build for no benefit over a small Python tool.
- **LLM-judge as the primary scorer from day one.** Rejected: adds per-run token cost and its own
  nondeterminism before a cheap, reproducible deterministic baseline even exists. The deterministic
  rubric is the foundation; the judge is an optional later layer.
- **Retry each question until it passes.** Rejected: masks router/model flakiness, which is exactly
  what the harness should surface (the n=17 brittleness ADR-010 warns about).

## Consequences

**Positive**
- A reproducible, committed quality number with per-category floors, obtained without touching or
  compromising the Gradle test suite.
- Flakiness is measured, not hidden — regressions are only actioned when stable.

**Negative / costs**
- Adds a Python operator tool and a growing `evaluation/results/` tree in the repo.
- Each run costs LLM tokens (3× the gold set for a baseline/release run).
- The guardrail doc now carries a scoping nuance that future contributors must respect (the harness
  is *not* a licence for live LLM calls inside `:core-api:test`).

**Follow-ups**
- Record `DEV-059`; add the scoping clause to `TECH_GUARDRAILS.md`; flip `ADR-010` → Accepted.
- Implementation detail: `IMPLEMENTATION_PLAN_PHASE2.md §2`; checklist: `TODO2.md` Stage P1.
