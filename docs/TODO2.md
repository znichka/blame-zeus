# blame-zeus: Project TODO — Phase 2 (Data-Quality & Evaluation Program)

Phase-2 stages track `IMPLEMENTATION_PLAN_PHASE2.md`. Each stage's **"Done when"** is the gate for
starting the next. This roadmap implements **ADR-017** (direction), **ADR-018** (evaluation
harness), and **ADR-019** (relation canonicalization), and is tracked under `TODO.md` →
*Post-MVP Enhancements* (named by ADR, not a numbered `IMPLEMENTATION_PLAN.md §9` stage, so §9
history stays untouched).

> **Operating model (ADR-017):** measurement-first, evaluation-gated. Build the harness and a
> committed baseline **before** touching data; gate every change on a **3-run** eval comparison
> (only *stable* PASS→FAIL regressions block); commit eval result artifacts as the quality audit
> trail. Priority: fix existing SQL/relational data (P3) **before** conflict depth (P4) or new data
> types (P5).

> Per-stage detailed checklists (`TODO-phase2-stageN.md`) are created **during** implementation of
> each stage, following the existing `TODO-stageN.md` pattern — this file is the outline.

Before starting any stage, re-read `DEVIATIONS.md` (per the CLAUDE.md deviation protocol). Relevant
carry-overs: **DEV-059** records this program's documentation-first landing; **DEV-054** (Q9/Q12
`WITH RECURSIVE`, fixed in P2) and **DEV-053** (Q13 formatting, expected already fixed by
DEV-056/DEV-057 — **confirmed** at baseline, fixed further only on evidence) are the two known
runtime defects addressed in P2;
**DEV-041** (schema-vocabulary → SQL quality) motivates ADR-019; **DEV-055** (tests mock
`@AiService`) bounds where the harness may live.

---

## Stage P1 — Evaluation harness + baseline  (ADR-018; ADR-010 accepted here)
**Done when:** `python -m runner --runs 3 --label baseline` completes against a running, seeded
server and writes a **committed** `evaluation/results/<UTC>__<sha>__baseline/`; every failing gold
question is triaged in `report.md` as pipeline-bug / data-gap / corpus-gap / eval-bug.

- [ ] `evaluation/runner/` package: `__main__.py` (CLI: `--runs`, `--label`, `--base-url`,
      `--questions`, `--ids`, `--debug`), `scoring.py` (§7 rubric verbatim + ADR-010 per-category
      floors), `report.py` (results dir: `raw_responses.json` / `scores.json` / `report.md`),
      `compare.py` (baseline vs candidate → `diff.md`)
- [ ] `evaluation/eval-config.json` — per-category floors, overall ≥75% target, base-url default
- [ ] 3-run stable / flaky / stable-fail classification; `serviceError:true` scored as fail (no
      retry); transport errors retry once
- [ ] Q10 `min_row_count` re-executes generated SQL via read-only `zeus_app` psycopg2 + statement timeout
- [ ] Implement `refusal_criteria` (phrase-list + empty-`citations[]`) **now**, so P4's REFUSAL
      Q16/Q17 need no scorer change
- [ ] Flip **ADR-010** → Accepted (done at documentation time); defer authoring its ~8 new questions
      to P4 (don't change yardstick and data at once)
- [ ] Commit baseline results dir; triage every failure in `report.md`
- [ ] Triage decides the **Q14 route-label** question (RAG-via-empty-SQL vs SQL-returns-rows, DEV-054);
      record as an eval-bug fix if the gold label changes

→ Detailed checklist: `TODO-phase2-stage-p1.md` (created at implementation)

---

## Stage P2 — Debuggability + known-defect fixes  (DEV-053, DEV-054)
**Done when:** the A3 cycle-detection check reports the `parent_of` graph clean (or lists + fixes the
reversed edges); a `debug:true` request returns a populated `DebugInfo`; Q9/Q12 no longer
`serviceError`; Q13 **confirmed passing** at baseline; `scripts/reseed-local.sh` re-applies V10–V14
without dropping embeddings; `:core-api:test` green; eval `--runs 3 --debug` vs baseline shows those
fixes and **zero stable regressions**.

- [x] `logging.level.com.blamezeus.coreapi: DEBUG` in `application.yml` (or `debug` profile)
- [x] `QueryRequest.debug` + `QueryResponse.debug: DebugInfo?` (`@JsonInclude(NON_NULL)`) via a
      **`ThreadLocal` singleton `DebugCapture`** (plain bean w/ constructor default, **not**
      `@Scope("request")` — keeps handler/retriever unit tests constructible), appended to by
      `SqlQueryHandler`, **`MixedQueryHandler`**, the chunk retriever, and `QueryService` (probe
      subject/claimType, claim count, first-attempt SQL, capped SQL rows, retrieved chunk refs,
      fallback/composer flags, draft answer) — DEV-064
- [x] `scripts/reseed-local.sh` — **`DROP TABLE entity_aliases`** (V14 is a bare `CREATE TABLE`) +
      `TRUNCATE` the other V10–V13 tables `CASCADE` → `DELETE FROM flyway_schema_history WHERE version
      IN ('10'…'16')` (**must include V15/V16** or Flyway skips the re-apply) → restart; **never**
      `down -v`; guard against a shared env (Flyway checksum trap) — DEV-065
- [ ] Q13: **verify passing at baseline, do not re-implement** — DEV-056 composer + DEV-057's
      already-mandated `r.passage_ref AS passage_ref` are expected to cover it; only tweak if the
      baseline still shows the dump/empty passageRef
- [ ] Q9/Q12 = **Stage 8.5 gap (ii) — root cause first, code fix only if still needed** (gate each
      rung on the previous rung's eval):
  - [ ] **Rung 0 (always):** cycle-detection check over `relationships` **authored now in P2** (→
        audit A3), run **before any SQL/prompt change**; fix reversed edges in candidate JSON →
        reseed → re-run eval. If Q9/Q12 pass over the clean DAG, **stop — ship no code.**
        Checker itself built + live-verified — DEV-066 (found 4 live cycles incl. a near-certain
        `Laertes`⇄`Odysseus` reversed edge). Fix + reseed + re-verify still pending (Track I).
  - [ ] **Rung 1 (only if clean DAG still fails/flakes):** LOUD bounded `WITH RECURSIVE` few-shot
        (depth cap + `visited`-id array) in `TextToSqlAgent`, breadcrumb via `sqlRows`
  - [ ] **Rung 2 (only if failure is malformed CTE, not data):** `runSqlWithErrorRecovery` +
        `regenerateAfterSqlError` in **both** `SqlQueryHandler` **and** `MixedQueryHandler`, rethrow
        ORIGINAL error on 2nd failure, DEV-057 attribution retry gets its own `try/catch`
  - [ ] **Rung 3 (only on evidence):** `V-migration` ancestry helper via `SchemaIntrospector`
- [x] Decision recorded: **skip `query_history`** for the PoC (eval artifacts + `DebugInfo` cover it)
      — DEV-064; revisit noted on the `TODO.md` P5 line
- [ ] TDD: retry path, cycle-detection check (pure Python over a fixture graph), and DebugCapture
      unit-tested, `@AiService` mocked; `:core-api:test` green — cycle-detection check (9 tests) and
      DebugCapture done; retry path is Track I's conditional Rung 2, not yet needed/shipped

→ Detailed checklist: `TODO-phase2-stage-p2.md` (created at implementation)

---

## Stage P3 — Data audit & error fixing  (ADR-019; priority per ADR-017)
**Done when:** `python -m audit` is clean (or every finding explicitly waived with a note); the 29
fuzzy-duplicate pairs and 203 `relationships_flagged_for_review.json` rows are triaged;
`relation_aliases` is live and applied by seedgen; eval (3-run) shows DATA/MIXED ≥ baseline and zero
stable regressions.

- [ ] `ingestion/audit/` package (`python -m audit`, read-only): A1 duplicate entities
      (rapidfuzz + transliteration heuristics), A2 candidate-drop accounting, **A3
      direction/integrity — cycle detection (self-loop / 2-cycle / longer) as first-class invariant,
      authored in P2, run every batch** + symmetric duplicates + DEV-040 invariants, A4 relation-label
      taxonomy → initial `relation_aliases` map, A5 alias/participant integrity
- [ ] `relation_aliases(alias PK, canonical, inverse BOOLEAN)` migration (new Phase-2 V-number);
      wire into `seedgen/relationships_gen.py` (apply map at generation; swap from/to on inverse)
- [ ] Triage backlogs: 29 fuzzy-dup pairs (merge + alias, DEV-043 pattern); 203 flagged relationships
- [ ] Fix loop each batch: edit candidate JSON → `seedgen --strict` → `reseed-local.sh` → `audit`
      clean → eval `--runs 3` → `compare.py` → commit (candidates + migrations + results) or revert
- [ ] Confirm `SchemaIntrospector` reflects the shrunk relation vocabulary
- [ ] Log DEV entries for any deviation from plan

→ Detailed checklist: `TODO-phase2-stage-p3.md` (created at implementation)

---

## Stage P4 — Iterative conflict-depth loop  (gold set grows in lockstep; ADR-010 questions land here)
**Done when:** the loop has run ≥3 batches end-to-end; `variant_claims` covers ≥4 claim_types and
all top-20-prominence subjects; the gold set is ≈25 questions with per-category floors enforced;
overall ≥75% sustained across a 3-run eval. *(The loop continues past this gate.)*

- [ ] Per batch (~25–50 groups): rank the 838 unreviewed groups by subject prominence; prioritize
      new claim_types beyond parentage/death (marriage, killer/slaying, birthplace, transformation)
- [ ] Review & promote in `notebooks/02_verify_conflicts.ipynb` (trust_tier 3→1, ADR-004 gate); new
      surface variants → `claim_type_aliases` follow-up migration (V9_2 precedent), never code
- [ ] Regenerate → reseed → audit → eval → compare → commit-or-revert (the P3 fix loop)
- [ ] Grow the gold set in the same commit: first batch adds ADR-010 backlog (REFUSAL Q16/Q17,
      enrichment-on-non-CONFLICT-route, schema-boundary); later batches add 1–3 questions per new
      data slice with **live-verified** keywords (DEV-050); old questions kept as regression
      sentinels; raise CONFLICT floor as the category grows
- [ ] Optional: add the LLM-judge scoring column once the deterministic loop is stable (ADR-018)

→ Detailed checklist: `TODO-phase2-stage-p4.md` (created at implementation)

---

## Stage P5 — New data types & systematic gap discovery
**Done when (per sub-stage):** its new gold questions pass, all sentinels stay green, per-category
floors hold across a 3-run eval; the relevant ADR/DEV entries are logged.

- [ ] **P5a** — numeric data (**activates ADR-009 → Accepted**): `contingents` table (new V-number),
      bounded extraction reusing instructor/checkpoint + `ref_ranges.py`, seedgen extension, numeric
      gold questions incl. one `ship_count` conflict
- [ ] **P5b** — myths & participants: grow beyond 5 myths (Trojan cycle — "died at Troy" has no
      structured backing, DEV-054 Q11); MIXED over-constraint prompt fix (SQL encodes only structured
      predicates), verified by Q11
- [ ] **P5c** — geography/epithets: places as attributes or a small table; epithets → `entity_aliases`
- [ ] Schema-prompt co-evolution each sub-stage: schema comments + `SchemaIntrospector` vocabulary
      (frequency-ordered, DEV-041); a new gold question verifies the model uses each new table
- [ ] Maintain `docs/DATA-GAPS.md` (triage-fed backlog) — it selects the next sub-stage; reconsider a
      minimal `query_log` only if real web traffic exists (weigh the write-grant exception)

→ Detailed checklist: `TODO-phase2-stage-p5.md` (created at implementation)

---

## Cross-cutting rules (apply to every stage)

- **Flyway checksum trap:** regenerate V10–V12 freely only while local-only; once a shared env has
  applied them, corrections are additive migrations (`V12_1`-style). New tables always get fresh
  V-numbers.
- **Root cause first, code fix only if still needed.** For every defect, diagnose and correct the
  underlying cause (data / existing prompt rule), reseed, and **re-measure before writing new code**.
  A workaround (prompt rule, query-time bound, retry, migration) ships only on *evidence* that the
  cause-level fix left the question failing — never pre-emptively stacked on an unreproduced defect.
- **Never act on a single-run delta** — the 3-run stable/flaky classification is the contract.
- **Keyword edits are logged eval-bug fixes** (live-verified, DEV-048/050), never silent tuning.
- **Embedding preservation:** never `down -v`; `reseed-local.sh` is the only sanctioned reseed path.
- **Deviation protocol (CLAUDE.md):** log DEV entries; annotate with banners; ADR status flips
  (ADR-009 at P5a) recorded properly.
