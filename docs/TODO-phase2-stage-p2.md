# Stage P2 — Debuggability + known-defect fixes: Detailed Checklist

**Done when:** (1) the **audit-A3 cycle-detection check** (Track G) reports the `parent_of` graph clean, or lists the
reversed edges it found and those are corrected at the candidate-JSON layer; (2) a `POST
/api/v1/query` with `{"debug": true}` returns a populated `DebugInfo` (probe subject/claimType, claim
count, first-attempt + capped SQL rows, retrieved chunk refs, fallback/composer flags, draft answer),
and the public contract is **byte-for-byte unchanged** when `debug` is absent/false; (3) `Q9`/`Q12` no
longer return `serviceError` and earn their content point over a genuine DAG; (4) `Q13` is **confirmed
passing** (not re-implemented); (5) `scripts/reseed-local.sh` re-applies V10–V16 without dropping
`narrative_chunks` embeddings; (6) `./gradlew :core-api:test` is green (DebugCapture, the debug
attachment funnel, and any shipped retry path unit-tested, `@AiService` mocked, TDD); (7) `python -m
runner --runs 3 --label p2 --debug` + `compare.py <baseline> <p2>` shows the Q9/Q12/Q13 fixes and
**zero stable regressions**; the results dir is committed.

> **Design source of truth:** `IMPLEMENTATION_PLAN_PHASE2.md §3` (the *what/how* — logging, debug
> surface, reseed script, the four-rung defect staircase, the `query_history` skip) and `§7`/`§9`
> (DTO sketch, critical files); `ADR-018 §Decision 4` (serviceError-scored-fail, no retry); the
> **Stage 8.5 gap (ii)** entry in `docs/TODO.md:220-265` (superseded here by root-cause-first). This
> checklist is the *granular task breakdown* — it does not re-justify the design.

> **Operating principle for every defect below (CLAUDE.md + §3.4):** **root cause first, code fix only
> if still needed.** Each defect is a *staircase*: diagnose and correct the underlying cause (usually
> data or an existing prompt rule), **reseed, and re-measure** before writing any new code. A code
> change (prompt rule, query-time bound, retry, migration) ships **only on evidence** that the
> cause-level fix left the question failing or flaky. **Do not pre-emptively stack workarounds on a
> defect not yet reproduced against clean data.** Concretely: Rung 0 (data fix) is always done; Rungs
> 1→3 each ship *only if* the previous rung's 3-run eval still shows Q9/Q12 stable-fail/flaky **and**
> (for Rungs 2–3) the residual failure matches that rung's own trigger (I6/I7). The eval-still-fails
> gate is **necessary but not, by itself, sufficient** for the later rungs — it is not a plain
> biconditional.

Before starting, re-read `DEVIATIONS.md` (deviation protocol). Relevant carry-overs:
- **DEV-054** — Q9/Q12 `WITH RECURSIVE` `serviceError` and the Q14 route-label ambiguity are the
  known runtime defects. Q14 was already resolved at P1 (route decided **SQL**, gold relabeled,
  DEV-063). P2 owns the Q9/Q12 half. The root cause is treated as **data-integrity (a graph cycle =
  a reversed-direction edge), not LLM SQL fragility** — a silent query-time cycle guard is *rejected*
  (§3.4) in favour of offline cycle *detection* + fixing the data.
- **DEV-053 / DEV-056 / DEV-057** — Q13 is **expected to pass** at baseline (DEV-056's
  `AnswerComposer` prose-ifies the raw dump; `TextToSqlAgent` **already mandates** `r.passage_ref AS
  passage_ref`, `TextToSqlAgent.kt:34-35,54,74-78`). P2's Q13 job is **verify at baseline, do not
  re-implement.** Only a still-broken baseline makes a prompt tweak new work.
- **DEV-057** — the SqlQueryHandler attribution retry (`generateSqlWithAttribution`) already exists and
  regenerates once; its *discarded first-attempt SQL* is exactly what `DebugInfo.firstAttemptSql`
  must surface. Give this retry its own `try/catch` if Rung 2 lands ("never worse").
- **DEV-055** — the `:core-api:test` suite mocks every `@AiService`; the debug wiring, retry path, and
  DebugCapture must be unit-tested with mocked AI services, TDD (failing test first).
- **DEV-040 / DEV-015 / DEV-042 / DEV-043** — the reversed-edge / direction class and the entity
  dup/merge class Rung 0 will surface. The Io precedent (DEV-042) shows how an "unknown-name" drop
  hides a split entity; direction fixes land at the **candidate-JSON layer**, then `seedgen`.
- **P1 baseline** — `evaluation/results/2026-07-22T19-02-10Z__de6de91__baseline/` is the diff target.
  Baseline was **10/16 (62.5%)**; Q9 serviceError (stable-fail), Q12 flaky (intermittent `serviceError`
  — the underlying reversed-edge/cycle is deterministic, but LLM SQL generation is non-deterministic,
  so a recursive query is only *sometimes* emitted), Q13 pass (3/3). Q6/Q7/Q8/Q11
  are triaged **data-gap → P3/P5b**, *not P2* — do not try to fix them here.

**Deviation protocol:** the debug surface, the cycle-detection check location, and any shipped rung
are all **new** relative to the MVP `IMPLEMENTATION_PLAN.md`. Log each as the next `DEV-NNN`
(next free number is **DEV-064**) and annotate per the CLAUDE.md protocol. Reserve, indicatively:
DEV-064 debug surface + DebugCapture ThreadLocal; DEV-065 reseed-local.sh; DEV-066 cycle-detection
check (→ audit A3); DEV-067+ each reversed-edge data fix and any Rung 1–3 code that actually ships.

---

## Contracts verified against the live tree (code against these exact shapes)

- **`QueryRequest`** (`domain/dto/QueryRequest.kt`) is today `data class QueryRequest(val question:
  String)` — add `debug: Boolean = false` (trailing, defaulted → every existing construction/JSON
  body stays valid; an absent `debug` deserializes to `false`).
- **`QueryResponse`** (`domain/dto/QueryResponse.kt`) has 7 fields ending in `conflictsInProse:
  Boolean = false`. Add `debug: DebugInfo? = null` (trailing, nullable, defaulted) annotated
  `@field:JsonInclude(JsonInclude.Include.NON_NULL)` so the serialized contract is unchanged when
  null. **Every `.copy(...)` site compiles untouched** (QueryService has 3; the handlers construct
  fresh). Confirm no test asserts an exact field *count* / full-constructor JSON equality.
- **`QueryService.handle(question: String)`** (`service/QueryService.kt:37`) is the single orchestrator
  and the only class that sees all handlers + the probe/lookup/compose stages. It has **three exit
  points** (serviceError branch `:69`, composed return `:73-80`, compose-catch `:83`) — all three must
  be routed through one `finalize()` funnel (Track C) so the debug attach/reset happens in exactly one
  place. `fetchClaims` (`:91`) already computes `probe.subject`/`probe.claimType` and the claim list —
  the probe fields and `claimRowCount` are captured there, not re-derived.
- **`SqlQueryHandler`** (`handler/SqlQueryHandler.kt`) holds `sql` (first attempt), the DEV-057 retry
  (`retrySql`, adopted only if it yields citations), and `EMPTY_RESULT_ANSWER` (the RAG-fallback
  sentinel `QueryService.handleSql` keys on `:141`). `firstAttemptSql` = the pre-retry `sql`;
  `sqlRows` = `finalRows` capped.
- **`MixedQueryHandler`** (`handler/MixedQueryHandler.kt:26-46`) runs Q12's SQL step (`generateSql` →
  `validate` → `queryForList` at `:27-31`) — this is where Q12's `serviceError` originates and where
  its `firstAttemptSql`/`sqlRows` must be captured.
- **`NarrativeChunkContentRetriever`** (`ai/NarrativeChunkContentRetriever.kt:47`) is invoked **inside
  LangChain4j's `retrievalAugmentor`**, deep under `RagAgent.answer(...)`, **on the same request
  thread** — QueryService never calls it directly. This is *exactly why* a **`ThreadLocal`
  `DebugCapture`** is the mechanism (§3.2): the retriever appends its `Row`s (id/source_id/passage_ref/
  score, `:82-85`) to the thread-local, and QueryService reads them back after `RagAgent` returns. A
  constructor-arg/param-threading approach cannot reach across the LangChain4j boundary; a
  `@Scope("request")` proxy would break every handler/retriever unit test's plain constructor.
- **`QueryController.query`** (`controller/QueryController.kt`) does `queryService.handle(request.question)`
  — becomes `handle(request.question, request.debug)`.
- **`application.yml`** has no `logging:` block yet and no profile files — §3.1 adds one line (or a
  `debug` profile). Datasource already sets `statement_timeout = '3s'` on Hikari; runtime user is
  `zeus_app` (read-only), Flyway user is `zeus`/superuser.
- **Migrations present:** V10–V14 (seedgen-owned V10–V12; V13 myths; V14 `entity_aliases` a **bare
  `CREATE TABLE`**, no `IF NOT EXISTS`), V15/V16 COMMENT-only + idempotent. `afterMigrate__grant_app_user.sql`
  re-grants `zeus_app`. **No V15/V16 in the seedgen output** — they are hand-authored, re-applied
  unchanged by the reseed.
- **Seedgen fix loop:** candidate JSON of record is `ingestion/extraction/output/*.json`
  (`relationships_candidates_cleaned.json` = a flat list of `{from_name, relation, to_name,
  is_contested, passage_ref, source_id}`, 6026 rows). `relationships_gen.py` →
  `canonical_edge.resolve_canonical_edges` renders V11. `parent_of`'s subject is the **child**
  (`to_name`); `from_id` = parent, `to_id` = child.

---

## Parallelization Guide

```
Track A  Debug contracts: DebugInfo + DebugCapture bean +   ─┐ (foundational — unblocks B, C, D)
         QueryRequest.debug + QueryResponse.debug             │
                                                              │
Track B  DebugCapture producers: SqlQueryHandler,   ─────────┤ needs A's DebugCapture + ChunkRef
         MixedQueryHandler, NarrativeChunkContentRetriever    │
Track C  QueryService finalize() funnel + attach/reset ──────┤ needs A; consumes B's captured fields
Track D  Controller + handle(question, debug) plumbing ──────┘ needs A (QueryRequest.debug)

Track E  application.yml DEBUG logging / debug profile  ──────  no code coupling — do anytime
Track F  scripts/reseed-local.sh                        ──────  no code coupling — do anytime
Track G  cycle-detection check (Python → audit A3)      ──────  ingestion/ only; independent of A–F
Track H  docs: query_history skip + DEV entries/banners ──────  pure prose — do anytime

Track I  reseed → run cycle check → fix data → eval → compare  SERIAL — needs A–H merged + live stack
  └─ Rung 1 (TextToSqlAgent few-shot)      \  CONDITIONAL — each ships ONLY IF the
  └─ Rung 2 (runSqlWithErrorRecovery retry)  } previous rung's 3-run eval still shows
  └─ Rung 3 (V-migration ancestry helper)  /  Q9/Q12 stable-fail/flaky (gated in Track I)
```

**Rule of thumb:** A is the only hard blocker for the Kotlin side (B/C/D branch off it). E/F/G/H are
fully independent and can proceed in parallel with A–D from minute one — **G (the cycle check) is on
the critical path for Q9/Q12 and should start immediately alongside A.** I is the integration gate;
its conditional rungs are the *only* place Q9/Q12 code may ship, and each is evidence-gated.

---

## Track A — Debug contracts + `DebugCapture` (foundational; do first)

Pins the interfaces B/C/D code against. Small; merge before B–D start in earnest. **Ships behind a
flag: zero behavior change when `debug=false`.**

- [x] **A1** — `domain/dto/DebugInfo.kt`: data class per §7 sketch —
      `probeSubject: String?`, `probeClaimType: String?`, `claimRowCount: Int`,
      `firstAttemptSql: String?`, `sqlRows: List<Map<String, Any?>>`,
      `retrievedChunks: List<ChunkRef>`, `fallbackFromSqlToRag: Boolean`,
      `composerSucceeded: Boolean`, `draftAnswer: String?`. Plus a nested/sibling
      `data class ChunkRef(val id: ..., val sourceId: String?, val passageRef: String?, val score: Double)`.
      (Retriever `Row` has no `id` column selected today — either add `nc.id` to `RETRIEVAL_SQL` (+ the
      `Row` mapper) in Track B, or make `ChunkRef.id` nullable and leave it `null`; pick one and state
      it in both A1 and B3 identically.) All fields defaulted where sane
      so a partially-filled capture serializes cleanly.
- [x] **A2** — `QueryRequest.debug`: add `val debug: Boolean = false` (trailing). Confirm the
      `@RequestBody` still deserializes a body with **no** `debug` key to `false` (Jackson/Kotlin
      default — add a controller/DTO test asserting it).
- [x] **A3** — `QueryResponse.debug`: add `val debug: DebugInfo? = null` (trailing) with
      `@field:JsonInclude(JsonInclude.Include.NON_NULL)`. **Contract-invariance test:** serialize a
      response with `debug = null` and assert the JSON has **no** `debug` key (byte-for-byte prior
      shape). Grep for any test asserting full-constructor equality / field count and update only if
      it exists.
- [x] **A4** — `service/DebugCapture.kt`: a **plain `@Component` bean** (constructor default
      `= DebugCapture()`, **NOT** `@Scope("request")`) wrapping a `ThreadLocal<MutableState>`. API:
      `reset()` (clear the thread-local at request entry), `snapshot(): DebugInfo` (build the DTO from
      accumulated state), and typed setters/appenders the producers call —
      `setFirstAttemptSql(sql)`, `setSqlRows(rows)`, `addRetrievedChunk(ref)` /
      `setRetrievedChunks(list)`, `setFallbackFromSqlToRag(b)`, `setComposerSucceeded(b)`,
      `setDraftAnswer(s)`, `setProbe(subject, claimType, rowCount)`. **Every accumulator is a no-op-safe
      write to the current thread's slot** — calling a setter with `reset()` never having run must not
      NPE (initialize the ThreadLocal via `withInitial`). Document that the pipeline is fully
      synchronous on the request thread, so a ThreadLocal is sufficient and keeps producer unit tests
      constructible without a web/proxy context.
- [x] **A5** — **TDD** `service/DebugCaptureTest.kt`: `reset()` then set each field → `snapshot()`
      returns them; a second `reset()` clears prior state (no bleed across simulated requests on the
      same thread); a `snapshot()` with nothing set returns an all-empty/defaults `DebugInfo` (never
      throws). Pure JVM, no Spring context, no DB.
- [ ] **A6** — commit A as one unit; note B/C/D may now branch. _(commit only on request per repo
      convention.)_

---

## Track B — `DebugCapture` producers (needs A; the three write sites)

Each producer **only writes to `DebugCapture`** — no behavior change, no reads. Guardable so the
writes are cheap even when debug is off (the snapshot is only *built* by QueryService when requested).

- [x] **B1** — `SqlQueryHandler`: capture `firstAttemptSql` = the immutable first-attempt `sql` (`:22`).
      The DEV-057 retry writes a **separate** `retrySql`/`finalSql` (`:49,55`) and never reassigns
      `sql`, so `sql` is still the first attempt at the `:61` return — there is no overwrite to race,
      capturing at `:61` is safe. Capture `sqlRows` = `finalRows` capped to the
      first ~25 (a `SQL_ROWS_CAP` const). Do it at the single `return QueryResponse(...)` (`:61`) and
      the `EMPTY_RESULT_ANSWER` early-return (`:28`) so an empty result still records the SQL it ran.
- [x] **B2** — `MixedQueryHandler`: capture `firstAttemptSql` = `sql` (`:27`) and `sqlRows` = `rows`
      capped (`:31`) — this is Q12's SQL step, the origin of its `serviceError`. Same cap const.
- [x] **B3** — `NarrativeChunkContentRetriever`: in `retrieve(...)` after `results` is computed
      (`:67`), `debugCapture.setRetrievedChunks(results.map { ChunkRef(it.id?, it.sourceId,
      it.passageRef, it.score) })`. **Decide the `id` question from A1** (use A1's exact alternatives):
      either add `nc.id` to `RETRIEVAL_SQL` + the `Row` mapper, or make `ChunkRef.id` nullable and leave
      it `null`. Inject `DebugCapture` via
      constructor (add the bean arg; existing tests construct with explicit args — update them to pass
      a real `DebugCapture()`).
- [x] **B4** — **Guard the cost:** the append sites are unconditional (cheap map builds), but the SQL
      row cap must be applied *at capture*, never storing thousands of rows. Confirm no producer reads
      the ThreadLocal or changes its return value — a `git diff` of each `handle()`/`retrieve()` shows
      only added capture lines.
- [x] **B5** — **TDD:** extend `SqlQueryHandlerTest`, `MixedQueryHandlerTest`, and the retriever test
      to inject a real `DebugCapture`, run `handle`/`retrieve`, and assert `snapshot()` carries the
      expected `firstAttemptSql`/`sqlRows`/`retrievedChunks` (mocked `@AiService`/`JdbcTemplate`).
      Assert the **return value is identical** with and without a fresh vs pre-reset capture (no
      behavior change).

---

## Track C — `QueryService` `finalize()` funnel (needs A; consumes B's captures)

The single place the debug snapshot is built + attached and the ThreadLocal is reset. **This is the
correctness-critical wiring** — a leaked ThreadLocal across pooled request threads is a real bug.

- [x] **C1** — `handle(question: String, debug: Boolean = false)`: `debugCapture.reset()` at the very
      top; wrap the whole body so **every** exit path (serviceError branch `:69`, composed return
      `:73-80`, compose-catch `:83` — the **same three** the contracts note enumerates; a router
      failure is **not** a separate exit, it sets `route = RAG` and flows into one of these three)
      funnels through one private
      `finalize(response: QueryResponse, debug: Boolean): QueryResponse`. Use `try { ... } finally {
      debugCapture.reset() }` so the thread-local is cleared even on an unexpected throw (no bleed to
      the next request on a reused thread).
- [x] **C2** — `finalize()` attaches `response.copy(debug = if (debug) debugCapture.snapshot() else
      null)`. When `debug=false`, `debug` stays `null` → NON_NULL omits it (Track A3's invariant).
- [x] **C3** — capture the QueryService-owned fields into `DebugCapture` at their natural points:
      `setProbe(probe.subject, probe.claimType, claims.size)` inside/after `fetchClaims` (`:91-104`);
      `setFallbackFromSqlToRag(true)` in `handleSql` on the `EMPTY_RESULT_ANSWER` RAG fallback (`:144`);
      `setDraftAnswer(draft.answer)` before composition; `setComposerSucceeded(true/false)` in the
      compose `try`/`catch` (`:73-84`).
- [x] **C4** — **TDD** extend `QueryServiceTest`: (a) `debug=false` → `response.debug == null` and the
      answer/route/citations are byte-identical to the pre-change behavior for SQL/RAG/MIXED and the
      serviceError branch; (b) `debug=true` → `response.debug` is populated with the probe fields,
      `fallbackFromSqlToRag`, `composerSucceeded`, `draftAnswer` for a fallback path and a composed
      path; (c) two sequential `handle(...)` calls on the same thread don't leak capture state (call
      1 debug, call 2 non-debug → call 2's `debug` is null and uncontaminated). Mock all `@AiService`.

---

## Track D — Controller / request plumbing (needs A's `QueryRequest.debug`)

- [x] **D1** — `QueryController.query`: `queryService.handle(request.question, request.debug)`.
- [x] **D2** — Confirm `WebController`/Thymeleaf (`index.html`) path is untouched — the web UI never
      sends `debug`, so it defaults to `false` and its response omits the key (no template change).
- [x] **D3** — **TDD/manual:** a `POST /api/v1/query {"question": "...", "debug": true}` slice/MockMvc
      test asserts the response body contains a `debug` object; a `{"question": "..."}` body asserts
      **no** `debug` key. (Full populated-DebugInfo assertion belongs to the live Track I run.)

---

## Track E — DEBUG logging (§3.1; no code — do anytime)

- [x] **E1** — `application.yml`: add `logging.level.com.blamezeus.coreapi: DEBUG` (or a `debug`
      Spring profile carrying it, if you want production quiet by default — pick one; the DEBUG lines
      already exist in `SqlQueryHandler`, `QueryService.fetchClaims`, the retriever). Zero code change.
- [x] **E2** — sanity: start the stack, fire one SQL and one RAG question, confirm generated-SQL,
      probe/lookup, and retrieval DEBUG lines appear. Note the profile/flag in `evaluation/README.md`
      or a one-liner so operators know how to turn it on for a `--debug` eval run.

---

## Track F — `scripts/reseed-local.sh` (§3.3; no code — do anytime)

The **only** sanctioned reseed path; **never** `docker compose down -v` (drops `narrative_chunks` →
costly OpenAI re-embed). Mirrors `run-local.sh`'s repo-root/`.env` bootstrap style.

- [x] **F1** — preconditions: app **stopped**, run as the **Flyway superuser** (`zeus`/`olympus`, the
      `POSTGRES_USER` creds — *not* `zeus_app`). Fail fast with a clear message if the app is up or
      creds are missing.
- [x] **F2** — **`DROP TABLE entity_aliases;`** (not `DELETE FROM`) — V14 is a bare `CREATE TABLE`
      (no `IF NOT EXISTS`) that both creates *and* seeds, so it must be dropped to re-apply cleanly.
- [x] **F3** — `TRUNCATE myth_participants, variant_claims, relationships, myths, entities CASCADE;`
      (`narrative_chunks` has **no** entity FK → deliberately left intact; embeddings preserved).
- [x] **F4** — `DELETE FROM flyway_schema_history WHERE version IN ('10','11','12','13','14','15','16');`
      — **must include V15 and V16.** Flyway won't re-apply a migration below the current max applied
      version, so leaving V16 in history makes it silently skip V10–V14; V15/V16 are COMMENT-only and
      idempotent, so re-applying is harmless. (Extend the list as new V-numbers land.)
- [x] **F5** — restart the app → Flyway re-applies V10–V16 (+ anything newer) in order; the
      `afterMigrate` callback re-grants `zeus_app`. Echo a "reseed complete — embeddings preserved"
      confirmation and a row-count sanity print (`entities`, `relationships`, `variant_claims`,
      `narrative_chunks`).
- [x] **F6** — **Shared-environment guard (the Flyway checksum trap, §8):** refuse to run (loud abort)
      if a shared/demo DB is detected — regenerating an *applied* V10–V12 breaks `flyway validate`
      everywhere. Gate on an explicit `ALLOW_RESEED=1` env or a `--local-only` flag + a printed
      warning; document the rule in the script header **and** cross-reference it in the (P3) audit README.
- [x] **F7** — a dry-run/`--check` mode that prints the SQL it *would* run without executing, so the
      first use is auditable.

---

## Track G — Cycle-detection check (§3.4 Rung 0; Python → becomes audit A3; independent — start now)

**On the critical path for Q9/Q12.** Author it **now in P2**; §4.1 makes it audit check **A3**, run
every batch thereafter. A cycle in `parent_of` — self-loop, 2-cycle (`A parent_of B` **and** `B
parent_of A`), or **longer** — is a near-certain reversed-direction edge, since a genealogy is a DAG.

- [x] **G1** — create the `ingestion/audit/` package (`__init__.py`) — the seed of P3's `python -m
      audit`. Add `ingestion/audit/cycle_check.py` with a **pure** core: `find_cycles(edges:
      list[Edge]) -> list[Cycle]` over a directed graph (Tarjan SCC or DFS back-edge), where each
      `Cycle` lists its **edges + `source_id` + `passage_ref`** per hop (so a reviewer can reverse/drop
      the offender). Filter to `relation == "parent_of"` by default; accept a relation-set param so
      P3 can widen it to all transitive relations.
- [x] **G2** — two readers over the **same** pure core (read-only, no mutation): (a)
      `load_from_candidates(path)` over `relationships_candidates_cleaned.json` (the editable source of
      truth — this is where fixes land); (b) `load_from_db(dsn)` over the live `relationships` table
      as `zeus_app` (read-only, statement timeout) to confirm the *seeded* graph matches. Both map to
      the same `Edge(from_name, to_name, relation, source_id, passage_ref)`.
- [x] **G3** — thin CLI `python -m audit.cycle_check [--candidates PATH | --db] [--relation parent_of]`
      printing a human report (each cycle: the edge chain + sources, flagged self-loop/2-cycle first as
      "near-certain reversed edge") **and** a machine-readable `findings.json`. Exit non-zero if any
      cycle is found (so the P3 fix loop can gate on it). **No mutation** — it *reports*, the human
      edits candidate JSON.
- [x] **G4** — **TDD** `ingestion/audit/tests/test_cycle_check.py` (pytest via `ingestion/.venv`):
      clean DAG → `[]`; self-loop; 2-cycle; a 3+-node cycle; a graph with one cycle + one clean
      component (only the cycle reported); each reported cycle carries the right edges + sources;
      relation filter excludes non-`parent_of` edges. **Pure over fixture graphs — no DB, no network.**
- [x] **G5** — README stub `ingestion/audit/README.md`: what A3 is, the DAG invariant, the
      candidate-JSON-layer fix rule, and the Flyway-checksum-trap cross-reference (shared with Track F).

---

## Track H — Docs / decisions (§3.5 + protocol; no code — do anytime)

- [ ] **H1** — record the **`query_history` skip** decision (§3.5) in `docs/DEVIATIONS.md`: not built
      for the PoC because (a) the eval runner persists full responses incl. `DebugInfo`, (b) `zeus_app`
      is read-only by guardrail (a write would need a grant change), (c) no organic traffic yet;
      revisit in P5 if real web usage appears. Cross-link from the P5 TODO line.
- [ ] **H2** — log **DEV-064** (debug surface + `DebugCapture` ThreadLocal — the plan's chosen shape
      over a `@Scope("request")` proxy, with the LangChain4j-retriever-boundary rationale) and add the
      `[DEVIATED - see DEVIATIONS.md #DEV-064]` banner where `IMPLEMENTATION_PLAN.md` describes the
      response DTO / QueryService, plus the `IMPLEMENTATION_PLAN_PHASE2.md §3.2` note.
- [ ] **H3** — log **DEV-065** (`reseed-local.sh`) and **DEV-066** (cycle-detection check authored in
      P2, located at `ingestion/audit/cycle_check.py`, becomes A3 in P3). Any reversed-edge data fix
      from Track I → its own **DEV-067+** (edge, both directions' sources, the tie-break rule applied).
- [ ] **H4** — mirror the completed items back into `TODO2.md` Stage P2 checkboxes and this file; keep
      `IMPLEMENTATION_PLAN_PHASE2.md` **unedited** (authoritative plan — deviations recorded separately).

---

## Track I — Integration gate: reseed → cycle-check → data fix → eval → compare (SERIAL)

Needs A–H merged + a running, seeded server. **This is the only place Q9/Q12 fixes are validated, and
the conditional rungs are the only place Q9/Q12 *code* may ship.** Every rung is gated on the previous
rung's **3-run** eval — never a single run (`§8` flakiness contract).

- [ ] **I1** — stack up (`scripts/run-local.sh`), confirm seeded (6 sources **and** non-empty
      `narrative_chunks` — P1 H1 caught a half-seeded DB; run `ingestion/main.py` if chunks are empty).
      Smoke-test the debug surface live: `POST /api/v1/query {"question":"Which Olympians are children
      of Cronus?","debug":true}` → confirm a populated `DebugInfo` (probe, sqlRows, chunk refs as
      applicable); and the same question without `debug` → **no** `debug` key.
- [ ] **I2** — **Rung 0 diagnose (always):** run `python -m audit.cycle_check --db` (seeded graph)
      **and** `--candidates` (source of truth) **before touching any SQL or prompt**. Record every
      `parent_of` cycle with its edges + sources.
- [ ] **I3** — **Rung 0 fix (always, if cycles found):** correct the offending edges at the
      **candidate-JSON layer** (`relationships_candidates_cleaned.json`) — reverse or drop, using
      `source_id` / `canonical_edge.py` spine priority as the tie-breaker. If a cycle traces to a
      *split/duplicated* entity (the Io/DEV-042 class), note it for P3 (don't merge entities here) but
      fix the direction. Then `python -m seedgen --strict` → `scripts/reseed-local.sh` → re-run
      `cycle_check --db` until **clean**.
- [ ] **I4** — **Re-measure:** `python -m runner --runs 3 --label p2 --debug` →
      `python -m runner.compare <…de6de91__baseline> <…p2>`. **If Q9/Q12 now answer over a clean DAG
      (no `serviceError`, content point earned) and zero stable regressions → STOP. Ship no Q9/Q12
      code.** Q13 must still show 3/3 (confirm, don't touch). Commit candidates + the corrected V11 +
      the results dir together.
- [ ] **I5 — Rung 1 (ONLY IF I4 still shows Q9/Q12 stable-fail/flaky over the clean DAG):** add a
      **LOUD** bounded `WITH RECURSIVE` few-shot to `TextToSqlAgent.generateSql` (depth cap +
      `visited`-id array). It must leave a breadcrumb — `DebugInfo.sqlRows` shows whether the
      visited-array truncation fired (a revisited id = a live data cycle Rung 0 missed → back to G/A3),
      **never a silent guard.** TDD the prompt-shape/regeneration path with a mocked agent. Re-run I4's
      eval+compare; gate Rung 2 on this result.
- [ ] **I6 — Rung 2 (ONLY IF Rung 1's 3-run eval still shows Q9/Q12 stable-fail/flaky AND the debug
      surface shows a malformed-CTE / generation-validation exception, not a live data cycle):** `runSqlWithErrorRecovery(question)` wrapping generate+execute, re-asking via
      a new `TextToSqlAgent.regenerateAfterSqlError(schema, question, priorSql, dbError)` (same
      `routingModel`, temp 0.0) through the shared `executeValidated`; on 2nd failure **rethrow the
      ORIGINAL error.** Place it in **both `SqlQueryHandler` and `MixedQueryHandler`** (Q12 fails in
      the MIXED SQL step); give DEV-057's attribution retry its **own** `try/catch` ("never worse").
      TDD both handlers' retry path with mocked `@AiService`. Re-run eval+compare.
- [ ] **I7 — Rung 3 (ONLY IF clean data + Rungs 1–2 still leave Q9/Q12 stable-fail):** a bounded
      recursive ancestry **view/function** in a fresh **V-migration**, advertised to the model via
      `SchemaIntrospector` (the V15/V16 schema-channel precedent). On evidence only. Re-run eval+compare.
- [ ] **I8** — **Final gate:** `compare.py` shows Q9/Q12 fixed + Q13 still passing + **zero stable
      PASS→FAIL regressions**; per-category floors hold (or are unchanged from baseline — P2 is not a
      data-quality stage, DATA floor may still BREACH pending P3, which is acceptable *as long as it
      did not regress*). `./gradlew :core-api:test` green. Results dir committed with the sha of the
      code that produced it (ADR-018 §Decision 5).

---

## Definition-of-done checklist (mirror of TODO2.md Stage P2)

- [ ] `logging.level.com.blamezeus.coreapi: DEBUG` present (yml or `debug` profile); DEBUG lines
      confirmed live.
- [ ] `QueryRequest.debug` + `QueryResponse.debug: DebugInfo?` (`@JsonInclude(NON_NULL)`) via a
      **ThreadLocal singleton `DebugCapture`** (plain bean, not `@Scope("request")`), appended to by
      `SqlQueryHandler`, `MixedQueryHandler`, `NarrativeChunkContentRetriever`, and `QueryService`;
      attached at one `finalize()` funnel, reset in `finally`. **Contract byte-identical when
      `debug=false`.**
- [ ] `scripts/reseed-local.sh` — `DROP TABLE entity_aliases` + `TRUNCATE` V10–V13 tables `CASCADE` +
      `DELETE FROM flyway_schema_history WHERE version IN ('10'…'16')` (incl. V15/V16) → restart;
      **never** `down -v`; shared-env guard (checksum trap). Embeddings preserved (verified by
      `narrative_chunks` row count surviving a reseed).
- [ ] Q13 **verified passing at baseline** — not re-implemented (DEV-056/057 cover it).
- [ ] Q9/Q12: **Rung 0 (cycle detection + data fix) always done**; the graph reported clean (or
      reversed edges listed + fixed at candidate-JSON layer); Rungs 1→3 shipped **only** on the prior
      rung's 3-run eval evidence. Q9/Q12 no longer `serviceError`; content point earned over a genuine
      DAG.
- [ ] `query_history` **skip** decision recorded (eval artifacts + `DebugInfo` cover the forensic need).
- [ ] Cycle-detection check authored (`ingestion/audit/cycle_check.py`, pure over a fixture graph,
      TDD) → becomes audit **A3** in P3.
- [ ] `./gradlew :core-api:test` green (DebugCapture, finalize funnel, producer captures, and any
      shipped retry path unit-tested; `@AiService` mocked, TDD). `pytest ingestion/audit/tests/` green.
- [ ] `python -m runner --runs 3 --label p2 --debug` + `compare.py <baseline> <p2>` → Q9/Q12/Q13
      fixes visible, **zero stable regressions**; results dir committed; `raw_responses.json` now
      carries probe output, retrieved chunk refs, SQL rows, first-attempt SQL.
- [ ] DEV entries logged (DEV-064 debug surface, DEV-065 reseed script, DEV-066 cycle check, DEV-067+
      per data fix / shipped rung); banners added; `IMPLEMENTATION_PLAN_PHASE2.md` left unedited.
```
