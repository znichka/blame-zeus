# ADR-017: Phase 2 — Data-Quality & Evaluation-Driven Iteration

| Field        | Value       |
|--------------|-------------|
| **Date**     | 2026-07-21  |
| **Status**   | Accepted    |
| **Amends**   | IMPLEMENTATION_PLAN.md §7 (Evaluation), §9 (Implementation Sequence) — pointer banners only |
| **Amended by** | —         |
| **Supersedes** | —         |

---

## Context

The MVP (`IMPLEMENTATION_PLAN.md §9`, Stages 1–10, plus the ADR-015/016 post-MVP work) is
functional end-to-end: a question routes through SQL / RAG / MIXED, gets an answer with citations,
and is enriched with attributed conflicts. But two structural gaps block the stated product goal —
**reliably answering any data-based question**:

1. **No way to measure answer quality.** `evaluation/gold-questions.json` (16 questions) and the §7
   scoring rubric (3 pts/question, ≥75% target) exist, but the `EvaluationRunner` that §7 specifies
   was never built (Stage 10 is unstarted). Every check to date has been manual `curl` /
   browser-smoke against individual questions (DEV-047/048/050/052/053/054). There is no baseline
   score and no way to tell whether a change helped or regressed.
2. **No way to diagnose a wrong answer.** The generated SQL and the conflict-probe output log only
   at `DEBUG` (and no `logging` config enables it); the retrieved RAG chunks, SQL result rows, and
   the DEV-057 discarded first-attempt SQL never reach the response; nothing about a query is
   persisted. A wrong answer leaves no trace.

Meanwhile the seed data has known, documented errors and gaps: ~838 of 841 detected conflict groups
are unreviewed (only 44 `variant_claims` across 2 claim_types promoted); 29 fuzzy-duplicate entity
pairs are un-triaged (DEV-044); 203 relationships are held in `relationships_flagged_for_review.json`;
and the 131 free-text relation labels fragment the text-to-SQL vocabulary (DEV-041 showed vocabulary
quality drives SQL quality). Past bugs of the same class (split entities Cronos/Cronus, Athene/Athena
per DEV-043; Io missing entirely per DEV-042) show these are systemic, not one-offs.

Adding or "fixing" data without a measurement loop risks silent regressions — exactly the failure
mode §7 was meant to prevent. Measurement must come first.

## Decision

Adopt a **measurement-first, evaluation-gated operating model** for all Phase 2 data and pipeline
work. Concretely:

1. **Build the evaluation harness and a committed baseline before touching any data.** No seed
   change is made until there is a reproducible score to compare against. (Harness design is
   **ADR-018**.)

2. **Every data/pipeline change is gated by a 3-run eval comparison.** A change is accepted only if
   it shows no *stable* regression (a question that flips PASS→FAIL across all 3 runs, not a flaky
   one). Results are committed as timestamped artifacts so quality is diffable in git history.

3. **Staged sequence P1 → P5**, each stage independently valuable and evaluable:
   - **P1** — evaluation harness + baseline.
   - **P2** — debuggability (logging, a `debug` response surface, a local reseed script) + resolving
     the two known runtime defects: Q9/Q12 `WITH RECURSIVE` fragility per DEV-054 (fix), and Q13
     raw-column-dump / empty relationship passageRef per DEV-053 (**confirm already fixed** by
     DEV-056/DEV-057 at baseline; further work only on evidence). See `IMPLEMENTATION_PLAN_PHASE2.md §3.4`.
   - **P3** — systematic audit and fixing of the *existing* seed (duplicates, relationship
     integrity, relation-label canonicalization per **ADR-019**), working the documented backlogs.
   - **P4** — the iterative conflict-depth loop over the 838 unreviewed groups, with the gold set
     growing in lockstep.
   - **P5** — new structured data types (numeric per ADR-009, myths, geography/epithets) and
     systematic gap discovery.

4. **Fix existing SQL/relational data (P3) before conflict depth (P4) or new data types (P5).** The
   product goal is *reliable* data answers; correcting what is already seeded and wrong takes
   priority over breadth. (User-directed priority.)

5. **Activate the two relevant Proposed ADRs at their stages.** ADR-010 (evaluation-set expansion +
   per-category scoring with floors) is **accepted now** — the harness (P1) commits to it
   immediately. ADR-009 (numeric/Catalogue-of-Ships data) is activated at **P5a**, remaining
   Proposed until then.

6. **Root cause first, code fix only if still needed.** For every defect, diagnose and correct the
   *underlying cause* — usually bad seed data or an already-present prompt rule — then **reseed and
   re-measure before writing any new code**. A workaround (prompt rule, query-time bound, retry,
   migration) is added only on *evidence* that the cause-level fix left the question failing or
   flaky, and successive workarounds are gated on the previous step's eval result. This is why P2
   treats Q9/Q12 as a data-integrity problem (reversed-direction edges producing a graph cycle)
   first and a SQL-robustness problem only if a clean DAG still fails — a silent query-time guard
   would merely mask the bad data while still emitting a wrong lineage. The measurement loop
   (Decision 2) is what makes "root cause first" enforceable: without a baseline there is no way to
   tell whether the cause-level fix was sufficient. Detailed staircase in
   `IMPLEMENTATION_PLAN_PHASE2.md §3.4`.

The design detail for each stage lives in `IMPLEMENTATION_PLAN_PHASE2.md`; the checklist and
"Done when" gates live in `TODO2.md`. This ADR is the *why*; those docs are the *what* and *how*.

## Alternatives considered

- **Keep manual `curl` / browser verification.** Rejected: it produces no baseline, no regression
  detection, and no history — the exact gaps that let seed errors accumulate unnoticed. It does not
  scale to an iterative add-and-measure loop.
- **Expand data breadth-first (new types / more entities) before fixing existing errors.** Rejected:
  contradicts the "reliable answers" goal — a broader corpus of wrong data answers more questions
  wrongly. Fixing the known-bad relational data first raises the reliability floor.
- **Fix data first, build measurement later.** Rejected: without a baseline, "later" can never tell
  whether the fixes helped or which change caused a regression. Measurement is the enabling
  capability, so it is P1.

## Consequences

**Positive**
- Committed eval result artifacts become the durable audit trail of answer quality over time.
- Every data change is provably non-regressing before it lands; silent quality drift is caught.
- The staged sequence keeps each step small, evaluable, and revertible.

**Negative / costs**
- Slower per-change: each batch runs the harness (3× the gold set) and a compare step.
- The operator must keep a running server + seeded DB to run the harness (it is offline but live).
- The gold set must grow in lockstep with the data, or new data goes unmeasured (addressed in P4).

**Scope note / sequencing**
- This ADR is recorded **before** implementation (the ADR-016/DEV-058 documentation-first
  precedent). The documentation deliverables — this ADR, ADR-018, ADR-019, `DEV-059`,
  `IMPLEMENTATION_PLAN_PHASE2.md`, `TODO2.md`, and the pointer banners — land first; the harness,
  debug surface, audit package, and data work are the staged implementation that follows.

**Follow-ups**
- Record `DEV-059` in `docs/DEVIATIONS.md` cross-referencing this ADR, ADR-018, ADR-019, and the
  ADR-010 acceptance.
- Add pointer banners to `IMPLEMENTATION_PLAN.md` §1, §7, §9; add a Phase-2 subsection to
  `docs/TODO.md` → *Post-MVP Enhancements* pointing to `TODO2.md`.
- Flip `ADR-010` to Accepted; add a forward-reference to `ADR-009` (activated at P5a).
