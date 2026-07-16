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

- [ ] **0.1** Confirm `RagAgent.answer(question: String): RagResponse` is unchanged since Stage 6 (single
      unannotated `String` param, `retrievalAugmentor`-wired, returns `{answer, citations}`). The
      augmented question is just a longer `String` — no interface change, no `@UserMessage` needed. This
      is the one call the whole handler hinges on.
- [ ] **0.2** Confirm the SQL half is reusable as-is: `TextToSqlAgent.generateSql(schema, question)`,
      `SchemaIntrospector.get()`, `SqlSafetyValidator.validate(sql)`, `JdbcTemplate.queryForList(sql)`
      — the exact four calls `SqlQueryHandler.handle()` already makes (`SqlQueryHandler.kt:22-26`).
      Note whether `stripMarkdownFence` (currently `private` in `SqlQueryHandler`) is needed by MIXED
      too — it is (same model, same fencing risk) → feeds Track A1's share-vs-duplicate decision.
- [ ] **0.3** Confirm the retrieval augmentor injects `RagAgent`'s context from the vector store on the
      **whole** augmented string (i.e. the injected SQL rows become part of the query embedding /
      prompt, not a separate channel). Read `config/RagConfig.kt`'s `retrievalAugmentor` bean to be
      sure the augmented text reaches the model — this is what makes "inject SQL results as context"
      actually work through the existing wiring. If the augmentor only embeds the question for
      retrieval and the SQL rows never reach the prompt, that's a finding → escalate to Track A.

---

## Track A — Design decisions (on paper; blocks B)

_Small but fixes the handler's entire shape. Do before writing Track B tests._

- [ ] **A1 — Share vs duplicate the SQL gen/exec sequence.** `MixedQueryHandler` needs the identical
      `generateSql → stripMarkdownFence → validate → queryForList` sequence `SqlQueryHandler` already
      has. Decide:
      - **(a) Duplicate** the ~5 lines + `stripMarkdownFence` into `MixedQueryHandler` (zero blast
        radius on shipped Stage 5 code; no DEV entry).
      - **(b) Extract** a shared `@Component` (e.g. `SqlExecutor.generateAndRun(question): List<Map>`)
        that both handlers call (DRY, but refactors shipped code → **requires a DEV-NNN entry** and
        re-running `SqlQueryHandlerTest`).
      Recommendation: **(a) duplicate** for a PoC — the shared surface is tiny and (b)'s refactor risk
      + deviation overhead outweighs the DRY win. Record the choice and rationale here.
- [ ] **A2 — Confirm NO `ConflictProbe`/entity extraction inside the handler.** Per the header note,
      the SQL query is the filter; entity resolution is not needed. Explicitly decide "not used" and
      record it, so a future reader doesn't re-add it from the stale IMPLEMENTATION_PLAN §717 /
      `ConflictProbe.kt` comment. (No code — a decision to *not* build something.)
- [ ] **A3 — Empty-SQL-filter behavior.** Decide what a MIXED query does when the SQL filter returns
      **zero rows**. Options:
      - **(a) Inject an explicit "no matching rows" context line** and still call `ragAgent.answer` —
        RAG narrates from the corpus with the empty-filter noted. Simple, always returns a MIXED answer.
      - **(b) Fall back to plain RAG** on the bare question (mirrors `QueryService.handleSql`'s
        DEV-026 empty→RAG, but here it's internal to the handler).
      Recommendation: **(a)** — MIXED already ends in a RAG call, so an empty filter is just a
      degenerate augmentation, not a reason to change routes; keeps `routeDecision = MIXED` honest and
      avoids a second dispatch. Record the choice; it fixes a Track B test case.
- [ ] **A4 — Augmentation string format.** Decide the exact template that turns
      `List<Map<String, Any?>>` rows into the context prepended/appended to the question. Keep it a
      readable, deterministic serialization (e.g. a labeled block: `"Relevant structured facts:\n- <row>\n...\n\nQuestion: <original>"`).
      Reuse `SqlQueryHandler.formatAnswer`'s row-flattening idea but keep it MIXED-local (per A1).
      Record the chosen template — Track B asserts the SQL rows appear verbatim in the string passed
      to the mocked `ragAgent.answer`.
- [ ] **A5 — Response shape.** Confirm the returned `QueryResponse` is: `answer` = `RagResponse.answer`,
      `routeDecision = RouteDecision.MIXED`, `citations` = `RagResponse.citations` (RAG-derived),
      `conflicts = emptyList()` (enrichment adds them later in `QueryService`, never the handler),
      `sqlGenerated` = the generated SQL string (so the web UI's collapsible SQL block works for MIXED
      too, matching `SqlQueryHandler`). Record; drives Track B assertions.

---

## Track B — `MixedQueryHandler` (TDD)

_Directory:_ `.../handler/` + `.../test/.../handler/`. _Depends on:_ Track A + Track 0. Pure mock test
(no Testcontainers), matching `SqlQueryHandlerTest`.

- [ ] **B1** `MixedQueryHandlerTest.kt` written FIRST. Mock `TextToSqlAgent`, `SchemaIntrospector`,
      `SqlSafetyValidator`, `JdbcTemplate`, `RagAgent`. Cases:
  - [ ] **(a)** happy path: given a stubbed SQL string + stubbed rows, assert the exact string passed
        to `ragAgent.answer(...)` **contains the SQL row values** (the A4 template) and the original
        question — this is the stage's headline invariant ("SQL results injected into the augmented
        question before the RAG call", TODO.md Stage 8 / IMPLEMENTATION_PLAN §1099).
  - [ ] **(b)** `verifyOrder`: `validator.validate(sql)` runs **before** `jdbcTemplate.queryForList(sql)`
        runs **before** `ragAgent.answer(augmented)` — the safety gate is never skipped (mirrors
        `SqlQueryHandlerTest`'s ordering test).
  - [ ] **(c)** response mapping: `answer`/`citations` come from the stubbed `RagResponse`;
        `routeDecision == MIXED`; `sqlGenerated == <the generated SQL>`; `conflicts` empty (per A5).
  - [ ] **(d)** empty-SQL-filter case per A3's decision (rows = `emptyList()` → asserts the A3(a)
        "no matching rows" context is injected and `ragAgent.answer` is still called exactly once).
  - [ ] **(e)** markdown-fenced SQL from the model is stripped before validation/execution (mirrors
        `SqlQueryHandlerTest`'s fence case — only if A1 chose duplicate; if A1 chose extract, this case
        lives in the shared component's test instead).
  - [ ] **(f)** a `SqlSafetyValidator` rejection (validate throws) propagates out of the handler (so
        `QueryService`'s inner catch turns it into `serviceError`) — assert the exception is not
        swallowed and `ragAgent.answer` is **never** called.
- [ ] **B2** `handler/MixedQueryHandler.kt` — `@Component`, constructor-injects the five deps above.
      Implements A1/A3/A4/A5. Match `SqlQueryHandler`'s logging style (`LoggerFactory`, `log.debug` the
      generated SQL, `log.info` the empty-filter branch). No LLM logic beyond the two interface calls.
- [ ] **B3** Run `:core-api:test --tests '*MixedQueryHandlerTest'` → green. Then full `:core-api:test`
      → confirm no regression (if A1 chose extract, `SqlQueryHandlerTest` must still pass against the
      refactored `SqlQueryHandler`).

---

## Track C — `QueryService` wiring

_Directory:_ `.../service/`. _Depends on:_ Track B (needs the real bean to inject).

- [ ] **C1** Constructor-inject `MixedQueryHandler` into `QueryService`. Replace
      `RouteDecision.MIXED -> placeholderResponse(route)` (`QueryService.kt:46`) with
      `RouteDecision.MIXED -> mixedQueryHandler.handle(question)`. Delete the now-dead
      `placeholderResponse` function **and** the `TODO(Stage 8)` comment (`QueryService.kt:45,102-108`)
      if MIXED was its only remaining caller (verify SQL/RAG don't use it — they don't).
- [ ] **C2** Update the class-level KDoc (`QueryService.kt:14-22`): drop "The MIXED handler lands in
      Stage 8 — until then that route gets a clearly-marked placeholder response." Now all three
      handlers are real; `enrich()` already covers all three routes unchanged.
- [ ] **C3** `QueryServiceTest.kt`: replace the placeholder test
      `` `a MIXED decision gets a Stage 5 placeholder response, not an exception` `` (line ~181) with:
  - [ ] a MIXED-dispatch test — `queryRouter.classify` → `MIXED`, mocked `mixedQueryHandler.handle`
        returns a real `QueryResponse`, assert it's returned (with default `ProbeResult("...", "none")`
        so enrichment no-ops, matching the existing `init{}` default) and the other two handlers are
        never called.
  - [ ] a MIXED-handler-failure test — `mixedQueryHandler.handle` throws → assert `serviceError == true`
        response with `routeDecision == MIXED` (proves the pre-existing inner catch covers the new route).
  - [ ] a MIXED-**with**-conflict test — mocked `conflictProbe`/`conflictLookup`/`conflictSynthesizer`
        return a non-empty conflict set → assert the MIXED answer comes back with `conflicts[]`
        populated, proving enrichment is genuinely route-independent (Stage 7's promise, now exercised
        on the MIXED path).
- [ ] **C4** `:core-api:test` → full suite green.

---

## Track D — Author the MIXED gold questions (Q11, Q12)

_File:_ `evaluation/gold-questions.json` (currently 14 questions; MIXED Q11/Q12 are absent). Pure JSON
authoring against the live seed — **fully parallel with Tracks 0/A/B/C**. No `EvaluationRunner` is
built here (that's Stage 10) — Track E validates by hand / `curl`.

- [ ] **D1** Add **Q11** — `"Which heroes had a divine parent and died at Troy?"`, `category: "MIXED"`,
      `expected_route: "MIXED"`, `required_keywords` (e.g. `["Troy", "divine"]` per IMPLEMENTATION_PLAN
      §998), `required_authors` (a source that actually narrates Trojan deaths, e.g. Homer — verify it's
      in the seeded corpus first). Content check scores on `answer` keywords + `citations[]` author
      (MIXED scoring path, IMPLEMENTATION_PLAN §1018-1019) — **not** on `conflicts[]`.
- [ ] **D2** Add **Q12** — `"What is the divine lineage connecting Achilles to Zeus?"`,
      `category: "MIXED"`, `expected_route: "MIXED"`, `required_keywords: ["Peleus", "Thetis", "Zeus"]`
      (IMPLEMENTATION_PLAN §999), `required_authors` from the seeded genealogy source (Apollodorus /
      Hesiod — verify). This one leans on the SQL lineage filter feeding the RAG narration.
- [ ] **D3** Verify against the live DB that the SQL filter for each is *answerable* — the entities /
      relationships needed (heroes with divine parents + Trojan-death participation for Q11; the
      Peleus→Achilles / Zeus→…→Peleus edges for Q12) actually exist in the seeded `entities`/
      `relationships`/`myth_participants` tables. If a question isn't answerable from the seed, adjust
      the phrasing/keywords rather than shipping an unscoreable gold question (note any change here).
- [ ] **D4** Confirm neither Q11 nor Q12 depends on conflict enrichment to score — they are MIXED, and
      a stray `conflicts[]` population (if the probe happens to fire) must not be *required* for the
      point. Sanity-check the `subject`/`claimType` the probe would extract isn't a stored conflict
      that pollutes the answer (DEV-053 phrasing-sensitivity awareness).
- [ ] **D5** Re-validate the JSON parses and the count is now 16 (14 + Q11 + Q12); ids stay consistent
      with the existing scheme (Q11/Q12 slot between DATA Q10 and CONFLICT Q13).

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
