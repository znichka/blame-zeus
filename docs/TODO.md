# blame-zeus: Project TODO

Stages track `IMPLEMENTATION_PLAN.md §9`. Each stage's "done when" is the gate for starting the next.

---

## Stage 1a — Gradle project scaffold 
**Done when:** `./gradlew :core-api:compileKotlin` succeeds; module structure matches plan.

- [x] Root `settings.gradle.kts` — `rootProject.name`, `include("core-api", "telegram-bot")`, comment excluding `ingestion/`
- [x] Root `build.gradle.kts` — `plugins {}` block only; shared version declarations
- [x] `gradle.properties` — `kotlin.code.style`, `org.gradle.jvmargs`, `javaVersion=21`
- [x] `buildSrc/` convention plugin — apply `kotlin("jvm")`, `jvmTarget="21"`, `kotlin-reflect`, `jackson-module-kotlin`
- [x] `core-api/build.gradle.kts` — all compile + test dependencies (LangChain4j, Flyway, pgvector, springdoc, Testcontainers, springmockk)
- [x] `telegram-bot/build.gradle.kts` — placeholder (`spring-boot-starter-web` only; telegrambots commented out per DEV-007)
- [x] `CoreApiApplication.kt` — `@SpringBootApplication` main class
- [x] `application.yml` — datasource + Flyway + JPA + `app.llm` blocks with env-var placeholders; `statement_timeout = '3s'` Hikari init SQL

---

## Stage 1b — Local dev infrastructure
**Done when:** `docker-compose up -d` starts Postgres; `docker-compose exec postgres pg_isready` returns success.

- [x] `docker-compose.yml` — `pgvector/pgvector:pg16`, volume, init mount, healthcheck, port 5432
- [x] `docker/init/01_readonly_user.sql` — create `zeus_app`, grant CONNECT + USAGE + SELECT
- [x] `docker-compose.full.yml` — placeholder with `postgres` + `core-api` + `telegram-bot` services
- [x] `.env.example` — all vars with placeholder values (no real keys)
- [x] Confirm `.env` is in `.gitignore`

---

## Stage 1c — Database schema + foundation tests ✅
**Done when:** Flyway applies V1–V8; `FlywayMigrationTest` + `SchemaIntrospectorTest` pass against Testcontainers; `zeus_app` SELECT works, DROP is denied.

> ⚠️ Deviations occurred in this stage. See DEVIATIONS.md for details (DEV-008, DEV-009).

- [x] Flyway V1–V8 SQL files (extensions, sources, entities, relationships, myths, myth_participants, variant_claims, narrative_chunks)
- [x] `afterMigrate__grant_app_user.sql` Flyway callback
- [x] `application-test.yml` — `ddl-auto: validate`, `flyway.enabled: true`
- [x] Testcontainers base config — `PostgreSQLContainer` with `pgvector/pgvector:pg16`, `@DynamicPropertySource`
- [x] `FlywayMigrationTest.kt` — table presence + column verification for `variant_claims`, `narrative_chunks`, `sources`
- [x] `SchemaIntrospector.kt` — lazy-built schema prompt from `information_schema` `[DEVIATED - see DEVIATIONS.md DEV-023]` — tables auto-enumerated (no hardcoded list); emits types, FKs, CHECKs, `COMMENT ON` text (V8_3), and live `relation`/`claim_type` value vocabularies
- [x] `SchemaIntrospectorTest.kt` — prompt contains all tables + critical columns; parity test asserts every non-excluded public table appears `[DEVIATED - see DEVIATIONS.md DEV-023]`

→ [Detailed track-by-track checklist](TODO-stage1.md)

---

## Stage 2 — Ingestion Setup (Apollodorus only)
**Done when:** `python main.py` ingests Apollodorus .txt without error; rows appear in `narrative_chunks` with correct `source_id`, `passage_ref`, and non-null `embedding`.

> ⚠️ Stage order changed by ADR-004 (`docs/adr/adr-004-seed-data-extraction-strategy.md`): ingestion now runs before seed data, since the extraction pipeline needs real ingested corpus text to run against. This stage was formerly numbered Stage 3.

- [x] Python venv + `requirements.txt` (`openai>=1.0`, `psycopg2-binary`, `pgvector`, `tenacity>=8.2`, `python-dotenv`) `[DEVIATED - see DEVIATIONS.md #DEV-010]`
- [x] `pyproject.toml` (or keep `requirements.txt` only) — kept `requirements.txt`-only
- [x] `ingestion/config.py` — reads all env vars via `python-dotenv` (since ADR-006/DEV-015 also hard-requires `EMBEDDING_MODEL`; `embedding_pipeline.py` embeds with `config.EMBEDDING_MODEL`, no hardcoded literal)
- [x] `ingestion/loader/source_registry.py` — `SourceConfig` dataclass; Apollodorus entry only
      (`apollodorus_refs` extractor `[DEVIATED - see DEVIATIONS.md #DEV-011]`)
- [x] `ingestion/loader/text_cleaner.py` — footnote stripping, whitespace normalization, page-header removal
- [x] `ingestion/chunker/text_chunker.py` — sentence-split + accumulate to 1500 chars with 2-sentence overlap; `_nearest_ref` lookup `[DEVIATED - see DEVIATIONS.md #DEV-012]` — fixed an infinite loop and an unbounded chunk-size overshoot in the plan's literal loop
- [x] `ingestion/pipeline/embedding_pipeline.py` — `embed_batch` (batch=20, tenacity retry), `store_chunks`, `validate_source_ids`, `clear_source_chunks` `[DEVIATED - see DEVIATIONS.md #DEV-013, #DEV-024]` — dropped unnecessary `numpy` dep, added missing batching loop; re-runs skip already-embedded chunks *before* the OpenAI call and commit per batch (DEV-024)
- [x] `ingestion/main.py` — `load_dotenv()` first, then pipeline loop
- [x] Python tests: `test_text_cleaner.py`, `test_text_chunker.py`, `test_passage_ref_extractors.py`
- [x] Developer manually downloads Apollodorus (Frazer, 1921) from Theoi (`theoi.com/Text/Apollodorus{1,2,3}.html` + `ApollodorusE.html`), concatenates 4 pages preserving `[book.chapter.section]` markers → saves as `corpus/apollodorus_bibliotheca_frazer1921.txt`; QA'd — no HTML artifacts, 386 markers ascending, no seam duplication
- [x] Verify: `pytest ingestion/tests/` passes; `python main.py` populates `narrative_chunks` — 260 chunks for `apollodorus-bibliotheca`, all embedded, idempotent re-run confirmed `[DEVIATED - see DEVIATIONS.md #DEV-027]` — required a hand-inserted `sources` row (Stage 4's `V9` not written yet)

→ [Detailed track-by-track checklist](TODO-stage2.md)

---

## Stage 3 — Full Corpus
**Done when:** All 6 sources indexed in `narrative_chunks`; row count per source is non-zero.

> ⚠️ Formerly Stage 4 — renumbered per ADR-004 (see Stage 2 note above).

- [ ] Developer manually downloads remaining 5 corpus files (Hesiod Theogony, Homeric Hymns, Homer Iliad, Homer Odyssey, Ovid Metamorphoses) from Project Gutenberg / sacred-texts.com into `ingestion/corpus/`
- [ ] Add `SourceConfig` entries for Hesiod Theogony, Homeric Hymns, Homer Iliad, Homer Odyssey, Ovid Metamorphoses to `source_registry.py`
- [ ] Implement passage ref extractors for each new source (homer_refs, ovid_refs, hesiod_refs, hymn_refs)
- [ ] Add extractor tests for all new sources in `test_passage_ref_extractors.py`
- [x] Flyway `V15__add_embedding_model_tracking.sql` + add `embedding_model` to `store_chunks()`'s INSERT (ADR-006, deferred per DEV-015) — ideally rows are stamped at ingestion time, but `V15` numerically follows Stage 4's unwritten `V9`–`V14` (applying it first breaks Flyway's default in-order validation). Resolve at implementation time (renumber, out-of-order, or land with Stage 4 + backfill the ingested rows) and log a DEV entry `[DEVIATED - see DEVIATIONS.md #DEV-028]` — landed early, renumbered into `V8_4__switch_embedding_to_3large_3072.sql` alongside the ADR-013 embedding upgrade; `store_chunks()` stamps `embedding_model`; no backfill needed (table truncated + re-embedded)
- [ ] Run full ingestion; verify per-source row counts in DB

→ [Detailed track-by-track checklist](TODO-stage3.md) — includes two pre-identified gotchas:
the `sources` hand-insert repeat (DEV-027 pattern, plus the Ovid `year_published NOT NULL` plan bug)
and the `text_cleaner` all-caps stripping that would silently delete Homer/Ovid `BOOK`/story markers.

---

## Stage 4 — Seed Data (Extraction-Assisted)
**Done when:** `GET /api/v1/entities` returns ≥60 entities; `GET /api/v1/sources` returns 6 rows; `VariantClaimRepositoryTest` finds ≥2 conflict rows for Aphrodite.

> ⚠️ Formerly Stage 2 — renumbered and redesigned per ADR-004 (`docs/adr/adr-004-seed-data-extraction-strategy.md`). `entities`/`relationships` are now LLM-extracted from the ingested corpus (Stage 2–3) with a developer spot-check; `variant_claims` candidates require explicit per-row review before promotion to `trust_tier=1`. `sources`, `myths`/`myth_participants`, and `entity_aliases` remain hand-curated, unaffected by this change.
>
> ⚠️ Amended further by ADR-007 (DEV-014, DEV-018, DEV-019, DEV-020: open `claim_type` + shared `claim_type_aliases.json` normalization, store-all extraction, one canonical edge for contested relationships, normalize-on-promotion, extraction-preferred floor conflicts, unified `death` canonical) and ADR-008 (DEV-015: extraction runs on Claude Opus 4.8 via `instructor.from_anthropic`). Full detail in `TODO-stage4.md`.

- [ ] Build extraction pipeline (`ingestion/extraction/`): `schema.py` (models carry `passage_ref`, populated mechanically from the segment — DEV-021), `known_aliases.json`, `entity_resolver.py`, `claim_extractor.py`, `conflict_detector.py`, `run_extraction.py`; the claim-type normalization map is the `claim_type_aliases` **DB table** (V8_2), not a JSON file `[DEVIATED - see DEVIATIONS.md DEV-014, DEV-020, DEV-021, DEV-022]`
- [ ] Add `instructor`, `rapidfuzz`, `anthropic` to `ingestion/requirements.txt` `[DEVIATED - see DEVIATIONS.md DEV-015]`
- [ ] Tune extraction prompt against Apollodorus in `ingestion/notebooks/01_test_extraction.ipynb` before running the full corpus
- [ ] Run extraction against all 6 ingested sources → `entities_candidates.json`, `relationships_candidates.json`, `variant_claims_candidates.json`
- [ ] Extraction-quality metric (diagnostic, non-blocking): before any hand-add, log how many cross-source floor conflicts the raw candidates contain unaided (`N/2` — Aphrodite, Achilles; Io is single-source, structurally excluded) `[DEVIATED - see DEVIATIONS.md DEV-019]`
- [ ] Flyway V9 — seed sources (6 slugs with `year_published`, `role`) — hand-curated; Homeric Hymns `author` is `Anonymous ("Homeric")`, not Hesiod `[DEVIATED - see DEVIATIONS.md DEV-018]`
- [ ] Flyway V10 — seed entities (~60–100) — merge spot-checked candidates from `entities_candidates.json`
- [ ] Flyway V11 — seed relationships (parent_of, married_to, killed_by with source attribution + `passage_ref` per DEV-021) — merge spot-checked candidates from `relationships_candidates.json`; a contested relationship keeps exactly **one** canonical spine-preferred edge — the contradiction is recorded in V12 instead `[DEVIATED - see DEVIATIONS.md DEV-014, DEV-021]`
- [ ] Flyway V12 — seed variant_claims — review candidates in `ingestion/notebooks/02_verify_conflicts.ipynb`, promote approved rows to `trust_tier=1` **writing the normalized canonical `claim_type`** (per the `claim_type_aliases` table, DEV-022) and carrying each row's `passage_ref` (DEV-021) at insert; floor conflicts (Aphrodite parentage, Io parentage, Achilles death) are extraction-preferred — hand-add only the ones extraction missed, recording which path each took; Achilles death seeds under canonical `death`, never `slaying` `[DEVIATED - see DEVIATIONS.md DEV-018, DEV-019, DEV-020, DEV-021, DEV-022]`
- [ ] Flyway V13 — seed myths + myth_participants — hand-curated, unaffected
- [ ] Flyway V14 — create + seed entity_aliases (~20 cross-cultural aliases) — hand-curated, unaffected; may reuse `known_aliases.json` as a source list
- [ ] JPA `@Entity` classes: `Source`, `EntityRecord`, `Relationship`, `Myth`, `MythParticipant`, `VariantClaim`, `NarrativeChunk`, `EntityAlias`
- [ ] Spring Data JPA repositories for all entities
- [ ] DTOs: `QueryRequest`, `QueryResponse`, `Citation`, `ConflictEntry`, `RagResponse`
- [ ] `GET /api/v1/entities` and `GET /api/v1/sources` read endpoints in `QueryController`
- [ ] Tests: `SourceRepositoryTest`, `EntityRepositoryTest`, `VariantClaimRepositoryTest` (Testcontainers)

→ [Detailed track-by-track checklist](TODO-stage4.md)

---

## Stage 5 — SQL Pipeline
**Done when:** DATA gold questions (Q6–Q10) answer correctly via `POST /api/v1/query`; `SqlSafetyValidatorTest` + `SqlQueryHandlerTest` pass.

> ⚠️ Updated assumptions based on DEV-004 (see DEVIATIONS.md): LangChain4j is `1.0.0-beta5` (not 1.0.0 GA). Before implementing, verify current beta5 API shapes for `@AiService`, `@V` parameter injection, `@SystemMessage`/`@UserMessage`, and `QueryRouter`/`TextToSqlAgent` interface construction.
>
> ⚠️ Amended by ADR-008 (DEV-015): the chat beans are `AnthropicChatModel` (Claude Haiku 4.5, `LLM_CHAT_MODEL=claude-haiku-4-5-20251001`), not `OpenAiChatModel`; `LLM_API_KEY` holds an Anthropic key. Run the gold set before committing to the swap (swap-after-eval discipline, ADR-008 §5).

- [ ] Tests first: `SqlSafetyValidatorTest` (SELECT/WITH allowed; DROP/DELETE/INSERT/UPDATE/`;` blocked)
- [ ] Tests first: `SqlQueryHandlerTest` (mock `TextToSqlAgent`, assert validator called before JdbcTemplate)
- [ ] Tests first: `QueryRouterTest` — assert the router only ever emits `SQL`/`RAG`/`MIXED`, never `CONFLICT` `[DEVIATED - see DEVIATIONS.md DEV-014]`
- [ ] `RouteDecision.kt` enum (`SQL`, `RAG`, `MIXED` — **no `CONFLICT`**) `[DEVIATED - see DEVIATIONS.md DEV-014]`
- [ ] `QueryRouter.kt` `@AiService` interface (temperature 0.0, returns `RouteDecision`); prompt keeps schema-boundary → RAG, **omits** any "route to CONFLICT" instruction `[DEVIATED - see DEVIATIONS.md DEV-014]`
- [ ] `TextToSqlAgent.kt` `@AiService` interface with `@V("schema")` + `@V("question")` params
- [ ] `SqlSafetyValidator.kt` — deny-list enforcement
- [ ] `SqlQueryHandler.kt` — generates SQL → validates → executes → formats rows + extracts citations
- [ ] Empty-result fallback in `SqlQueryHandler` (ADR-005 §Decision.3): zero rows → fall back to RAG; also treat **aggregate-zero** as empty — a single row whose values are all `0`/`NULL` (`COUNT`=0, `SUM`=NULL), since aggregations never return zero rows `[DEVIATED - see DEVIATIONS.md DEV-026]`
- [ ] Add `langchain4j-anthropic-spring-boot-starter` to `core-api/build.gradle.kts` (keep `langchain4j-open-ai-spring-boot-starter` — the embedding bean needs it) `[DEVIATED - see DEVIATIONS.md DEV-015]`
- [ ] `LangChain4jConfig.kt` routing + synthesis model beans — `AnthropicChatModel`, temps 0.0/0.3, model name from `LLM_CHAT_MODEL` `[DEVIATED - see DEVIATIONS.md DEV-015]`
- [ ] `SchemaIntrospector.kt` — already built and made self-describing in Stage 1c (auto-enumerated tables, types/FKs/CHECKs/comments/value vocabularies) — Stage 5 only consumes it; lean on the V8_3 schema comments instead of hand-writing per-table prompt rules `[DEVIATED - see DEVIATIONS.md DEV-023]`
- [ ] `QueryService.kt` skeleton — routes SQL decision to `SqlQueryHandler`
- [ ] Log generated SQL at DEBUG level
- [ ] Wire `POST /api/v1/query` in `QueryController`

---

## Stage 6 — RAG Pipeline
**Done when:** FACT gold questions (Q1–Q5) return cited answers; `RagQueryHandlerTest` passes.

> ⚠️ Updated assumptions based on DEV-004 (see DEVIATIONS.md): LangChain4j is `1.0.0-beta5`. Before implementing, verify beta5 API shapes for `RagAgent @AiService`, `EmbeddingStore`, `ContentRetriever`, and `PgVectorEmbeddingStore` (including `createTable(false)` parameter shape).

- [ ] Tests first: `RagQueryHandlerTest` (mock `RagAgent`, assert `RagResponse.citations` returned without text parsing)
- [ ] `RagAgent.kt` `@AiService` interface — JSON structured return (`RagResponse`); system message includes the conflict-aware backstop instruction: if retrieved passages give different accounts of the same point from different sources, present each with its attribution rather than merging or picking one (ADR-007 §3) `[DEVIATED - see DEVIATIONS.md DEV-014]`
- [ ] `RagQueryHandler.kt`
- [ ] `LangChain4jConfig.kt` — `embeddingModel` bean only; **no `PgVectorEmbeddingStore`/`EmbeddingStoreContentRetriever` beans** — beta5's store hardcodes its own `embedding_id UUID`/`text` schema and cannot read `narrative_chunks(id, content, …)` (verified against the pinned jar). Instead: small custom `ContentRetriever` over `JdbcTemplate` (embed query → `ORDER BY embedding::halfvec(3072) <=> (?::vector(3072))::halfvec(3072) LIMIT 5` — the halfvec cast is REQUIRED to hit V8_4's expression index, a plain `embedding <=> ?` silently seq-scans (updated based on DEV-028, see DEVIATIONS.md); minScore=0.65 filter, returning `source_id`/`passage_ref` for citations); drop `langchain4j-pgvector` from `build.gradle.kts`. Embedding model name injected from `app.llm.embedding-model` (`EMBEDDING_MODEL` env var, now `text-embedding-3-large` per ADR-013), not hardcoded (ADR-006, deferred per DEV-015) `[DEVIATED - see DEVIATIONS.md DEV-025]`
- [ ] `EmbeddingConsistencyChecker.kt` — `ApplicationReadyEvent` check that the configured embedding model matches what the corpus rows were embedded with (the `narrative_chunks.embedding_model` column exists since V8_4/DEV-028 — compares against `text-embedding-3-large`); logs errors, never blocks startup (ADR-006, deferred per DEV-015)
- [ ] `canary-aphrodite.json` golden-vector fixture (generated once via the Python pipeline, with `EMBEDDING_MODEL=text-embedding-3-large` per DEV-028) + `EmbeddingConsistencyTest.kt` (ADR-006, deferred per DEV-015)
- [ ] `EXPLAIN ANALYZE` index-usage check on the HNSW retrieval query, once ingested data exists — must show `narrative_chunks_embedding_hnsw_idx` (the V8_4 halfvec expression index), which only matches the cast form of the query (ADR-006 §10 addition, deferred per DEV-015; updated based on DEV-028)
- [ ] Add RAG route to `QueryService`
- [ ] Router fallback: catches router exceptions, defaults to RAG

---

## Stage 7 — Conflict Enrichment (router-independent)
**Done when:** the Aphrodite question returns ≥2 attributed versions in `conflicts[]` **even though it routes to SQL/RAG, not a CONFLICT route**; `ConflictLookupTest` + enrichment test pass.

> ⚠️ Recast by ADR-007 (`[DEVIATED - see DEVIATIONS.md DEV-014]`): there is **no `CONFLICT` route and no `ConflictQueryHandler`**. Conflict surfacing is a router-independent enrichment step in `QueryService`, invoked after *any* answer, that writes only `conflicts[]` (never `answer`) and is wrapped so it can never break the primary answer.
>
> ⚠️ Updated assumptions based on DEV-004 (see DEVIATIONS.md): LangChain4j is `1.0.0-beta5`. Before implementing, verify beta5 API shapes for `EntityExtractor`/`ConflictProbe @AiService` (temperature 0.0) and `ConflictSynthesizer @AiService` (temperature 0.3) — annotation and parameter injection shapes may differ from 1.0.0 GA.

- [ ] Tests first: `ConflictLookupTest` (all matching `variant_claims` rows returned for a subject + normalized `claim_type`; unknown entity / empty result handled gracefully) `[DEVIATED - see DEVIATIONS.md DEV-014]`
- [ ] Tests first: `QueryService` enrichment test — a conflict-shaped question routed to SQL/RAG still yields a populated `conflicts[]`; a claim-type mismatch (e.g. appearance question on a subject with a stored death conflict) yields empty `conflicts[]`; enrichment failure leaves the primary answer intact `[DEVIATED - see DEVIATIONS.md DEV-014]`
- [ ] `EntityExtractor.kt` `@AiService` interface (temperature 0.0)
- [ ] `ConflictProbe.kt` `@AiService` interface (temperature 0.0) → `{subject, claimType}` (may be folded into `EntityExtractor`); returns empty/`none` `claimType` when the question maps to no modeled attribute `[DEVIATED - see DEVIATIONS.md DEV-014]`
- [ ] `ConflictSynthesizer.kt` `@AiService` interface (temperature 0.3) — reused unchanged to format fetched versions
- [ ] `ConflictLookup.kt` (shared component, **not** an `@AiService`) — three-step entity resolution (exact → alias → trigram), then two fetches over that resolution: (a) a **claim-type-filtered** fetch for enrichment (`subject_entity_id = ? AND claim_type = normalize(probeClaimType)`, using `idx_variant_claims_subject_type`), and (b) a **subject-only** fetch (all `claim_type`s for the entity) backing the `/conflicts/{entityName}` endpoint; reads the shared `claim_type_aliases` DB table (V8_2) for `normalize()` — same rows the offline detector reads; never a code-side copy of the map `[DEVIATED - see DEVIATIONS.md DEV-014, DEV-022]`
- [ ] `QueryService` enrichment step — after `dispatch(route)`, skip on `serviceError`, else `conflictProbe.extract` → `conflictLookup.find` → `conflictSynthesizer.synthesize`; write only `conflicts[]`, wrapped in try/catch so it never breaks the primary answer `[DEVIATED - see DEVIATIONS.md DEV-014]`
- [ ] `GET /api/v1/conflicts/{entityName}` endpoint — backed by `ConflictLookup`'s **subject-only** fetch (no claim-type context at the URL), not a handler; returns all stored `variant_claims` for the entity across claim_types `[DEVIATED - see DEVIATIONS.md DEV-014]`

---

## Stage 8 — Mixed Pipeline
**Done when:** MIXED gold questions (Q11–Q12) return both SQL rows and narrative answer; `MixedQueryHandlerTest` passes.

> ⚠️ Updated assumptions based on DEV-004 (see DEVIATIONS.md): LangChain4j is `1.0.0-beta5`. `MixedQueryHandler` calls `ragAgent.answer(augmented)` — confirm the `RagAgent @AiService` interface verified in Stage 6 is unchanged before building on it.

- [ ] Tests first: `MixedQueryHandlerTest` (SQL results injected into augmented question before RAG call)
- [ ] `MixedQueryHandler.kt` — SQL filter → inject results as context → `ragAgent.answer(augmented)`
- [ ] Add MIXED route to `QueryService`
- [ ] `QueryService` inner try-catch: handler failures return `serviceError=true` response

---

## Stage 9 — Web UI
**Done when:** Manual smoke test of all 17 gold questions in browser passes; route badge + citations render correctly.

> ⚠️ Updated based on DEV-009 (see DEVIATIONS.md): springdoc-openapi is `2.6.0` (not `2.8.3` — DEV-006 picked a version requiring Spring Boot 3.4.x, which broke `@SpringBootTest` context loading under Spring Boot 3.3.13). `OpenApiConfig.kt` should target `2.6.0`'s API surface; `@Operation`/`@Tag` usage is unaffected.

- [ ] `WebController.kt` — `GET /` + `POST /web/query`
- [ ] `templates/index.html` — form, route badge (color-coded), answer block, citations footnotes, conflicts section, collapsible SQL block, error banner for `serviceError`
- [ ] Tailwind CSS via CDN (no build step)
- [ ] `OpenApiConfig.kt` — Springdoc customization
- [ ] `QueryControllerIntegrationTest` — HTTP 200; `routeDecision` present (`SQL`/`RAG`/`MIXED`); a conflict-shaped question populates `conflicts[]` via enrichment regardless of route `[DEVIATED - see DEVIATIONS.md DEV-014]`
- [ ] Smoke test: Swagger UI loads at `/swagger-ui.html`

---

## Stage 10 — Evaluation
**Done when:** `EvaluationRunner` reports ≥75% on all 17 gold questions (≥13/17 at full score).

- [ ] Complete `evaluation/gold-questions.json` — all 17 questions with `required_keywords`, `required_authors`, `forbidden_patterns`, REFUSAL `refusal_criteria`. Re-point conflict questions Q13–15 `expected_route` (parentage → SQL, death → RAG); **no question uses `CONFLICT` as an `expected_route`** (it survives only as a `category`) `[DEVIATED - see DEVIATIONS.md DEV-014]`
- [ ] `EvaluationRunner` (standalone `fun main()` or JUnit integration test)
- [ ] Score logic: route match (1pt), author/conflict check (1pt), content check (1pt). For CONFLICT-category questions the conflict check keys on `conflicts[]` (≥2 distinct `claimValue`), **independent of the route** — not a `CONFLICT` route match `[DEVIATED - see DEVIATIONS.md DEV-014]`
- [ ] REFUSAL scoring: `refusal_criteria` pass + no `forbidden_patterns`
- [ ] Q9 guard: assert `sqlGenerated != null` before checking `WITH RECURSIVE`
- [ ] Q10 guard: execute generated SQL against test DB, assert `rowCount >= 12`
- [ ] Q14 guard: skip per-author check when `required_authors.size < 2`
- [ ] Tune `minScore` in `contentRetriever` if FACT scores are low
- [ ] Run full evaluation; fix any failing questions

---

## Stage 11 — Telegram Bot (Phase 2, optional)
**Done when:** Bot answers questions in Telegram chat; `/start` command works.

> ⚠️ Updated assumptions based on DEV-007 (see DEVIATIONS.md): `telegrambots-spring-boot-starter` is currently commented out in `telegram-bot/build.gradle.kts`. Verify correct artifact coordinates before adding (likely `org.telegram:telegrambots-spring-boot-starter:6.9.7`).

- [ ] `telegram-bot/build.gradle.kts` — add `telegrambots-spring-boot-starter:6.9.x` (verify coordinates first) + `spring-boot-starter-web` `[DEVIATED - see DEVIATIONS.md DEV-007]`
- [ ] `BlamezeusBot` extending `TelegramLongPollingBot`
- [ ] `CoreApiClient` — `RestClient` calling `POST /api/v1/query`
- [ ] `TelegramResponseFormatter` — MarkdownV2 formatting, message splitting at >4096 chars
- [ ] `docker-compose.full.yml` — add `telegram-bot` service with `depends_on: core-api: condition: service_healthy`
- [ ] Add `TELEGRAM_BOT_TOKEN` + `TELEGRAM_BOT_USERNAME` + `CORE_API_BASE_URL` to `.env.example`
