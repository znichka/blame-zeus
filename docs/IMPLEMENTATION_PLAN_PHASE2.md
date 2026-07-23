# blame-zeus: Implementation Plan — Phase 2 (Data-Quality & Evaluation Program)

> **Continuation of `IMPLEMENTATION_PLAN.md`.** The MVP plan (§1–§11) remains authoritative and
> unchanged; this document is the authoritative *design* for Phase 2. It implements **ADR-017**
> (direction), **ADR-018** (evaluation harness), and **ADR-019** (relation canonicalization). The
> staged checklist and "Done when" gates live in **`TODO2.md`**. The *why* lives in the ADRs — this
> plan gives the *what* and *how* and references the ADRs rather than re-justifying them.
>
> Numbering is local to Phase 2 (§1…§10). Stages are labelled **P1–P5** to avoid collision with the
> MVP's §9 Stages 1–11.

---

## 1. Rationale & operating model

The MVP answers questions but cannot be *measured* or *debugged*, and its seed data has documented
errors and gaps (ADR-017 §Context). Phase 2 adopts a **measurement-first, evaluation-gated** loop:

1. Build the evaluation harness and commit a **baseline** before touching data (P1).
2. Make wrong answers **diagnosable** and fix the two known runtime defects (P2).
3. **Audit and fix** the existing seed — the priority per ADR-017 §Decision 4 (P3).
4. **Iterate** conflict depth in eval-gated batches, growing the gold set in lockstep (P4).
5. Add **new data types** and discover gaps systematically (P5).

Every data/pipeline change is accepted only if a **3-run** eval comparison shows no *stable*
regression. All eval results are committed as timestamped artifacts, so answer quality is diffable
in git history. A shared triage taxonomy — **pipeline-bug / data-gap / corpus-gap / eval-bug** —
classifies every eval failure and selects the next stage's work.

---

## 2. Evaluation harness (P1) — implements ADR-018

### 2.1 Package layout

A standalone Python operator tool, **not** part of the Gradle build or CI (ADR-018 §Decision 2),
run against a live server:

```
evaluation/
├── gold-questions.json          (existing fixture; grows per ADR-010 in P4)
├── eval-config.json             (NEW — per-category floors, target, base-url default)
├── runner/
│   ├── __main__.py              (CLI: --runs, --label, --base-url, --questions, --ids, --debug)
│   ├── scoring.py               (§7 rubric verbatim + ADR-010 per-category floors)
│   ├── report.py                (writes results/<UTC>__<sha>__<label>/)
│   └── compare.py               (baseline vs candidate → diff.md)
└── results/                     (committed run artifacts; one dir per run)
```

CLI preflight: `GET /api/v1/sources` to confirm the server is up and seeded before scoring.

### 2.2 Scoring (`scoring.py`)

Implements `IMPLEMENTATION_PLAN.md §7` exactly — 3 pts/question:
- **Route match (1 pt):** `routeDecision == expected_route`. CONFLICT-category questions are scored
  on `conflicts[]`, never route (ADR-007/DEV-014, already reflected in §7's banner).
- **Author/conflict check (1 pt):** FACT/MIXED → ≥1 `required_authors` in `citations[]`; CONFLICT →
  `conflicts[]` has ≥ `conflicts_min_count` distinct `claimValue`s (plus the per-author check only
  when `required_authors.size >= 2`, the Q14 guard); DATA/REFUSAL → auto-1 if route matches.
- **Content check (1 pt):** word-boundary keyword regex over `answer` (CONFLICT: over
  `conflicts[].claimValue`); `forbidden_patterns` any-match = fail; plus per-question guards
  `sql_must_contain` (Q9 `WITH RECURSIVE`) and `min_row_count` (Q10 ≥12, re-executing the generated
  SQL via a **read-only** `psycopg2` connection as `zeus_app` under a statement timeout).
- **REFUSAL content:** implement `refusal_criteria` (phrase-list + empty-`citations[]` heuristics per
  §7) **now, in P1** — even though no REFUSAL question is authored until P4 — so P4's Q16/Q17 need no
  scorer change when they land.

**ADR-010 amendments (accepted at P1):** report **per-category pass rates with floors** in addition
to the blended aggregate; floors configured in `eval-config.json` (e.g. overall ≥75%, CONFLICT floor,
DATA floor; REFUSAL floor once REFUSAL questions are authored in P4).

### 2.3 Nondeterminism & artifacts

- `--runs N` runs the whole set N times; each question is classified **stable-pass** (N/N),
  **flaky** (mixed), or **stable-fail** (0/N). Aggregate = worst run (pessimistic), flaky list
  called out. `serviceError:true` is a scored failure, never retried; only transport/HTTP errors
  retry once (ADR-018 §Decision 4).
- `report.py` writes per run: `raw_responses.json` (full `QueryResponse` per question per
  repetition — with P2's `DebugInfo` this becomes a complete forensic record), `scores.json`
  (per-question/per-point, per-run + aggregated), `report.md` (human table + flakiness class +
  triage taxonomy column).
- `compare.py <baseline> <candidate>` → `diff.md`: PASS→FAIL regressions first, per-category deltas,
  route changes, conflict-count changes. Used at every later stage's gate.

**Exit (P1):** `python -m runner --runs 3 --label baseline` produces a committed baseline dir; every
failing question is triaged in `report.md`. Expect Q9/Q12 pipeline-bug (serviceError); Q13 is
expected to **pass** at baseline (DEV-056/DEV-057, confirmed in P2 per §3.4) — treat a Q13 failure as
a signal to reopen it, not the baseline expectation.
Triage also **decides the Q14 route-label question** — gold labels it RAG via SQL-empty fallback, but
DEV-054's stronger schema grounding sometimes makes SQL return rows (the Stage 8.5 "Watch" item). Pick
the authoritative label at baseline and record it as an eval-bug fix if the gold label changes.

---

## 3. Debuggability & known-defect fixes (P2)

### 3.1 Logging

Add to `application.yml` (or a `debug` profile): `logging.level.com.blamezeus.coreapi: DEBUG` — this
turns on the already-present DEBUG lines for generated SQL (`SqlQueryHandler`), probe/lookup
(`QueryService.fetchClaims`), and retrieval. Zero code change, immediate payoff.

### 3.2 Debug surface

- `QueryRequest` gains `debug: Boolean = false`.
- `QueryResponse` gains `debug: DebugInfo?` annotated `@JsonInclude(NON_NULL)` — the public contract
  is unchanged when off.
- `DebugInfo` carries: `probeSubject`, `probeClaimType`, `claimRowCount`, `firstAttemptSql` (the
  DEV-057 discarded SQL), `sqlRows` (capped, first ~25), `retrievedChunks` (id, source_id,
  passage_ref, score), `fallbackFromSqlToRag`, `composerSucceeded`, `draftAnswer` (pre-composition).
- Implementation: a **`ThreadLocal` singleton `DebugCapture`** (a plain bean with a constructor
  default `= DebugCapture()`, **not** a `@Scope("request")` proxy) appended to by `SqlQueryHandler`,
  `MixedQueryHandler` (Q12's SQL step is here), the chunk retriever, and `QueryService`;
  `QueryService` attaches it to the response only when `debug` is requested (reset at entry, attached
  at a single `finalize()` funnel). The pipeline is fully synchronous on the request thread, so a
  `ThreadLocal` is sufficient and — unlike a request-scoped proxy — keeps every existing
  handler/retriever unit test constructible without a web/proxy context. Smallest change that exposes
  retrieval internals without redesigning `RagResponse`.

### 3.3 Local reseed script

`scripts/reseed-local.sh` — the sanctioned path to re-apply migrations V10–V14 (only the seedgen-owned
V10–V12 change content; V13/V14 are re-applied unchanged) **without** destroying embeddings. As Flyway
superuser, app stopped:
- **`DROP TABLE entity_aliases;`** — *not* `DELETE FROM`: `V14__create_entity_aliases.sql` is a bare
  `CREATE TABLE` (no `IF NOT EXISTS`), so it must be dropped for V14 to re-apply cleanly (V14 both
  creates and seeds it).
- `TRUNCATE myth_participants, variant_claims, relationships, myths, entities CASCADE;`
  (`narrative_chunks` has no entity FK — safe).
- `DELETE FROM flyway_schema_history WHERE version IN ('10','11','12','13','14','15','16');` —
  **must include V15 and V16.** Flyway won't re-apply a migration below the current max applied
  version, so leaving V16 in history makes it silently skip re-applying V10–V14; V15/V16 are
  COMMENT-only and idempotent, so re-applying them is harmless.
- Restart → Flyway re-applies V10–V16 (+ anything newer) in order; the `afterMigrate` callback
  re-grants `zeus_app`.

**Never** `docker compose down -v` (it drops `narrative_chunks` → costly OpenAI re-embed). The script
guards against running when a shared environment exists (see §8, the Flyway checksum trap).

### 3.4 Known-defect fixes (both pipeline-bugs — fix before data stages so they don't pollute measurements)

**Operating principle for every defect below: root cause first, code fix only if still needed.** Each
item is a staircase — diagnose and correct the underlying cause (usually data or an existing prompt
rule), **reseed, and re-measure** before writing any new code. A code change (prompt rule, query-time
bound, retry, migration) is added only on *evidence* that the cause-level fix left the question
failing or flaky, and each rung is gated on the previous rung's eval result. We do not pre-emptively
stack workarounds on top of a defect we have not yet reproduced against clean data.

- **Q13 raw-column-dump / empty relationship passageRef (DEV-053) — likely already fixed; verify, do
  not re-implement.** DEV-056's `AnswerComposer` prose-ifies the dump and `TextToSqlAgent` **already
  mandates `r.passage_ref AS passage_ref`** (DEV-057; `TextToSqlAgent.kt:34-35,54,74-78`), with
  `SqlQueryHandler.extractCitations` reading it case-insensitively. So the P1 baseline is expected to
  show Q13 **passing**; P2's job is to **confirm that at baseline**, not to add a projection rule.
  Only if the baseline still shows the dump/empty passageRef is a further prompt tweak new work.
- **Q9/Q12 `WITH RECURSIVE` fragility (DEV-054) — root cause first, code fix only if still needed.**
  This addresses the existing **Stage 8.5 gap (ii)** (`docs/TODO.md:220-265`), but **supersedes** that
  entry's "likely fix: … + a cycle guard": a *silent query-time* cycle guard is rejected below in
  favour of root-cause-first offline cycle *detection* (audit A3) plus fixing the reversed edges in
  data. The runaway recursion / 3 s timeout is **primarily a data-integrity symptom, not LLM SQL
  fragility**: a `parent_of` walk can only recurse forever if the relation graph has a **cycle**, and
  a genealogy is a DAG — so a cycle is almost always a **reversed-direction edge** (the
  DEV-040/DEV-015 direction class). A silent query-time cycle-guard would only *mask* the bad data and
  still emit a wrong lineage. So the work is a staircase, each rung gated on the previous rung's eval:
  - **Rung 0 — fix the data (the actual fix; always done first).** Author a **cycle-detection check**
    over the `relationships` graph **now in P2** (it root-causes Q9/Q12; thereafter it is audit check
    **A3**, §4.1). It walks each transitive relation and **lists every cycle with the specific edges +
    sources** (a self-loop or 2-cycle is a near-certain reversed edge). Run it against the current
    seed **before touching any SQL or prompt**; correct the offending edges in the candidate JSON
    (reverse/drop, source as tie-breaker per `canonical_edge.py`) → `reseed-local.sh` → **re-run the
    eval.** If Q9/Q12 now answer over a clean DAG, **stop here — no code change ships.**
  - **Rung 1 — LOUD query-time bound, only if a clean DAG still fails/flakes.** *If and only if* the
    reseeded eval still shows Q9/Q12 stable-fail or flaky, add a bounded `WITH RECURSIVE` few-shot
    (depth cap + `visited`-id array) to `TextToSqlAgent.generateSql`. It must leave a breadcrumb — the
    debug surface's `sqlRows` shows whether the visited-array truncation fired (a revisited id = a
    live data cycle Rung 0 missed, sent back to A3), never a silent guard.
  - **Rung 2 — error-corrective retry, only if the failure is malformed CTE grammar (not data).** *If*
    the debug surface shows the failure is a generation/validation exception rather than a data cycle,
    wrap generate+execute in `runSqlWithErrorRecovery(question)` that re-asks via a new
    `TextToSqlAgent.regenerateAfterSqlError(schema, question, priorSql, dbError)` (same `routingModel`,
    temp 0.0) through the shared `executeValidated`; if the retry also fails, **rethrow the ORIGINAL
    error**. Place it in **both `SqlQueryHandler` and `MixedQueryHandler`** (Q12 fails in the MIXED
    handler's SQL step), and give DEV-057's attribution retry its own `try/catch` ("never worse").
  - **Rung 3 — `V-migration` ancestry helper** (bounded recursive view/function advertised via
    `SchemaIntrospector`, the V15/V16 schema-channel precedent) **only if** clean data + Rungs 1–2
    still leave Q9/Q12 stable-fail — **on evidence.**

### 3.5 `query_history` — deliberately skipped for the PoC

Not built now: (a) the eval runner already persists full responses (incl. `DebugInfo`) per run,
covering the forensic need; (b) the runtime user `zeus_app` is read-only by guardrail, so history
writes would need a grant change; (c) there is no organic traffic yet. Revisit in P5 if real web
usage appears.

**Exit (P2):** the A3 cycle-detection check reports the `parent_of` graph clean (or lists + fixes the
reversed edges it found); eval `--runs 3 --debug` vs baseline via `compare.py` — Q9/Q12 no
serviceError and content point earned (now answering over a genuine DAG, not a bounded-but-wrong
walk), Q13 **confirmed passing**, zero stable regressions; `raw_responses.json` now carries probe
output, retrieved chunk refs, SQL rows, first-attempt SQL. `:core-api:test` green (retry path,
cycle-detection check, and DebugCapture unit-tested, `@AiService` mocked, TDD).

---

## 4. Data audit & relation canonicalization (P3) — implements ADR-019

> ⚠️ Deviations occurred in this stage. See DEVIATIONS.md for details (DEV-070 through DEV-083 as
> of the second Track I pass — the audit runner + all five checks, `relation_aliases` (Track F),
> two fix-loop passes, and the Track J3 cycle-conflation triage; detailed checklist:
> `docs/TODO-phase2-stage-p3.md`).

### 4.1 Audit package

`ingestion/audit/` (`python -m audit`, read-only over candidate JSON + live DB; emits
`ingestion/audit/reports/<date>.md` + machine-readable findings JSON). Checks:

- **A1 — duplicate entities:** `rapidfuzz` full-pairs over V10 names + transliteration heuristics for
  the known bug class (K↔C, `-os`↔`-us`, `-e`↔`-a`, `Ou`↔`U` — the Cronos/Cronus, Athene/Athena,
  Ocean/Oceanus pattern, DEV-043). Cross-check `entity_aliases` + `known_aliases.json`; unaliased
  pairs → triage.
- **A2 — candidate-drop accounting:** explain the 6,026→2,496 relationship drop by reason
  (unknown-entity-name, contested-edge collapse, dedupe). Unknown-name drops are where missing/split
  entities hide (the Io precedent, DEV-042).
- **A3 — direction/integrity:** **cycle detection over transitive relations is the first-class
  invariant here** (authored in P2 for Q9/Q12, then run every batch). Any cycle in `parent_of` —
  self-loop, 2-cycle (`A parent_of B` **and** `B parent_of A`), **or longer** — is a near-certain
  reversed-direction edge, since a genealogy is a DAG; the check lists each cycle's edges + sources
  so they can be reversed/dropped at the candidate-JSON layer. Plus symmetric duplicates, direction
  spot-checks against a small hand-truth list, and DEV-040's invariants re-run after every fix batch.
  This is the mechanism that makes the "recursion failure ⇒ find the bad data" loop a standing
  regression gate, not a one-off.
- **A4 — relation-label taxonomy:** frequency-classify all 131 labels into canonical / synonym /
  inverse / legit-long-tail → **produces the initial `relation_aliases` map** (ADR-019).
- **A5 — alias/participant integrity:** every alias target exists; no alias equals a canonical name;
  `myth_participants` names resolve.

### 4.2 `relation_aliases` (ADR-019)

New Phase-2 Flyway migration creating `relation_aliases(alias PK, canonical, inverse BOOLEAN)` (DDL
sketch in §7). `seedgen/relationships_gen.py` applies the map at generation time — swapping
`from_id`/`to_id` on `inverse` labels — exactly as `variant_claims_gen.py` applies the claim-type
map. Shrinks `SchemaIntrospector`'s relation vocabulary → better text-to-SQL.

### 4.3 Backlogs & fix loop

Work the documented backlogs: the 29 fuzzy-dup pairs (merge at candidate-JSON layer + alias, DEV-043
pattern) and the 203 `relationships_flagged_for_review.json` rows (promote-with-fix or reject,
recorded in the file). **Fix loop (used from here on):** edit candidate JSON → `python -m seedgen
--strict` → `scripts/reseed-local.sh` → `python -m audit` (must be clean) → eval `--runs 3` →
`compare.py` → commit (candidates + migrations + results together) or revert. The audit run becomes
a permanent pre-seedgen gate.

**Exit (P3):** all audit checks pass or are explicitly waived with a note; both backlog files
triaged; `relation_aliases` live and applied; DATA/MIXED ≥ baseline, zero stable regressions.

---

## 5. Iterative improvement loop (P4) — conflict depth

Repeatable batch (~25–50 conflict groups each) over the 838 unreviewed groups:

1. **Pick a tranche** — rank groups by subject prominence (relationship degree in V11 / mention
   count; the audit package emits the ranking). Prioritize **new claim_types beyond
   parentage/death** drawn from the actual candidate distribution (audit emits it): likely
   marriage/spouse, killer/slaying, birthplace, transformation.
2. **Review & promote** in `notebooks/02_verify_conflicts.ipynb` (existing tool): trust_tier 3→1,
   the ADR-004 human gate. New claim-type surface variants → `claim_type_aliases` follow-up
   migration (V9_2 precedent), never code.
3. **Regenerate & reseed:** `seedgen --strict` → `reseed-local.sh` → `audit`.
4. **Grow the gold set in the same commit** — where ADR-010's authoring lands, spread across
   batches: first batch adds the ADR-010 backlog (REFUSAL Q16/Q17, an enrichment-on-non-CONFLICT-route
   question, a schema-boundary question); each later batch adds 1–3 questions targeting the newly
   promoted data with **live-verified** keywords (the DEV-050 rule). Old questions are never removed
   — they are the regression sentinels. Raise the CONFLICT floor as the category grows.
5. **Eval + compare + decide:** `--runs 3` → `compare.py` vs the last accepted run. Green → commit
   candidates + migrations + gold set + results together. Red → triage (data-gap / pipeline-bug /
   eval-bug), fix or revert the batch. The optional **LLM-judge column** (ADR-018 §Decision 3) may
   be added here once the deterministic loop is stable.

**Exit (P4, the loop continues after):** ≥3 batches end-to-end; `variant_claims` covers ≥4
claim_types and all top-20-prominence subjects; gold set ≈25 with per-category floors enforced;
overall ≥75% sustained across 3-run evals.

**Risk:** more claim_types stress `ConflictProbe`'s phrasing sensitivity — track flaky CONFLICT
questions separately before touching the probe prompt (ADR-007 warns against over-enumerating
surface forms; the RAG backstop is the designed complement).

---

## 6. New structured data types & gap discovery (P5)

Independently shippable sub-stages, each with its own gold questions and schema-prompt co-evolution
(schema comments + `SchemaIntrospector` vocabulary, frequency-ordered per DEV-041):

- **P5a — numeric data (activates ADR-009):** `contingents(leader entity ref, origin, ship_count,
  source_id, passage_ref)` (new V-number migration); a bounded extraction script reusing the
  `instructor`/checkpoint machinery + `ref_ranges.py`; a `seedgen` extension; numeric gold questions
  including one `ship_count` conflict. **ADR-009 flips to Accepted here.**
- **P5b — myths & participants:** grow beyond 5 myths (the Trojan cycle especially — DEV-054's Q11
  "died at Troy" has no structured backing); plus the MIXED over-constraint fix (teach
  `TextToSqlAgent`/`MixedQueryHandler` that MIXED SQL encodes only structured predicates, DEV-054
  gap (i)), verified by Q11.
- **P5c — geography/epithets:** locations as entity attributes or a small `places` table; epithets
  flow into `entity_aliases` (improves `ConflictLookup` resolution and entity matching).
- **Gap-discovery machinery:** every eval `report.md` carries the triage taxonomy; maintain a running
  `docs/DATA-GAPS.md` backlog fed by triage, which selects the next sub-stage. Only here, if real web
  usage exists, reconsider a minimal `query_log` table (weigh the write-grant exception vs the
  guardrail; eval artifacts may still suffice).

**Exit (per sub-stage):** its new gold questions pass, all sentinels stay green, per-category floors
hold across a 3-run eval; ADRs/DEV entries logged per the deviation protocol.

---

## 7. Data-model additions (sketches)

```sql
-- ADR-019 (P3)
relation_aliases(alias TEXT PRIMARY KEY, canonical TEXT NOT NULL,
                 inverse BOOLEAN NOT NULL DEFAULT FALSE);

-- ADR-009 (P5a) — indicative
contingents(id SERIAL PK, leader_id INT→entities, origin TEXT, ship_count INT,
            source_id TEXT→sources, passage_ref TEXT);
```

```kotlin
// P2 debug surface (indicative)
data class DebugInfo(
  val probeSubject: String?, val probeClaimType: String?, val claimRowCount: Int,
  val firstAttemptSql: String?, val sqlRows: List<Map<String, Any?>>,
  val retrievedChunks: List<ChunkRef>, val fallbackFromSqlToRag: Boolean,
  val composerSucceeded: Boolean, val draftAnswer: String?,
)
```

New `variant_claims.claim_type` values (P4) are added as data + `claim_type_aliases` rows, not schema
changes. New Flyway migrations always take a fresh V-number (§8).

---

## 8. Risks & cross-cutting rules

- **Flyway checksum trap.** Free regeneration of V10–V12 is legal only while **no shared environment**
  has applied them (currently true — local-only). The moment a demo/shared DB applies them,
  corrections must land as additive migrations (`V12_1`-style, the V8_1–V8_4 / V9_1–V9_2 precedent);
  regenerating an applied file breaks `flyway validate` everywhere. New tables always get fresh
  V-numbers. This rule lives in `scripts/reseed-local.sh` and `ingestion/audit/README`.
- **Flakiness vs regression.** Never act on a single-run delta; the 3-run stable/flaky classification
  is the contract.
- **Keyword brittleness.** Keywords are live-verified (DEV-048/050); a keyword edit is a logged
  **eval-bug** fix, never silent tuning to make a run pass.
- **Embedding preservation.** Never `down -v`; `reseed-local.sh` is the only sanctioned reseed path.
- **Entity-merge fallout (P3).** Merging entities changes ids/names that
  `variant_claims_candidates.json` and V13 name-based subqueries reference — `seedgen --strict` +
  audit A5 catch this; run the full chain every batch.

---

## 9. Critical files

- `evaluation/gold-questions.json` — the yardstick; runner input; ADR-010 expansion target (P4).
- `evaluation/runner/`, `evaluation/eval-config.json` — the harness (P1, new).
- `scripts/reseed-local.sh` — sanctioned reseed (P2, new); `ingestion/audit/` — audit package (P3, new).
- `ingestion/seedgen/__main__.py`, `seedgen/relationships_gen.py` — regeneration loop +
  `relation_aliases` wiring (P3).
- `core-api/.../service/QueryService.kt` — debug-surface attachment; orchestrates all measured behavior.
- `core-api/.../handler/SqlQueryHandler.kt` — Q13 citations + error-corrective retry (P2).
- `core-api/.../ai/TextToSqlAgent.kt` — `passage_ref` projection prompt rule (P2).
- `core-api/.../config/SchemaIntrospector.kt` — schema→model channel every data expansion co-evolves.
- `core-api/src/main/resources/application.yml` — DEBUG logging (P2).
- `ingestion/extraction/output/*.json` — the editable source of truth for all seed fixes.

## 10. Verification

1. **P1:** start stack (`scripts/run-local.sh`), `python -m runner --runs 3 --label baseline`,
   confirm committed results dir + triaged `report.md`.
2. **P2:** re-run eval `--debug`; confirm Q9/Q12/Q13 fixed, no stable regressions; `./gradlew
   :core-api:test` green.
3. **P3–P5:** every batch ends with `audit` clean + `compare.py` showing no stable PASS→FAIL; the
   per-category floors hold; results dirs committed as the audit trail of quality over time.
