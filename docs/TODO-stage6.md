# Stage 6 — RAG Pipeline: Detailed Checklist

**Done when:** FACT gold questions (Q1–Q5) return cited answers via `POST /api/v1/query`
(`routeDecision: RAG`, non-empty `citations` with real `author`/`work`/`passageRef`, no text-parsed
citations); `RagQueryHandlerTest`, `ContentRetrieverTest`, and `EmbeddingConsistencyTest` pass; the
retrieval query provably hits the V8_4 halfvec HNSW index (`EXPLAIN ANALYZE`).

> This stage builds the second end-to-end query path. Query text → `EmbeddingModel` (OpenAI
> `text-embedding-3-large`, 3072-dim) → custom `ContentRetriever` (halfvec cosine over
> `narrative_chunks`) → `RagAgent` `@AiService` (synthesises a cited `RagResponse` from retrieved
> context, temp 0.3) → `RagQueryHandler` → `QueryService` dispatches the `RAG` route. **MIXED and the
> conflict-enrichment step do not exist yet** (Stages 7/8) — this stage wires only the RAG branch and
> the RagAgent conflict-aware *backstop* (unstructured disagreements in retrieved prose), NOT the
> structured `variant_claims` enrichment (that is Stage 7).
> **Prerequisite: Stages 2–4 complete** — 3,524 embedded chunks live in `narrative_chunks`, all
> stamped `embedding_model = 'text-embedding-3-large'` (V8_4/DEV-028). Without ingested vectors the
> retriever returns nothing and the FACT slice cannot pass.

> **Gold questions:** `evaluation/gold-questions.json` currently holds **only DATA Q6–Q10** (pulled
> forward in Stage 5). This stage **adds the FACT subset Q1–Q5** (Track G) — authoring them is part of
> Stage 6, not a pre-existing artifact. No `EvaluationRunner` is built here; Track H reads the file by
> hand / with `curl`. A green FACT slice here is **not** "gold set passing."

Before starting, re-read `DEVIATIONS.md`. Relevant carry-overs:
- **DEV-004** — LangChain4j is `1.0.0-beta5`, **not** 1.0.0 GA. Before writing any `@AiService` /
  retriever code, verify current beta5 API shapes for `RagAgent @AiService`, `ContentRetriever`,
  `Content`/`TextSegment`/`Metadata`, `EmbeddingModel.embed(...)`, and how a bean-defined
  `ContentRetriever` binds to an `@AiService`. (See Track 0.)
- **DEV-046** — Multi-`ChatModel`-bean wiring is `@AiService(wiringMode = EXPLICIT, chatModel = "…")`
  (LangChain4j bean-name string, **not** Spring `@Qualifier`); the model interface is `ChatModel`, not
  `ChatLanguageModel`. `RagAgent` runs on `synthesisModel` (temp 0.3, already defined in
  `LangChain4jConfig`). Confirm the same annotation carries a `contentRetriever = "beanName"` (or
  equivalent) attribute in beta5 for EXPLICIT wiring, or the retriever will not attach (Track 0.2).
- **DEV-025** — **No `PgVectorEmbeddingStore` / `EmbeddingStoreContentRetriever` beans.** beta5's store
  hardcodes an `embedding_id UUID / text` schema and cannot read `narrative_chunks(id, content, …)`.
  Stage 6 implements a **custom `ContentRetriever` over `JdbcTemplate`**; **drop `langchain4j-pgvector`**
  from `build.gradle.kts`.
- **DEV-028 / ADR-013** — Embedding is `text-embedding-3-large`, **vector(3072)**. The HNSW index is a
  **halfvec EXPRESSION index** (`narrative_chunks_embedding_hnsw_idx`, V8_4). The retrieval query MUST
  cast: `ORDER BY embedding::halfvec(3072) <=> ($1::vector(3072))::halfvec(3072)` — a plain
  `embedding <=> ?` silently seq-scans. `embedding_model` column exists and is stamped per row.
- **DEV-033 / DEV-034** — Chunks are **paragraph-aligned**; `passage_ref` is the paragraph's
  corpus-native range (`"3.38-3.57"`; bare points for Apollodorus sections). **The chunk's ref IS the
  citation.** Cross-chunk overlap was dropped — the only near-duplicates are sub-chunks of ~160
  oversized paragraphs that **share a `passage_ref`**; dedupe retrieved chunks by `passage_ref` when
  building context so two sub-chunks of one paragraph don't both consume a top-k slot.
- **DEV-008** — Testcontainers pinned `1.21.4`; reuse `AbstractContainerTest` for any DB test.
- **DEV-015 / ADR-006** — Embedding model name comes from `app.llm.embedding-model`
  (`EMBEDDING_MODEL`, default `text-embedding-3-large`) and key from `app.llm.embedding-api-key`
  (`OPENAI_API_KEY`) — both already present in `application.yml`. **Never hardcode the model literal**
  in the bean/checker.

## Parallelization Guide

```
Track 0 (beta5 RAG API spike) ─┐
Track A (build + EmbeddingModel)├─→ Track B (ContentRetriever) ─┐
Track C (RagAgent interface)  ─┘                                ├─→ Track D (RagQueryHandler) ─→ Track E (QueryService) ─→ Track H (verify)
Track F (embedding consistency guard) ──────────────────────────┘                                    ↑
Track G (author FACT gold Q1–Q5) ────────────────────────────────────────────────────────────────────┘
```

- **Track 0** — short read-only spike (no production code). De-risks the beta5 retriever/`@AiService`
  binding for B and C. Do it first, or in parallel with A/F/G accepting some rework risk.
- **A, F, G have no dependency on each other** — start all three immediately.
  - **A** (drop `langchain4j-pgvector`, add `EmbeddingModel` bean) is runtime wiring; blocks B/C/F at
    *runtime* (they inject the bean) but not at compile time.
  - **F** (`EmbeddingConsistencyChecker` + `canary-aphrodite.json` + `EmbeddingConsistencyTest`) is a
    self-contained startup guard; only depends on the `app.llm.embedding-model` value and the existing
    `narrative_chunks.embedding_model` column. **F's canary-fixture generation is an offline Python
    step** — kick it off early (it needs a live `OPENAI_API_KEY`).
  - **G** (author FACT Q1–Q5 in `gold-questions.json`) is pure JSON authoring against the corpus; no
    code dependency. Track H consumes it.
- **B depends on A** (`EmbeddingModel` bean) **+ Track 0** (`Content`/`Metadata` shape). Testable with a
  mocked `EmbeddingModel` + Testcontainers DB seeded with a few embedded rows.
- **C depends on Track 0** (retriever→`@AiService` binding + JSON return shape). Compiles independently;
  needs B's `ContentRetriever` bean + A's `EmbeddingModel` to actually retrieve at runtime.
- **D depends on C** (`RagAgent` interface — mock it in the test). **E depends on D.** **H is last.**

---

## Track 0 — beta5 RAG API verification spike (read-only, no production code)

_Purpose:_ resolve DEV-004 for the RAG surface before writing code. Inspect the pinned jars / existing
beta5 usage; write findings into a scratch note or inline TODO comments, not the codebase. Log anything
that contradicts the plan as a DEV entry.

- [x] **0.1** Confirm `EmbeddingModel` bean shape: `dev.langchain4j.model.openai.OpenAiEmbeddingModel`
  builder (`.apiKey`/`.modelName`/`.dimensions`?) is on the classpath via
  `langchain4j-open-ai-spring-boot-starter` (kept per DEV-015). Confirm `text-embedding-3-large`
  returns **3072-dim** vectors natively (ADR-013) and whether `.dimensions(3072)` must be set
  explicitly or is the model default. Note the `embed(String): Response<Embedding>` /
  `Embedding.vector(): float[]` accessor shapes B will call.
  — Confirmed: `OpenAiEmbeddingModelName.TEXT_EMBEDDING_3_LARGE.dimension() == 3072` is the
  `knownDimension()` fallback when `.dimensions()` is left null, so it need not be set explicitly.
  Accessor chain confirmed: `embed(String): Response<Embedding>` → `.content(): Embedding` →
  `.vector(): FloatArray`. See scratch note §0.1.
- [x] **0.2** Resolve **how a bean-defined `ContentRetriever` binds to `RagAgent @AiService`** under
  EXPLICIT wiring (DEV-046 established chat-model binding is a bean-name string, not `@Qualifier`).
  Check `AiServicesAutoConfig` source for a `contentRetriever` attribute on
  `dev.langchain4j.service.spring.AiService` and whether a single `ContentRetriever` bean auto-attaches
  or must be named. Record the exact annotation form C3 will use.
  — Confirmed: `contentRetriever` is a bean-name string attribute, same mechanism as `chatModel`.
  Under EXPLICIT wiring there is NO auto-attach even with a single candidate bean — the attribute
  must be set or the retriever silently doesn't wire. Form for C1:
  `@AiService(wiringMode = EXPLICIT, chatModel = "synthesisModel", contentRetriever = "<beanName>")`.
  See scratch note §0.2.
- [x] **0.3** Confirm structured-return (`RagResponse`) deserialization in beta5: with a `@SystemMessage`
  describing the JSON schema, does `AiServices` auto-deserialize the POJO (as in the plan §5 snippet),
  and does it need `@UserMessage` on the param when there is a single argument? Note whether nested
  `List<Citation>` deserializes without extra annotations. (Cross-check the Stage 5 finding that
  enum/POJO output parsing is handled by GA core, DEV-046.)
  — Confirmed: a single unannotated parameter is auto-treated as the user message
  (`findUserMessageTemplateFromTheOnlyArgument`), exactly like `QueryRouter.classify` already does —
  no `@UserMessage` needed. POJO parsing (incl. nested `List<Citation>`) goes through the generic
  reflection-based `OutputParser`, same family as `RouteDecision` enum parsing. Since
  `AnthropicChatModel` doesn't advertise `RESPONSE_FORMAT_JSON_SCHEMA`, the framework additionally
  auto-appends textual format instructions to the user message (harmless overlap with our
  `@SystemMessage` JSON description). See scratch note §0.3.
- [x] **0.4** Confirm the `Content` / `TextSegment` / `Metadata` API B must emit: how to attach
  `source_id` / `passage_ref` / score to a retrieved `Content` so C's `@AiService` context and the
  handler's citations can read them. Note the `Content.from(TextSegment)` + `Metadata.from(map)` shapes.
  — Confirmed and refined: two distinct metadata bags. `Content.metadata(): Map<ContentMetadata, Object>`
  (closed enum: `SCORE`/`RERANKED_SCORE`/`EMBEDDING_ID`) carries the retrieval score; `TextSegment`'s
  own `Metadata` (arbitrary `String`-keyed map via `Metadata.from(map)`) carries `source_id`/`passage_ref`.
  Full shape: `Content.from(TextSegment.from(content, Metadata.from(mapOf("source_id" to id, "passage_ref" to ref))), mapOf(ContentMetadata.SCORE to score))`.
  See scratch note §0.4.

**No plan contradictions found; no new DEV-NNN required.** Full findings:
`/private/tmp/claude-501/-Users-ekaterina-alay-Documents-blame-zeus/0ada99d9-90c7-4aa9-9914-2448d9d5d312/scratchpad/track0-findings.md`
(scratch note, not part of the repo).

---

## Track A — Build dependency + EmbeddingModel bean + config

_Directory:_ `core-api/`. Runtime wiring; independent to author but B/C/F need it to boot.

- [x] **A1** Remove `dev.langchain4j:langchain4j-pgvector:1.0.0-beta5` from `core-api/build.gradle.kts`
  (DEV-025 — the custom retriever replaces it). Keep `langchain4j-open-ai-spring-boot-starter` (the
  `EmbeddingModel` bean needs it) and `langchain4j-anthropic-spring-boot-starter`. Confirm the build
  still resolves and `bootRun` classpath no longer contains `langchain4j-pgvector`.
  — Done. `:core-api:compileKotlin` and `:core-api:test` both green with the dependency removed.
- [x] **A2** Add `@Bean fun embeddingModel(): EmbeddingModel` to `config/LangChain4jConfig.kt` —
  `OpenAiEmbeddingModel`, `apiKey` from `app.llm.embedding-api-key`, `modelName` from
  `app.llm.embedding-model` (**injected, never the literal** per ADR-006/DEV-015), dimensions per Track
  0.1. Only ONE `EmbeddingModel` bean exists, so no EXPLICIT-wiring dance is needed for it (unlike the
  two `ChatModel` beans). Update the class doc comment (currently says "no embeddingModel bean here").
  — Done; `dimensions()` deliberately left unset per Track 0.1 finding (native 3072 default). Class doc
  comment updated.
- [x] **A3** Confirm `application.yml` already carries `app.llm.embedding-api-key: ${OPENAI_API_KEY}`
  and `app.llm.embedding-model: ${EMBEDDING_MODEL:text-embedding-3-large}` — **present since Stage 4**;
  verify, no edit expected. Confirm `.env` supplies `OPENAI_API_KEY`.
  — Confirmed present in both files, no edit made.

---

## Track B — Custom ContentRetriever over JdbcTemplate (TDD)

_Directory:_ `core-api/src/main/kotlin/com/blamezeus/coreapi/ai/` (or `.../rag/`) + matching test dir.
_Depends on:_ A2 (`EmbeddingModel` bean, injected) + Track 0.1/0.4. This is the DEV-025 replacement for
`PgVectorEmbeddingStore`.

- [x] **B1** `ContentRetrieverTest.kt` written first (Testcontainers, `AbstractContainerTest`) — seed a
  handful of `narrative_chunks` rows with known embeddings (or embed via a mocked `EmbeddingModel`
  returning fixed vectors), then assert: (a) top-k ordering by cosine distance, (b) `maxResults = 5`
  cap, (c) `minScore = 0.65` filter drops below-threshold rows, (d) **`passage_ref` dedupe** — two
  sub-chunks sharing a ref don't both appear (DEV-034), (e) each returned `Content` carries
  `source_id` + `passage_ref` in metadata, (f) empty result when nothing clears threshold.
  — Done as `NarrativeChunkContentRetrieverTest.kt`: 8 seeded rows at precise cosine-similarity
  angles cover ordering + cap + minScore-drop + dedupe in one assertion, plus 2 more tests for the
  metadata shape and the fully-empty case. 3/3 green.
- [x] **B2** Implement the custom `ContentRetriever` (`implements dev.langchain4j.rag.content.retrieval
  .ContentRetriever`): `embeddingModel.embed(query)` → JdbcTemplate query with the **REQUIRED halfvec
  cast** —
  `ORDER BY embedding::halfvec(3072) <=> ($1::vector(3072))::halfvec(3072) LIMIT ?` — selecting
  `content, source_id, passage_ref` and the cosine score; filter by `minScore`; dedupe by
  `passage_ref`; map each row to `Content.from(TextSegment.from(content, Metadata.from(...)))`. Inject
  `maxResults`/`minScore` (defaults 5 / 0.65) from config or constants — comment that `minScore` is the
  Track H tuning knob (§7). **Do not** hand-embed the vector literal in Kotlin — bind the `float[]` as a
  pgvector parameter (confirm the parameter form: `?::vector(3072)` with a string/array bind).
  — Done as `NarrativeChunkContentRetriever.kt`. Vector bound via `com.pgvector:pgvector`'s `PGvector`
  (added as a direct dependency — it was only ever transitive through the now-removed
  `langchain4j-pgvector`), no manual literal formatting. SQL wraps the halfvec-cast distance in a
  subquery so `ORDER BY`/`LIMIT`/score all reuse one computed `distance` alias. `maxResults`/`minScore`
  are `@Value`-injected from `app.rag.max-results`/`app.rag.min-score` (new `application.yml` keys,
  defaults 5/0.65). SQL over-fetches `maxResults * 3` rows before Kotlin-side minScore filter + dedupe
  + final cap, so the rare shared-`passage_ref` case doesn't shrink below `maxResults` distinct passages.
- [x] **B3** Register the retriever as a Spring `@Bean` (or `@Component`) so Track C's `@AiService` can
  bind it (name per Track 0.2).
  — `@Component`, default bean name `narrativeChunkContentRetriever` (matches Track C1's
  `contentRetriever` attribute). Confirmed live: the full `@SpringBootTest` suite boots cleanly with
  `RagAgent` wired against this bean name — a mismatch would fail every context-backed test.
- [x] **B4** Log at DEBUG: query text, returned chunk count, top score, and the `passage_ref`s retrieved
  (mirrors `SqlQueryHandler`'s "Generated SQL" DEBUG line for Track H observability).
  — Done.

---

## Track C — RagAgent @AiService interface

_Directory:_ `.../ai/`. _Depends on:_ Track 0.2/0.3 + B3 (retriever bean, runtime). Compiles independently.

- [x] **C1** `ai/RagAgent.kt` `@AiService` interface bound to `synthesisModel` (temp 0.3) and the
  Track-B retriever, per the EXPLICIT-wiring form resolved in Track 0.2 (e.g.
  `@AiService(wiringMode = EXPLICIT, chatModel = "synthesisModel", contentRetriever = "…")`).
  `fun answer(@UserMessage question: String): RagResponse` (confirm `@UserMessage` need per Track 0.3).
  — Done: `contentRetriever = "narrativeChunkContentRetriever"`. No `@UserMessage` — single
  unannotated `question` param is auto-treated as the user message (Track 0.3), same as
  `QueryRouter.classify`.
- [x] **C2** `@SystemMessage`: "Greek mythology scholar, answer using ONLY provided context, return
  JSON `{answer, citations:[{author, work, passageRef}]}`, cite every factual claim, empty citations +
  explanatory sentence when context doesn't support an answer" (plan §5 snippet). **Plus the ADR-007 §3
  conflict-aware backstop** `[DEV-014]`: if retrieved passages give **different accounts of the same
  point from different sources**, present each with its attribution rather than merging or picking one.
  This is the RagAgent *prose* backstop only — structured `variant_claims` enrichment is Stage 7.
  — Done, matches the plan's wording plus the conflict-aware backstop paragraph.
- [x] **C3** Confirm `RagResponse` DTO (`ai`/`domain.dto`) matches the JSON the system message promises
  (`answer: String`, `citations: List<Citation>`) — it already exists (`domain/dto/RagResponse.kt`);
  verify `Citation` field names (`author`/`work`/`passageRef`/`stance`) deserialize from the model's
  JSON. No new DTO expected.
  — Confirmed unchanged; no new DTO needed. Full `@SpringBootTest` suite boots cleanly with `RagAgent`
  registered (proxy creation + retriever/chatModel bean resolution all succeed at context startup) —
  live JSON deserialization itself is exercised end-to-end starting at Track D/H once a handler calls it.

---

## Track D — RagQueryHandler (TDD)

_Directory:_ `.../handler/`. _Depends on:_ C1 (`RagAgent` interface — mocked in test).

- [x] **D1** `RagQueryHandlerTest.kt` written first — mock `RagAgent`; assert the handler returns
  `RagResponse.citations` **without any text/prose parsing**, maps `answer`/`citations` straight into
  `QueryResponse(routeDecision = RAG, sqlGenerated = null, conflicts = emptyList())`, and that a
  no-context `RagResponse` (empty citations + "not supported" answer) passes through intact rather than
  erroring. Assert `RagAgent.answer` is called exactly once with the raw question.
  — Done, written and confirmed red (`Unresolved reference 'RagQueryHandler'`) before D2. 3/3 green
  after implementation.
- [x] **D2** `handler/RagQueryHandler.kt` — `ragAgent.answer(question)` → map `RagResponse` →
  `QueryResponse`. Retriever auto-populates context (no manual retrieval call here); citations are
  already structured. `conflicts = emptyList()` (Stage 7 enrichment fills it later); `serviceError`
  left default false.
  — Done, direct 1:1 mapping, no parsing logic — matches D1's test exactly. Full suite green.

---

## Track E — QueryService RAG route

_Directory:_ `.../service/`. _Depends on:_ D2 (`RagQueryHandler`).

- [ ] **E1** `QueryServiceTest.kt` extended — RAG route now dispatches to `RagQueryHandler` (was the
  Stage-5 placeholder); `RagQueryHandler` exception → `serviceError == true` + non-blank answer (reuse
  the existing inner try/catch); the **router-failure-defaults-to-RAG** path (already implemented Stage
  5) now yields a real RAG answer, not the placeholder — update that assertion. MIXED stays a
  placeholder (Stage 8).
- [ ] **E2** `service/QueryService.kt` — inject `RagQueryHandler`; `when(route)` `RAG -> ragQueryHandler
  .handle(question)`; drop the `RAG` arm of `placeholderResponse` (MIXED-only placeholder remains).
  Remove the `// TODO(Stage 6/8)` for RAG.
- [ ] **E3** **SQL empty-result → RAG fallback** (ADR-005 §Decision.3, DEV-026): `SqlQueryHandler`
  carries a `// TODO(Stage 6): wire real RAG fallback` marker for its empty / aggregate-zero branch.
  Decide scope: either wire `RagQueryHandler` as the fallback there now, or (if keeping SQL/RAG handlers
  decoupled) have `QueryService` detect the SQL empty-placeholder and re-dispatch to RAG. **Not in the
  master Stage 6 bullet list** — surfaced here from the code marker; confirm intent before implementing,
  and if deferred, re-point the marker to a later stage + log the decision.
- [ ] **E4** Verify via `curl` in Track H: a FACT question returns `routeDecision: RAG`, non-empty
  `citations`, `sqlGenerated: null`.

---

## Track F — Embedding consistency guard (checker + canary + test)

_Directory:_ `.../config/` + test dir + `evaluation/` or test resources. _Independent_ — start early.
ADR-006, deferred to this stage per DEV-015.

- [x] **F1** `config/EmbeddingConsistencyChecker.kt` — `@EventListener(ApplicationReadyEvent)` that
  compares `app.llm.embedding-model` against the distinct `embedding_model` value(s) in
  `narrative_chunks` (column exists since V8_4/DEV-028). On mismatch: **log an error, never block
  startup** (drift is a data problem, not a boot failure). Handle the empty-table case gracefully
  (log info, no error). Do NOT hardcode `text-embedding-3-large` — read the injected config value.
  — Done, plain `JdbcTemplate`-backed `@Component`, config value injected via `@Value`.
- [x] **F2** Generate `canary-aphrodite.json` **once, offline** via the Python pipeline with
  `EMBEDDING_MODEL=text-embedding-3-large` (DEV-028): a fixed query string ("Who were Aphrodite's
  parents?" or similar) + its known 3072-dim embedding vector. Store under test resources. This pins the
  embedding model's output so a silent model/dimension swap is caught. (Needs a live `OPENAI_API_KEY`;
  kick off early.)
  — Done via new one-off `ingestion/scripts/generate_canary.py` (reuses `pipeline.embedding_pipeline
  .embed_batch`), run once against the live key. Output confirmed 3072 dims, model
  `text-embedding-3-large`, written to `core-api/src/test/resources/canary-aphrodite.json`.
- [x] **F3** `EmbeddingConsistencyTest.kt` — embed the canary query via the live `EmbeddingModel` bean
  (or mock, per test policy — **no live LLM in unit tests**; use a Testcontainers/integration tag if a
  real embed is required) and assert dimension == 3072 and cosine similarity to the stored canary vector
  ≈ 1.0 within tolerance. Assert the checker logs (not throws) on a deliberately mismatched config.
  — Done: `EmbeddingModel` mocked per the no-live-LLM-in-tests policy (returns the pinned vector itself —
  this exercises the dimension/cosine plumbing, not real-model drift detection, which Track H4 checks
  live). Checker tested with a Logback `ListAppender` across mismatch/match/empty-table cases. 4/4 green.

---

## Track G — Author FACT gold questions Q1–Q5

_Directory:_ `evaluation/gold-questions.json`. _Independent_ — pure authoring against the corpus. Track
H consumes these.

- [x] **G1** Add FACT questions Q1–Q5 to `gold-questions.json` following `IMPLEMENTATION_PLAN.md §7`
  schema (matching the existing DATA Q6–Q10 shape): `id`, `category: "FACT"`, `expected_route: "RAG"`,
  `question`, `required_keywords`, `required_authors`, `forbidden_patterns`. Each question must be
  answerable from ingested corpus text (Apollodorus / Hesiod / Homer / Hymns / Ovid) with a citable
  passage — e.g. the plan's "Why did Athena turn Arachne into a spider?" (Ovid). Pick `required_authors`
  from the 6 seeded `sources` slugs only.
  — Done, ids 1–5 added ahead of the existing DATA Q6–Q10.
- [x] **G2** Sanity-check each Q against the live corpus before committing (a quick retriever/`curl`
  probe once Track E is up, or a manual `narrative_chunks` `ILIKE` grep) so H isn't chasing questions
  the corpus can't answer — mirror the Stage 5 lesson that keyword shortfalls trace to data gaps, not
  pipeline bugs.
  — Done via direct `psql` word-boundary greps against the live 3,524-row `narrative_chunks` table.
  Found 3 of 5 questions' `required_keywords` used vocabulary absent from the actual seeded
  translations (Q3 "nobody"→"Noman", Q4 "Eris"/"discord" not present at all, Q5 "abduction" not
  present) — logged as **DEV-048**, keywords adjusted in the committed JSON. Q1/Q2 matched the plan
  verbatim. Not yet checked against a real synthesized answer (no RagAgent this session) — Track H
  must re-verify live.

---

## Track H — Verification (sequential, run last)

_Depends on:_ all tracks. Needs a live `.env` (`OPENAI_API_KEY` for embedding, `LLM_API_KEY` +
`LLM_CHAT_MODEL` for chat) and the DB at Flyway head with the full ingested corpus.

- [ ] **H1** `ContentRetrieverTest` green (ordering, cap, minScore, passage_ref dedupe, metadata).
- [ ] **H2** `RagQueryHandlerTest` green (structured citations, no prose parsing).
- [ ] **H3** `QueryServiceTest` green (RAG dispatch + router-fallback-to-real-RAG + handler-error).
- [ ] **H4** `EmbeddingConsistencyTest` green; boot the app and confirm the checker logs a **match** (no
  error) against the live corpus rows.
- [ ] **H5** **`EXPLAIN ANALYZE`** the retriever's cosine query against the live DB and confirm it uses
  `narrative_chunks_embedding_hnsw_idx` (the V8_4 halfvec expression index) — **not** a seq scan.
  Deliberately drop the `::halfvec(3072)` cast once and confirm it regresses to seq scan, proving the
  cast is load-bearing (DEV-028). (ADR-006 §5 / §10 check.)
- [ ] **H6** Boot with real `.env`; run **FACT Q1–Q5** live via `POST /api/v1/query`: each routes `RAG`,
  returns non-empty `citations` with real `author`/`work`/`passageRef`, `sqlGenerated: null`, no
  `forbidden_patterns` text, and clears its `required_keywords`/`required_authors`. Record any keyword
  shortfalls and root-cause them (corpus gap vs. minScore too high vs. pipeline) before calling done.
- [ ] **H7** Confirm the Track B DEBUG log fires for each H6 query (query text + retrieved
  `passage_ref`s + top score).
- [ ] **H8** Tune `minScore` if FACT scores are low (start 0.65; §7) and re-run H6; record the final
  value + rationale.
- [ ] **H9** Log any deviations in `DEVIATIONS.md` (new DEV-NNN), mark affected items above with
  `[DEVIATED - see DEVIATIONS.md #DEV-NNN]`, add the stage-note pointer to `IMPLEMENTATION_PLAN.md`, and
  flip the Stage 6 boxes in `TODO.md`.
