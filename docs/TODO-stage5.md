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

- [x] **0.1** `[DEVIATED - see DEVIATIONS.md #DEV-046]` Confirmed the pinned versions in
  `core-api/build.gradle.kts` (`langchain4j-spring-boot-starter:1.0.0-beta5`,
  `langchain4j-open-ai-spring-boot-starter:1.0.0-beta5`, `langchain4j-pgvector:1.0.0-beta5`) and
  confirmed `langchain4j-anthropic-spring-boot-starter:1.0.0-beta5` resolves at the same coordinate
  (POM fetched from Maven Central; Track A1 adds it). Side-finding: the beta5 pin only covers the
  Spring-integration artifacts — each transitively pulls `langchain4j:1.0.0`/`langchain4j-core:1.0.0`
  (GA) for the actual `@AiService` machinery.
- [x] **0.2** Verified via cached jar sources (no live LLM calls): `@AiService`
  (`dev.langchain4j.service.spring.AiService`, annotation-driven — a `BeanFactoryPostProcessor` builds
  `AiServices.builder(interfaceClass)...build()` under the hood), `@V("name")` parameter injection,
  `@SystemMessage`/`@UserMessage` all match current GA docs exactly (pulled transitively from GA core,
  per 0.1). Enum return (`RouteDecision`) is auto-handled by `EnumOutputParser` — format instructions
  auto-appended to the prompt, response parsed case-insensitively with bracket-stripping; no extra code
  needed in `QueryRouter` beyond the method signature.
- [x] **0.3** `[DEVIATED - see DEVIATIONS.md #DEV-046]` Confirmed via `AiServicesAutoConfig` source:
  binding is **not** Spring `@Qualifier` — it's `@AiService(wiringMode = AiServiceWiringMode.EXPLICIT,
  chatModel = "<beanName>")`, a LangChain4j-internal bean-name-string lookup. `AUTOMATIC` wiring throws
  `IllegalConfigurationException` when >1 `ChatModel` bean exists (Stage 5 always has two). Chosen
  wiring for Track A2/C3/C4: `QueryRouter` + `TextToSqlAgent` (temp 0.0) → `chatModel = "routingModel"`;
  Stage 7's `ConflictSynthesizer` (temp 0.3) → `chatModel = "synthesisModel"`. Also: the implemented
  interface is `ChatModel`, not the plan snippet's `ChatLanguageModel` (renamed in GA).

---

## Track A — Build dependency + LangChain4j config + application.yml

_Directory:_ `core-api/`. Runtime wiring; independent to author but D/E need it to boot.

- [x] **A1** Added `dev.langchain4j:langchain4j-anthropic-spring-boot-starter:1.0.0-beta5` to
  `core-api/build.gradle.kts` — kept `langchain4j-open-ai-spring-boot-starter` `[DEV-015]`. Resolves
  and appears on the runtime classpath (confirmed via `bootRun`'s process classpath).
- [x] **A2** `config/LangChain4jConfig.kt` created. `[DEVIATED - see DEVIATIONS.md #DEV-046]`
  `@Bean fun routingModel(): ChatModel` / `@Bean fun synthesisModel(): ChatModel` (bean method name is
  the wiring key, not `@Qualifier`) → `AnthropicChatModel` at temperature 0.0/0.3 respectively, model
  name from `app.llm.chat-model`, api key from `app.llm.chat-api-key`. No embedding/store/retriever
  beans added (Stage 6). `QueryRouter`/`TextToSqlAgent` bind via `@AiService(wiringMode = EXPLICIT,
  chatModel = "routingModel")`.
- [x] **A3** `application.yml` already had `app.llm.chat-api-key`/`chat-model` (no default) and Hikari
  `connection-init-sql: "SET statement_timeout = '3s'"` from an earlier stage — verified present,
  confirmed live via a manual `pg_sleep(5)` cancellation test (Track F8).
- [x] **A4** `[DEVIATED - see DEVIATIONS.md #DEV-046]` — see Track 0.3 above; logged.

---

## Track B — SqlSafetyValidator (TDD, fully independent)

_Directory:_ `core-api/src/main/kotlin/com/blamezeus/coreapi/safety/` + matching test dir. Pure Kotlin,
no Spring/DB. Start immediately.

- [x] **B1** `SqlSafetyValidatorTest.kt` written first (15 cases incl. all bullets below plus a
  `deleted_entities` table-name false-positive check).
- [x] **B2** `safety/SqlSafetyValidator.kt` implemented — whole-keyword regex (`\bKEYWORD\b`)
  case-insensitive deny-list, `;`-anywhere rejection, SELECT/WITH-only allow-list. 15/15 tests green.

---

## Track C — AI service interfaces (routing + text-to-SQL)

_Directory:_ `core-api/src/main/kotlin/com/blamezeus/coreapi/routing/` and `.../ai/`. Depends on the
beta5 shapes from Track 0.

- [x] **C1** `QueryRouterTest.kt` written first — asserts `RouteDecision.entries` is exactly
  `{SQL, RAG, MIXED}` (size 3, no `CONFLICT`) `[DEV-014]`, and a mockk'd `QueryRouter` consumer only
  branches on those three values (exhaustive `when`, no `else`).
- [x] **C2** Confirmed `routing/RouteDecision.kt` already correct (`SQL`, `RAG`, `MIXED`, no
  `CONFLICT`) — no change needed `[DEV-014]`.
- [x] **C3** `routing/QueryRouter.kt` `@AiService(wiringMode = EXPLICIT, chatModel = "routingModel")`
  interface, `classify(question: String): RouteDecision`, prompt routes SQL/RAG/MIXED per the plan's
  examples, omits any CONFLICT instruction `[DEV-014]`.
- [x] **C4** `ai/TextToSqlAgent.kt` `@AiService(wiringMode = EXPLICIT, chatModel = "routingModel")` —
  `generateSql(@V("schema") schema: String, @V("question") question: String): String` with
  `@UserMessage("Question: {{question}}")` (required once 2 `@V` params are present — see Track 0.2's
  `getUserMessageTemplate` finding). Prompt covers SELECT-only/ILIKE/WITH RECURSIVE/source-join rules
  per the plan, plus two rules added after live testing (Track F, DEV-047): no markdown fences, and
  anchor/recursive-branch column-scope consistency in `WITH RECURSIVE`. No hand-listed schema (DEV-023).

---

## Track D — SqlQueryHandler (TDD)

_Depends on:_ B2 (`SqlSafetyValidator`), C4 (`TextToSqlAgent`). Injects the existing
`SchemaIntrospector` + `JdbcTemplate`. _Directory:_ `.../handler/`.

- [x] **D1** `SqlQueryHandlerTest.kt` written first — 11 cases: validator-before-JdbcTemplate ordering,
  rejected SQL never reaches `JdbcTemplate`, exact-verbatim SQL to the validator, markdown-fence
  stripping (added after Track F, DEV-047), citation extraction (present/absent), empty-result and
  aggregate-zero placeholder cases, and a genuine-nonzero-value control case.
- [x] **D2** `handler/SqlQueryHandler.kt` — exact flow as specified, plus a `stripMarkdownFence` step
  between `generateSql` and `validate` (DEV-047).
- [x] **D3** `log.debug("Generated SQL for '{}': {}", question, sql)` before `jdbcTemplate.queryForList`
  — confirmed live in Track F7 for all 5 gold questions.
- [x] **D4** Empty/aggregate-zero detection implemented (`isAggregateZero`, single row all
  null-or-numeric-zero); Stage-5 placeholder `QueryResponse` returned with
  `// TODO(Stage 6): wire real RAG fallback` marker, no shape deviation from the plan.

---

## Track E — QueryService orchestrator + endpoint

_Depends on:_ D2 (`SqlQueryHandler`), C3 (`QueryRouter`). _Directory:_ `.../service/` + `.../controller/`.

- [x] **E1** `QueryServiceTest.kt` written first — 5 cases: SQL dispatches to `SqlQueryHandler` only,
  router exception defaults to `RAG` without propagating, RAG/MIXED get the Stage-5 placeholder (not
  an exception), SQL-handler exception → `serviceError == true` + non-blank answer, and a router
  failure's response is always well-formed. (RAG/MIXED real-handler dispatch deferred to Stages 6/8.)
- [x] **E2** `service/QueryService.kt` — exact outer/inner try-catch structure from the plan; `when`
  exhaustive over the 3-value enum, `RAG`/`MIXED` → placeholder with `// TODO(Stage 6/8)` marker
  `[DEV-014]`.
- [x] **E3** `POST /api/v1/query` added to `controller/QueryController.kt`, calls
  `queryService.handle(request.question)`.
- [x] **E4** Confirmed via live `curl` runs (Track F): `routeDecision` populated, `sqlGenerated`
  non-null for SQL answers / null for RAG placeholder and serviceError responses.

---

## Track F — Verification (sequential, run last)

- [x] **F1** Green (15/15).
- [x] **F2** Green (2/2, no `CONFLICT` value).
- [x] **F3** Green (11/11, ordering + fence-stripping + empty/aggregate-zero all covered).
- [x] **F4** Green (5/5).
- [x] **F5** Booted with real `.env` (`LLM_API_KEY`/`LLM_CHAT_MODEL`/`OPENAI_API_KEY`/`ANTHROPIC_API_KEY`
  sourced from the project's `.env`, DB already at Flyway V14 going in): both `AnthropicChatModel`
  beans wired with no `app.llm.*` errors, `ApplicationReady` reached.
- [x] **F6** `[DEVIATED - see DEVIATIONS.md #DEV-047]` All 5 DATA questions run live against real
  Anthropic + Postgres: all route `SQL`, `sqlGenerated` non-null, no `serviceError`, no
  `forbidden_patterns` text. Q9's `sqlGenerated` contains `WITH RECURSIVE`; Q10's SQL executed directly
  returns exactly **12** rows (≥12 ✓). Two real Stage-5 bugs found and fixed live (markdown-fence
  stripping, `relationships` direction schema comment via `V15`) — see DEV-047. After both fixes,
  `required_keywords` coverage: Q6 4/6 (Zeus/Hera/Poseidon/Demeter; Hades/Hestia seeded as
  `type='other_god'`), Q7 1/2 (Heracles; Perseus has zero `relationships` rows), Q8 2/3
  (Medusa/Gorgon; no Cetus entity/myth-participant seeded), Q9 1/3 (Cronus; Heaven/Uranus-Ouranos
  entity split and no Heaven→Chaos edge), Q10 pass. All four shortfalls verified directly against the
  DB as pre-existing Stage 4 seed-data completeness gaps, not Stage 5 pipeline defects — not patched
  here (would require fabricating unverified `relationships`/citation rows); flagged for a Stage 4
  follow-up pass.
- [x] **F7** DEBUG log confirmed present for all 5 F6 queries (`Generated SQL for '...'`); Q9 emitted
  `WITH RECURSIVE`. (No live question happened to route SQL-with-`sources`-join in this run; the
  `sources`-join citation-extraction path is deterministically covered by `SqlQueryHandlerTest`
  instead — see D1.)
- [x] **F8** Confirmed live: `SET statement_timeout = '3s'; SELECT pg_sleep(5);` via `zeus_app` was
  cancelled by Postgres ("canceling statement due to statement timeout"), matching Hikari's
  `connection-init-sql`.
- [x] **F9** `DEVIATIONS.md` updated (DEV-046, DEV-047); affected TODO items marked above;
  `IMPLEMENTATION_PLAN.md §5` amended with a DEV-046 pointer note.
