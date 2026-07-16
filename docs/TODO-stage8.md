# Stage 8 — Mixed Pipeline (SQL filter → inject → RAG narration): Detailed Checklist

**Done when:** the two MIXED gold questions (Q11 "Which heroes had a divine parent and died at
Troy?", Q12 "What is the divine lineage connecting Achilles to Zeus?") route `MIXED` and return a
narrative answer that is **demonstrably grounded in SQL-filtered rows** (the injected entities /
lineage appear in the prose) **with RAG-derived citations**; `MixedQueryHandlerTest` passes with all
`@AiService` interfaces mocked (no live LLM); `QueryService` dispatches `RouteDecision.MIXED` to the
real handler (the Stage 5 placeholder is gone) and its existing inner try-catch still converts a
handler failure to a `serviceError` response; conflict enrichment continues to run **route-independently**
on top of the MIXED answer (unchanged from Stage 7 — nothing new wired, just verified it still fires);
and the full `:core-api:test` suite is green.

> **Design is the plan's, not the plan's dead branches.** `MixedQueryHandler` is
> `TextToSqlAgent.generateSql()` → validate → execute → **inject the result rows as context into an
> augmented question string** → `ragAgent.answer(augmented)` (IMPLEMENTATION_PLAN §793, TODO.md Stage 8).
> Two things the older plan text still mentions are **NOT** part of this design and must not be built:
> - **No `EntityExtractor` / `ConflictProbe` call inside `MixedQueryHandler`.** IMPLEMENTATION_PLAN
>   §717 and the forward-looking comments in `ConflictProbe.kt` / CLAUDE.md say the MIXED handler
>   *"can"* inject `ConflictProbe` and read `.subject`. The SQL-filter design does not need entity
>   resolution — the SQL query *is* the filter. Confirm this in Track A2 and do not add the dependency.
> - **No `CONFLICT` route / `ConflictQueryHandler`** (killed in Stage 7 per ADR-007 / DEV-014).
>   Conflict surfacing for MIXED answers happens exactly like every other route: via
>   `QueryService.enrich()`, already built and route-independent. Stage 8 adds **zero** conflict code.

> **Prerequisite: Stages 5, 6, 7 complete.** This handler reuses the SQL path built in Stage 5
> (`TextToSqlAgent`, `SchemaIntrospector`, `SqlSafetyValidator`, `JdbcTemplate`) and the RAG path built
> in Stage 6 (`RagAgent`, wired via `retrievalAugmentor`). `QueryService.enrich()` (Stage 7) already
> wraps whatever `handle()` returns for **any** route, so a MIXED answer is conflict-enriched the moment
> the placeholder is replaced with a real answer — no enrichment wiring changes.

Before starting, re-read `DEVIATIONS.md`. Relevant carry-overs:
- **DEV-004** — LangChain4j is `1.0.0-beta5`. No new `@AiService` interface is introduced in this
  stage; `MixedQueryHandler` is a plain `@Component` that *consumes* the already-proven
  `TextToSqlAgent` and `RagAgent` beans. `RagAgent.answer(question: String)` takes the single
  augmented string — confirm the interface is byte-unchanged from Stage 6 before building on it.
- **DEV-046 / DEV-015** — two `ChatModel` beans (`routingModel` 0.0, `synthesisModel` 0.3). Nothing
  new to wire here, but be aware `TextToSqlAgent` runs on the 0.0 model and `RagAgent` on the 0.3
  model — `MixedQueryHandler` inherits both correctly just by injecting the existing beans.
- **DEV-026 / ADR-005 §Decision.3** — the SQL-empty → RAG fallback for the *pure* SQL route lives in
  `QueryService.handleSql()`, keyed on `SqlQueryHandler.EMPTY_RESULT_ANSWER`. Track A3 must decide the
  **analogous** behavior for a MIXED query whose SQL filter returns zero rows — it is a *different*
  case (MIXED already ends in a RAG call), so do not blindly reuse the constant.
- **DEV-021 / DEV-051** — surfaced `conflicts[]` cite via the deterministic `ConflictSynthesizer`;
  irrelevant to the MIXED *answer/citations* (those come from `RagResponse`), but relevant to Track E's
  verification that a MIXED question which *also* has stored conflicts surfaces them correctly.
- **DEV-053** — `ConflictProbe` claim-type extraction is narrative-phrasing-sensitive. Track D must
  author Q11/Q12 so the CONFLICT-independent MIXED scoring doesn't accidentally depend on conflict
  enrichment firing (Q11/Q12 are MIXED, not CONFLICT — they should score on `citations[]` + keywords).
- **DEV-008** — Testcontainers pinned `1.21.4`; reuse `AbstractContainerTest` for any DB-backed test.
  `MixedQueryHandlerTest` should be a **pure mock** test (mock `TextToSqlAgent`/`RagAgent`/`JdbcTemplate`),
  matching `SqlQueryHandlerTest`'s no-container pattern — no Testcontainers needed for the handler unit test.

**Deviation protocol:** if Track A1 extracts shared SQL-gen/exec logic out of `SqlQueryHandler` (a
refactor of already-shipped Stage 5 code), that is a deviation — log it as the next `DEV-NNN`
(latest is **DEV-053**), mark the touched `SqlQueryHandler` line, and add the §9 stage-note pointer.
If A1 chooses to duplicate instead, no DEV entry is needed.

## Parallelization Guide

```
Track 0 (read-only confirm) ─┐
                             ├─→ Track B (MixedQueryHandler, TDD) ─→ Track C (QueryService wiring) ─┐
Track A (3 design decisions) ┘                                                                      ├─→ Track E (verify)
Track D (author MIXED gold Q11/Q12) ───────────────────────────────────────────────────────────────┘
```

- **Track 0 + Track A + Track D start immediately, in parallel** — 0 is read-only, A is decisions on
  paper, D is pure JSON authoring against the seeded DB. None depend on each other.
- **Track B depends on A** (its 3 decisions fix the handler's shape) **+ Track 0** (interface confirms).
- **Track C depends on B** — it swaps the placeholder for the real bean.
- **Track E is last** — it needs B + C (live handler) and D (gold questions to run).

---

## Track 0 — Pre-flight confirms (read-only, no production code)

_Purpose:_ confirm the three interfaces `MixedQueryHandler` composes are byte-unchanged and behave as
Stage 8 assumes. Write findings to a scratch note, not the repo; log any contradiction as a DEV entry.

- [x] **0.1** Confirmed via `ai/RagAgent.kt` — `answer(question: String): RagResponse` is unchanged
      since Stage 6: single unannotated `String` param (no `@UserMessage` needed, same as
      `QueryRouter.classify`), `@AiService(wiringMode = EXPLICIT, chatModel = "synthesisModel",
      retrievalAugmentor = "retrievalAugmentor")`, returns `RagResponse{answer, citations}`
      (`domain/dto/RagResponse.kt`). A longer augmented string is just a longer `String` — no
      interface change required.
- [x] **0.2** Confirmed via `handler/SqlQueryHandler.kt:22-26` — the exact four calls are
      `textToSqlAgent.generateSql(schemaIntrospector.get(), question)` (`ai/TextToSqlAgent.kt:39`,
      `@UserMessage("Question: {{question}}")` over the `routingModel`), `schemaIntrospector.get():
      String` (`config/SchemaIntrospector.kt:21`, cached schema-prompt string), `validator.validate(sql)`
      (`safety/SqlSafetyValidator.kt:13`, throws on rejection), `jdbcTemplate.queryForList(sql):
      List<Map<String, Any?>>`. `stripMarkdownFence` (`SqlQueryHandler.kt:53-63`) is `private` and IS
      needed by MIXED too — same `routingModel`, same fencing risk, no fence-stripping elsewhere → feeds
      Track A1 (duplicate vs. extract).
- [x] **0.3** Confirmed via `config/RagConfig.kt` + `ai/NarrativeChunkContentRetriever.kt` — no separate
      channel exists. `DefaultRetrievalAugmentor` builds its `Query` from the single user-message string
      AiServices passes in (the whole augmented string), `NarrativeChunkContentRetriever.retrieve()`
      embeds `query.text()` directly (`NarrativeChunkContentRetriever.kt:48`) for the vector search, and
      `DefaultContentInjector` (`metadataKeysToInclude` = author/work/passage_ref/stance) appends the
      retrieved passages onto that same original user message rather than replacing it — so the injected
      SQL rows reach both the retrieval embedding and the final LLM prompt. No finding to escalate to
      Track A.

---

## Track A — Design decisions (on paper; blocks B)

_Small but fixes the handler's entire shape. Do before writing Track B tests._

- [x] **A1 — Share vs duplicate the SQL gen/exec sequence.** Decided **(a) duplicate**: the
      `generateSql → stripMarkdownFence → validate → queryForList` sequence plus a private
      `stripMarkdownFence` copy is duplicated into `MixedQueryHandler`, matching `SqlQueryHandler.kt:22-26,53-63`
      byte-for-byte in shape. Zero blast radius on shipped Stage 5 code, no `SqlQueryHandlerTest`
      re-run needed, no DEV-NNN entry. The shared surface (~10 lines) doesn't justify a shared
      `@Component` for a PoC.
- [x] **A2 — Confirm NO `ConflictProbe`/entity extraction inside the handler.** Decided: not used.
      `MixedQueryHandler` composes only `TextToSqlAgent`, `SchemaIntrospector`, `SqlSafetyValidator`,
      `JdbcTemplate`, `RagAgent` — the generated SQL query *is* the filter, so no entity resolution step
      is needed. IMPLEMENTATION_PLAN §717's "can inject `ConflictProbe`" and the forward-looking comment
      in `ConflictProbe.kt` describe a path this stage does not take; conflict surfacing stays entirely
      in `QueryService.enrich()`, route-independent, per ADR-007.
- [x] **A3 — Empty-SQL-filter behavior.** Decided **(a)**: inject an explicit "no matching rows found
      in structured data" context line into the augmented string and still call `ragAgent.answer` —
      `routeDecision` stays `MIXED`, no second dispatch, RAG narrates from the corpus with the
      empty-filter noted. Mirrors the spirit of `SqlQueryHandler`'s `EMPTY_RESULT_ANSWER` handling
      (DEV-026) without reusing that SQL-route-specific constant, since MIXED never returns early —
      it always ends in a RAG call.
- [x] **A4 — Augmentation string format.** Decided template (row-flattening reuses
      `SqlQueryHandler.formatAnswer`'s idea — `row.values.joinToString(", ")` per row — kept MIXED-local
      per A1):
      ```
      Relevant structured facts:
      - <row1 value1, row1 value2, ...>
      - <row2 value1, row2 value2, ...>

      Question: <original question>
      ```
      Empty-filter case (A3) substitutes a single line, `- No matching rows found in structured data.`,
      for the row list. Track B asserts the SQL row values appear verbatim in the string passed to the
      mocked `ragAgent.answer`.
- [x] **A5 — Response shape.** Confirmed: `answer` = `RagResponse.answer`, `routeDecision =
      RouteDecision.MIXED`, `citations` = `RagResponse.citations` (RAG-derived, `Citation` DTO
      unchanged), `conflicts = emptyList()` (enrichment adds them later in `QueryService`, never the
      handler — matches `QueryResponse` DTO's existing shape, no DTO changes needed), `sqlGenerated` =
      the generated SQL string (post-fence-strip), even in the A3 empty-filter case (so the web UI's
      collapsible SQL block works for MIXED too, matching `SqlQueryHandler`).

---

## Track B — `MixedQueryHandler` (TDD)

_Directory:_ `.../handler/` + `.../test/.../handler/`. _Depends on:_ Track A + Track 0. Pure mock test
(no Testcontainers), matching `SqlQueryHandlerTest`.

- [x] **B1** `MixedQueryHandlerTest.kt` written FIRST (`handler/MixedQueryHandlerTest.kt`). Mocks
      `TextToSqlAgent`, `SchemaIntrospector`, `SqlSafetyValidator`, `JdbcTemplate`, `RagAgent` via MockK,
      matching `SqlQueryHandlerTest`'s no-container pattern. Cases:
  - [x] **(a)** happy path: `injects SQL row values and the original question into the augmented string
        passed to RagAgent` — asserts the string passed to `ragAgent.answer(...)` contains the SQL row
        values (Achilles/Sarpedon) and the original question.
  - [x] **(b)** `validates and executes the generated SQL before calling RagAgent` — `verifyOrder`:
        `validator.validate` → `jdbcTemplate.queryForList` → `ragAgent.answer`.
  - [x] **(c)** `maps the RagResponse into a MIXED QueryResponse with the generated SQL and no
        conflicts` — `answer`/`citations` from the stubbed `RagResponse`, `routeDecision == MIXED`,
        `sqlGenerated` == the generated SQL, `conflicts` empty, `serviceError` false.
  - [x] **(d)** `an empty SQL filter injects a no-matching-rows note and still calls RagAgent exactly
        once` — rows = `emptyList()`, asserts the A3(a) note is injected and `ragAgent.answer` called
        exactly once.
  - [x] **(e)** `a markdown-fenced SQL response is stripped before validation and execution` — mirrors
        `SqlQueryHandlerTest`'s fence case (A1 chose duplicate, so this case lives here too).
  - [x] **(f)** `a SqlSafetyValidator rejection propagates and RagAgent is never called` — exception
        not swallowed, `jdbcTemplate.queryForList` and `ragAgent.answer` both verified never called.
- [x] **B2** `handler/MixedQueryHandler.kt` — `@Component`, constructor-injects the five deps above.
      Implements A1 (duplicated `stripMarkdownFence`)/A3(a)/A4 (labeled-block template)/A5 (response
      shape). Matches `SqlQueryHandler`'s logging style (`LoggerFactory`, `log.debug` the generated
      SQL, `log.info` the empty-filter branch). No LLM logic beyond the two interface calls.
- [x] **B3** `:core-api:test --tests '*MixedQueryHandlerTest'` → green (6/6). Full `:core-api:test` →
      124 tests, 0 failures, 0 errors — no regression (A1 chose duplicate, so `SqlQueryHandlerTest` is
      untouched).

---

## Track C — `QueryService` wiring

_Directory:_ `.../service/`. _Depends on:_ Track B (needs the real bean to inject).

- [x] **C1** Constructor-injected `MixedQueryHandler` into `QueryService`. Replaced
      `RouteDecision.MIXED -> placeholderResponse(route)` with
      `RouteDecision.MIXED -> mixedQueryHandler.handle(question)`. Deleted the now-dead
      `placeholderResponse` function and the `TODO(Stage 8)` comment — confirmed MIXED was its only
      caller (`grep -rn placeholderResponse`), SQL/RAG never used it.
- [x] **C2** Class-level KDoc rewritten: drops "The MIXED handler lands in Stage 8 — until then that
      route gets a clearly-marked placeholder response," now reads "the only class that knows about
      all three handlers (SqlQueryHandler, RagQueryHandler, MixedQueryHandler)." `enrich()` untouched —
      already covers all three routes.
- [x] **C3** `QueryServiceTest.kt`: replaced the placeholder test with:
  - [x] `a MIXED decision dispatches to MixedQueryHandler and nowhere else` — `queryRouter.classify` →
        `MIXED`, mocked `mixedQueryHandler.handle` returns a real `QueryResponse`, asserted it's
        returned byte-identical (relying on the existing `init{}` default `ProbeResult("Unknown",
        "none")` so enrichment no-ops) and `sqlQueryHandler`/`ragQueryHandler` are never called.
  - [x] `when the MIXED handler throws, the response has serviceError true and a non-empty answer` —
        proves the pre-existing inner catch covers the new route.
  - [x] `a MIXED-routed answer also gets enriched with conflicts, proving enrichment is genuinely
        route-independent` — mocked `conflictProbe`/`conflictLookup`/`conflictSynthesizer` return a
        non-empty conflict set, asserted `conflicts[]` populates on the MIXED answer.
- [x] **C4** `:core-api:test` → full suite green: 126 tests, 0 failures, 0 errors (was 124; net +2 from
      replacing 1 placeholder test with 3 new MIXED-dispatch tests).

---

## Track D — Author the MIXED gold questions (Q11, Q12)

_File:_ `evaluation/gold-questions.json` (currently 14 questions; MIXED Q11/Q12 are absent). Pure JSON
authoring against the live seed — **fully parallel with Tracks 0/A/B/C**. No `EvaluationRunner` is
built here (that's Stage 10) — Track E validates by hand / `curl`.

- [x] **D1** Added **Q11** — `"Which heroes had a divine parent and died at Troy?"`, `category: "MIXED"`,
      `expected_route: "MIXED"`, `required_keywords: ["Troy", "divine"]`, `required_authors: ["Homer"]`
      (verified against the live DB: Sarpedon, `child_of` Zeus, is killed by Patroclus across several
      richly-narrated `homer-iliad` chunks, e.g. passage_ref `16.419-16.501` — a real answerable
      divine-parent-died-at-Troy case in the seeded corpus).
- [x] **D2** Added **Q12** — `"What is the divine lineage connecting Achilles to Zeus?"`,
      `category: "MIXED"`, `expected_route: "MIXED"`, `required_keywords: ["Peleus", "Thetis", "Zeus"]`,
      `required_authors: ["Apollodorus"]` (verified: `apollodorus-bibliotheca` passages 3.13.5/3.13.6
      narrate Peleus + Thetis directly).
- [x] **D3** Verified against the live DB (`docker exec blame-zeus-postgres-1 psql`):
      `relationships` has both `Achilles son_of/child_of Peleus` and `Peleus father_of Achilles`, plus
      **two independent Zeus paths** — `Zeus father_of Aeacus father_of Peleus father_of Achilles` and
      `Zeus parent_of Thetis mother_of Achilles` — so Q12's lineage filter is answerable multiple ways.
      For Q11, `Sarpedon child_of Zeus` is in `relationships` and his death at Patroclus's hands is
      narrated across `homer-iliad` passage_refs `16.419-16.501`; no `myths`/`myth_participants` row
      names Troy explicitly (only "The Judgment of Paris" mentions "near Troy"), but MIXED's design
      doesn't require that — the SQL filter finds divine-parent heroes, RAG supplies "died at Troy"
      from Iliad narrative. Both questions answerable from the Phase 1 seed as authored; no phrasing
      change needed.
- [x] **D4** Confirmed via `variant_claims` query: `Zeus`/`Peleus`/`Thetis` have **zero** stored
      conflict rows, so Q12 can't trigger stray `conflicts[]`. `Achilles` does have 22 stored `death`
      claims (feeds Q15's CONFLICT question) and Q11's phrasing ("died at Troy") could plausibly make
      `ConflictProbe` extract `subject=Achilles, claimType=death` (DEV-053) — but structurally harmless:
      `QueryService.enrich()` only ever writes `conflicts[]`, never touches `answer`/`citations`, so
      MIXED scoring (which reads only those two) can't be polluted either way.
- [x] **D5** Re-validated: `python3 -c "import json; json.load(open('evaluation/gold-questions.json'))"`
      parses cleanly, count is now 16 (was 14 + Q11 + Q12), ids
      `[1..10, 11, 12, 13, 14, 15, 18]` — Q11/Q12 slot between DATA Q10 and CONFLICT Q13 as planned.

---

## Track E — Live verification (last)

_Depends on:_ B + C + D. No new automated tests here — this is the end-to-end confirm against the real
API + corpus + Postgres, mirroring Stage 7's Track H.

- [ ] **E1** Full `:core-api:test` green (all handler + service tests, including the new
      `MixedQueryHandlerTest` and the reworked `QueryServiceTest` MIXED cases). Record the count.
- [ ] **E2** Boot with real `.env` against live Postgres (Flyway at head, full 6-source corpus).
      `POST /api/v1/query {"question":"Which heroes had a divine parent and died at Troy?"}` →
      assert `routeDecision: "MIXED"`, an answer that names actual SQL-filtered heroes **and** reads as
      narrative prose (not a raw column dump), `citations[]` with a real author/work/passageRef.
- [ ] **E3** `POST {"question":"What is the divine lineage connecting Achilles to Zeus?"}` → assert
      `routeDecision: "MIXED"`, the answer traces Peleus/Thetis/Zeus, `sqlGenerated` is a real lineage
      query (confirm the SQL rows genuinely shaped the prose — check the debug log for the augmented
      string, per the A4 template).
- [ ] **E4** Confirm the injected-SQL invariant live: enable `log.debug` and verify the string handed
      to `ragAgent.answer` for E2/E3 actually contains the executed rows (the whole point of "MIXED",
      distinguishing it from a plain RAG answer to the same question).
- [ ] **E5** Empty-filter live check: a MIXED-routed question whose SQL filter returns zero rows behaves
      per A3's decision (no exception, still returns a MIXED answer). Pick or craft one; record the result.
- [ ] **E6** Route-independent enrichment still fires: pick a MIXED-routed question that *also* has a
      stored conflict for its subject and confirm `conflicts[]` populates on top of the MIXED answer —
      proves Stage 7's enrichment survived the Stage 8 wiring (belt-and-suspenders vs C3's mocked test).
- [ ] **E7** Handler-failure degradation: confirm (via `QueryServiceTest` C3, already mocked — a live
      forced-failure isn't safely reproducible) that a MIXED handler exception yields a `serviceError`
      response, not an unhandled 500.
- [ ] **E8** Bookkeeping: if A1 chose the extract option, log the `DEV-NNN`, mark the touched
      `SqlQueryHandler` line, and add the IMPLEMENTATION_PLAN §9 stage-note pointer. Flip the TODO.md
      Stage 8 boxes. Record the final "Stage 8 complete" line here (tests green + live-verified).

---

**Stage 8 completion criteria recap:** `MixedQueryHandler` shipped (SQL filter → inject → RAG),
`QueryService` dispatches MIXED to it (placeholder gone), Q11/Q12 authored and live-answerable,
conflict enrichment confirmed still route-independent, full suite green, end-to-end live-verified.
