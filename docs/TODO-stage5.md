# Stage 5 — SQL Pipeline: Detailed Checklist

**Done when:** DATA gold questions (Q6–Q10) answer correctly via `POST /api/v1/query`
(`routeDecision: SQL`, answer contains the expected entities, `sqlGenerated` populated);
`SqlSafetyValidatorTest`, `SqlQueryHandlerTest`, `QueryRouterTest`, and `QueryServiceTest`
(SQL-dispatch slice) all pass.

> This stage builds the first end-to-end query path: `QueryRouter` classifies the question,
> `TextToSqlAgent` turns it into SQL, `SqlSafetyValidator` gates it, `SqlQueryHandler` executes
> it, and `QueryService` orchestrates. **RAG and MIXED handlers do not exist yet** (Stages 6/8) —
> this stage wires only the SQL branch and leaves clearly-marked placeholders for the others.
> **Prerequisite: Stage 4 (Seed Data) must be complete** — the DATA questions query real
> `entities`/`relationships`/`sources` rows, and `SchemaIntrospector` reads the live schema.

> **Gold questions:** `evaluation/gold-questions.json` exists but currently holds **only the DATA
> subset Q6–Q10** (an early pull-forward of the Stage 10 eval artifact). Fields follow
> `IMPLEMENTATION_PLAN.md §7`; two forward-compat keys encode the §7 runner notes — `sql_must_contain`
> (Q9 → `WITH RECURSIVE`) and `min_row_count` (Q10 → ≥12, with an empty `required_keywords`). The
> remaining questions (FACT/MIXED/CONFLICT/REFUSAL) are added in Stages 6–10 as their pipelines land —
> so a green DATA slice here is **not** "gold set passing." No `EvaluationRunner` is built in this
> stage; Track F reads the file by hand / with `curl`.

Before starting, re-read `DEVIATIONS.md`. Relevant carry-overs:
- **DEV-004** — LangChain4j is `1.0.0-beta5`, **not** 1.0.0 GA. Before writing any `@AiService`
  code, verify current beta5 API shapes for `@AiService`, `@V` parameter injection,
  `@SystemMessage`/`@UserMessage`, and structured-return handling. Annotation/param-injection
  shapes may differ from GA docs. (See Track 0.)
- **DEV-014** — There is **no `CONFLICT` route**. `RouteDecision` is `SQL | RAG | MIXED` only
  (already stubbed in Stage 4's `routing/RouteDecision.kt`). `QueryRouter`'s prompt must **omit**
  any "route to CONFLICT" instruction. Conflict surfacing is a router-independent enrichment step
  built later in Stage 7 — do not add it here.
- **DEV-015** — Chat model is **Anthropic** (`AnthropicChatModel`, Claude Haiku 4.5,
  `LLM_CHAT_MODEL=claude-haiku-4-5-20251001`), not `OpenAiChatModel`. `LLM_API_KEY` holds an
  Anthropic key. Add `langchain4j-anthropic-spring-boot-starter`; keep the OpenAI starter (the
  Stage 6 embedding bean still needs it). Run the gold set before committing to the swap
  (swap-after-eval discipline, ADR-008 §5).
- **DEV-023** — `SchemaIntrospector` is **already built and self-describing** (auto-enumerated
  tables + types/FKs/CHECKs/`COMMENT ON` text/value vocabularies). Stage 5 only *consumes* it —
  do **not** hand-write per-table prompt rules; lean on the V8_3 schema comments.
- **DEV-026** — the ADR-005 empty-result fallback also covers **aggregate-zero** results (a single
  row that is all `0`/`NULL` — `COUNT`=0, `SUM`=NULL), since aggregations never return zero rows.
- **DEV-008** — Testcontainers pinned to `1.21.4`; reuse `AbstractContainerTest` for any DB test.

## Parallelization Guide

```
Track 0 (beta5 API spike) ─┐
Track A (build + config)   ├─→ Track D (SqlQueryHandler) ─→ Track E (QueryService + endpoint) ─→ Track F (verify)
Track B (SqlSafetyValidator)┤        ↑                              ↑
Track C (AI interfaces)    ─┘────────┘──────────────────────────────┘
```

- **Track 0** is a short read-only verification spike (no production code) that de-risks the beta5
  API for everyone downstream. Do it first, or in parallel with A/B/C if you accept some rework risk.
- **A, B, C have no dependency on each other** — start all three in parallel immediately.
  - **A** (build dep + `LangChain4jConfig` beans + `application.yml`) is runtime wiring; it blocks
    nothing at *compile* time but D/E need it to actually run.
  - **B** (`SqlSafetyValidator` + its test) is fully self-contained — pure Kotlin, no Spring, no DB.
  - **C** (`QueryRouter`, `TextToSqlAgent` interfaces + `QueryRouterTest`) only needs `RouteDecision`
    (already exists) and the beta5 annotation shapes from Track 0.
- **D depends on B (validator) + C4 (`TextToSqlAgent`)** and injects the existing
  `SchemaIntrospector` + `JdbcTemplate`. Compiles against the interface; needs A's beans to run.
- **E depends on D** (`SqlQueryHandler`) and **C3** (`QueryRouter`) — the orchestrator + endpoint.
- **F is sequential and last.**

---

## Track 0 — beta5 API verification spike (read-only, no production code)

_Purpose:_ resolve DEV-004 before writing `@AiService` code. Look at the actual pinned jars and any
existing beta5 usage in the repo; write findings into a scratch note or inline TODO comments, not the
codebase.

- [ ] **0.1** Confirm the pinned versions in `core-api/build.gradle.kts`
  (`langchain4j-spring-boot-starter:1.0.0-beta5`, `langchain4j-open-ai-spring-boot-starter:1.0.0-beta5`,
  `langchain4j-pgvector:1.0.0-beta5`) and check whether an `langchain4j-anthropic-*` artifact at the
  same beta5 coordinate exists (Track A1 adds it).
- [ ] **0.2** Verify the beta5 shapes of: `@AiService` (annotation-driven vs. `AiServices.builder()`),
  `@V("name")` parameter injection, `@SystemMessage`/`@UserMessage`, and how a `@AiService` method
  returning an **enum** (`RouteDecision`) is deserialized (this is what `QueryRouter` relies on).
- [ ] **0.3** Confirm how `@AiService` interfaces bind to a specific `ChatLanguageModel` bean when
  multiple exist (`@Qualifier("routingModel")` vs. explicit `AiServices` wiring in config) — Stage 5
  has two chat beans at different temperatures, so the binding mechanism matters. Record the chosen
  wiring approach for Track A2 / C3 / C4.

---

## Track A — Build dependency + LangChain4j config + application.yml

_Directory:_ `core-api/`. Runtime wiring; independent to author but D/E need it to boot.

- [ ] **A1** Add `dev.langchain4j:langchain4j-anthropic-spring-boot-starter:1.0.0-beta5` to
  `core-api/build.gradle.kts` — **keep** `langchain4j-open-ai-spring-boot-starter` (the Stage 6
  embedding bean still requires it) `[DEV-015]`. Confirm the artifact resolves (Track 0.1).
- [ ] **A2** `config/LangChain4jConfig.kt` (new file — does not exist yet):
  - `@Bean @Qualifier("routingModel")` → `AnthropicChatModel` (temperature **0.0**), model name from
    `app.llm.chat-model`, api key from `app.llm.chat-api-key` `[DEV-015]`.
  - `@Bean @Qualifier("synthesisModel")` → `AnthropicChatModel` (temperature **0.3**), same model/key
    (used by `ConflictSynthesizer` in Stage 7; build the bean now so config is complete).
  - **No** `embeddingModel` / `embeddingStore` / `contentRetriever` beans here — those are Stage 6,
    and the pgvector store beans are dropped entirely per DEV-025. Do not add them.
  - Wire `QueryRouter` / `TextToSqlAgent` `@AiService` interfaces to `routingModel` per the binding
    approach chosen in Track 0.3.
- [ ] **A3** `application.yml` — ensure `app.llm.chat-api-key: ${LLM_API_KEY}` and
  `app.llm.chat-model: ${LLM_CHAT_MODEL}` (**no default** — must always be set explicitly, per
  CLAUDE.md). Confirm Hikari `connection-init-sql: "SET statement_timeout = '3s'"` is present (it
  caps LLM-generated SQL — Stage 1c should already have it; verify, don't duplicate).
- [ ] **A4** If any Stage 5 assumption from the plan snippets changes on contact with beta5 (e.g. the
  `OpenAiChatModel` snippet in `IMPLEMENTATION_PLAN.md §5`), **log a DEV entry** and mark affected
  items `[DEVIATED - see DEVIATIONS.md #DEV-NNN]` per the deviation protocol. Do not overwrite the plan.

---

## Track B — SqlSafetyValidator (TDD, fully independent)

_Directory:_ `core-api/src/main/kotlin/com/blamezeus/coreapi/safety/` + matching test dir. Pure Kotlin,
no Spring/DB. Start immediately.

- [ ] **B1** *Tests first:* `SqlSafetyValidatorTest.kt` (`safety/` test package). Cover, at minimum
  (`IMPLEMENTATION_PLAN.md §8`):
  - `SELECT id FROM entities` → allowed (no throw)
  - `WITH RECURSIVE t AS (SELECT ...) SELECT * FROM t` → allowed
  - `DROP TABLE entities` → `IllegalArgumentException`
  - `DELETE`, `INSERT`, `UPDATE` statements → rejected
  - `SELECT 1; DROP TABLE entities` (embedded `;`) → rejected
  - case-insensitivity (`drop table ...`, `Select ...`) and leading-whitespace tolerance
- [ ] **B2** `safety/SqlSafetyValidator.kt` — allow only statements starting with `SELECT`/`WITH`;
  deny-list `DROP`, `DELETE`, `INSERT`, `UPDATE`, and the `;` character. Match whole keywords
  case-insensitively (avoid rejecting a legit substring like a column named `updated_at` — test this).
  Throw `IllegalArgumentException` on rejection.

---

## Track C — AI service interfaces (routing + text-to-SQL)

_Directory:_ `core-api/src/main/kotlin/com/blamezeus/coreapi/routing/` and `.../ai/`. Depends on the
beta5 shapes from Track 0.

- [ ] **C1** *Tests first:* `QueryRouterTest.kt` — with a mocked `QueryRouter` (`mockk`), assert the
  handler/consumer only ever acts on `SQL`/`RAG`/`MIXED`; assert `RouteDecision` has **no `CONFLICT`
  value** (compile-time: reference `RouteDecision.entries` and assert size 3 / exact set)
  `[DEV-014]`. (True prompt-classification quality is exercised in Track F against gold questions,
  not unit-tested against a live LLM — no live LLM calls in tests.)
- [ ] **C2** Verify `routing/RouteDecision.kt` is already the correct enum (`SQL`, `RAG`, `MIXED`, **no
  `CONFLICT`**) — stubbed in Stage 4 (Track E5). No change expected; confirm and move on `[DEV-014]`.
- [ ] **C3** `routing/QueryRouter.kt` `@AiService` interface — `@SystemMessage` classifies the question
  into `RouteDecision` (returns the enum directly), temperature 0.0 (bound to `routingModel`). Prompt
  routes schema-boundary/data questions → `SQL`, narrative/"why" questions → `RAG`, multi-hop
  filter+narrate → `MIXED`. **Omit** any CONFLICT instruction `[DEV-014]`. Bind to `routingModel`
  per Track 0.3.
- [ ] **C4** `ai/TextToSqlAgent.kt` `@AiService` interface —
  `fun generateSql(@V("schema") schema: String, @V("question") question: String): String`, temperature
  0.0. `@SystemMessage` uses a `{{schema}}` placeholder populated at call time from
  `SchemaIntrospector.get()`. Prompt rules (`IMPLEMENTATION_PLAN.md §5`): SELECT only; ILIKE for names;
  `WITH RECURSIVE` for lineage; JOIN `sources` for attribution when querying `relationships`/
  `variant_claims`; for direct `entities` attribute queries (`type`/`generation`/`domain`) **do not
  fabricate a source join** (no source FK exists there). Do **not** re-list tables/columns by hand —
  the injected `SchemaIntrospector` prompt already carries them (DEV-023).

---

## Track D — SqlQueryHandler (TDD)

_Depends on:_ B2 (`SqlSafetyValidator`), C4 (`TextToSqlAgent`). Injects the existing
`SchemaIntrospector` + `JdbcTemplate`. _Directory:_ `.../handler/`.

- [ ] **D1** *Tests first:* `SqlQueryHandlerTest.kt` — mock `TextToSqlAgent` + `SqlSafetyValidator`
  (`mockk`); assert the **validator is called before** `JdbcTemplate` executes (ordering verify);
  assert a rejected SQL never reaches `JdbcTemplate`; assert generated SQL is passed to the validator
  verbatim. Include an empty-result case and an aggregate-zero case (see D4).
- [ ] **D2** `handler/SqlQueryHandler.kt` — constructor injects `textToSqlAgent`, `schemaIntrospector`,
  `validator`, `jdbcTemplate` (`IMPLEMENTATION_PLAN.md §5`). Flow:
  `generateSql(schemaIntrospector.get(), question)` → `validator.validate(sql)` →
  `jdbcTemplate.queryForList(sql)` → format rows into an answer + extract citations from result columns
  → return `QueryResponse(routeDecision = SQL, sqlGenerated = sql, ...)`.
- [ ] **D3** Log the generated SQL at **DEBUG** level in `SqlQueryHandler` before execution (plan item
  "Log generated SQL at DEBUG level").
- [ ] **D4** Empty-result fallback (ADR-005 §Decision.3 + **DEV-026**): zero rows → fall back to RAG;
  also treat **aggregate-zero** as empty (a single row whose values are all `0`/`NULL`).
  > ⚠️ **Cross-stage dependency:** the actual RAG fallback needs `RagQueryHandler`, which is **Stage
  > 6**. For Stage 5, implement the *detection* (empty + aggregate-zero) now and route the fallback to
  > a clearly-marked Stage-5 placeholder response (e.g. an "answer not found in structured data"
  > `QueryResponse`), with a `// TODO(Stage 6): wire real RAG fallback` marker. Wire the real
  > `RagQueryHandler` call in Stage 6. If this placeholder shape differs from the plan, log a DEV entry.

---

## Track E — QueryService orchestrator + endpoint

_Depends on:_ D2 (`SqlQueryHandler`), C3 (`QueryRouter`). _Directory:_ `.../service/` + `.../controller/`.

- [ ] **E1** *Tests first:* `QueryServiceTest.kt` (SQL-dispatch slice) — mock `QueryRouter` +
  `SqlQueryHandler`; assert a `SQL` decision dispatches to `SqlQueryHandler` and nowhere else; assert a
  **router exception defaults to RAG** (`IMPLEMENTATION_PLAN.md §5` outer catch); assert that when both
  router and handler throw, the response has `serviceError == true` and a non-empty `answer`. (RAG/MIXED
  dispatch assertions are added in Stages 6/8 when those handlers exist.)
- [ ] **E2** `service/QueryService.kt` skeleton — inject `queryRouter` + `sqlQueryHandler`. Outer
  try/catch around `queryRouter.classify(question)` degrades to `RouteDecision.RAG` on failure; inner
  try/catch around dispatch returns a `serviceError = true` `QueryResponse` on handler failure (plan
  §QueryService). `when(route)`:
  - `SQL` → `sqlQueryHandler.handle(question)`
  - `RAG`, `MIXED` → **Stage-5 placeholder** `QueryResponse` ("not yet implemented", marked
    `// TODO(Stage 6/8)`) — these branches get real handlers in Stages 6/8. Keep the `when` exhaustive
    over the 3-value enum (no `CONFLICT` case — it doesn't exist) `[DEV-014]`.
- [ ] **E3** Wire `POST /api/v1/query` in `controller/QueryController.kt` — accept `QueryRequest`, call
  `queryService.handle(request.question)`, return `QueryResponse`. The controller skeleton +
  `GET /entities` / `GET /sources` already exist from Stage 4 (Track F) — add the POST mapping only.
- [ ] **E4** Sanity: `QueryResponse.routeDecision` is populated with the routed value; `sqlGenerated`
  is non-null for SQL answers and null otherwise; Swagger UI (`/swagger-ui.html`) lists the new POST.

---

## Track F — Verification (sequential, run last)

- [ ] **F1** `./gradlew :core-api:test --tests "*SqlSafetyValidatorTest"` — green.
- [ ] **F2** `./gradlew :core-api:test --tests "*QueryRouterTest"` — green (no `CONFLICT` value).
- [ ] **F3** `./gradlew :core-api:test --tests "*SqlQueryHandlerTest"` — green (validator-before-JDBC
  ordering + empty/aggregate-zero cases).
- [ ] **F4** `./gradlew :core-api:test --tests "*QueryServiceTest"` — green (SQL dispatch + router
  fallback + serviceError).
- [ ] **F5** Boot `core-api` locally (DB running, `LLM_API_KEY` + `LLM_CHAT_MODEL` + `OPENAI_API_KEY`
  set): confirm `AnthropicChatModel` beans wire and the app reaches `ApplicationReady` with no missing
  `app.llm.*` property errors.
- [ ] **F6** Run each DATA question in `evaluation/gold-questions.json` (Q6–Q10) via
  `curl -XPOST localhost:8080/api/v1/query -d '{"question":"..."}'`. For each: assert
  `routeDecision: SQL`, `sqlGenerated` non-null, and every string in `required_keywords` appears
  (case-insensitive) in the answer while no `forbidden_patterns` string does. This is the stage's
  done-when gate. Per-question specials from §7 / the JSON:
  - **Q9** — the answer must contain all of Cronus/Ouranos/Chaos **and** `sqlGenerated` must contain
    `WITH RECURSIVE` (the `sql_must_contain` key); guard the null check on `sqlGenerated` first.
  - **Q10** — `required_keywords` is empty by design; instead execute the generated SQL against the DB
    and assert it returns **≥12 rows** (`min_row_count`) — do not keyword-search the prose.
- [ ] **F7** Check the DEBUG log shows the generated SQL for each F6 query; spot-check that Q9 emitted
  `WITH RECURSIVE` and that an attribution-style question JOINed `sources`.
- [ ] **F8** Confirm the `statement_timeout = '3s'` cap is live (a deliberately expensive/looping SQL is
  killed rather than hanging) — sanity check on the Hikari `connection-init-sql`.
- [ ] **F9** If any deviation occurred, ensure `DEVIATIONS.md` is updated, affected items are marked
  `[DEVIATED - see DEVIATIONS.md #DEV-NNN]`, and the Stage 5 note in `IMPLEMENTATION_PLAN.md` /
  `TODO.md` reflects it (deviation protocol steps 2–5).
