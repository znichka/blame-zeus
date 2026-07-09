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
- [x] `SchemaIntrospector.kt` — lazy-built schema prompt from `information_schema`
- [x] `SchemaIntrospectorTest.kt` — prompt contains all tables + critical columns

→ [Detailed track-by-track checklist](TODO-stage1.md)

---

## Stage 2 — Ingestion Setup (Apollodorus only)
**Done when:** `python main.py` ingests Apollodorus .txt without error; rows appear in `narrative_chunks` with correct `source_id`, `passage_ref`, and non-null `embedding`.

> ⚠️ Stage order changed by ADR-004 (`docs/adr/adr-004-seed-data-extraction-strategy.md`): ingestion now runs before seed data, since the extraction pipeline needs real ingested corpus text to run against. This stage was formerly numbered Stage 3.

- [x] Python venv + `requirements.txt` (`openai>=1.0`, `psycopg2-binary`, `pgvector`, `tenacity>=8.2`, `python-dotenv`) `[DEVIATED - see DEVIATIONS.md #DEV-010]`
- [x] `pyproject.toml` (or keep `requirements.txt` only) — kept `requirements.txt`-only
- [x] `ingestion/config.py` — reads all env vars via `python-dotenv`
- [ ] `ingestion/loader/source_registry.py` — `SourceConfig` dataclass; Apollodorus entry only
      (`apollodorus_refs` extractor done `[DEVIATED - see DEVIATIONS.md #DEV-011]`; `SourceConfig`/`SOURCE_REGISTRY` still pending)
- [x] `ingestion/loader/text_cleaner.py` — footnote stripping, whitespace normalization, page-header removal
- [ ] `ingestion/chunker/text_chunker.py` — sentence-split + accumulate to 1500 chars with 2-sentence overlap; `_nearest_ref` lookup
- [ ] `ingestion/pipeline/embedding_pipeline.py` — `embed_batch` (batch=20, tenacity retry), `store_chunks`, `validate_source_ids`, `clear_source_chunks`
- [ ] `ingestion/main.py` — `load_dotenv()` first, then pipeline loop
- [ ] Python tests: `test_text_cleaner.py`, `test_text_chunker.py`, `test_passage_ref_extractors.py`
- [x] Developer manually downloads Apollodorus (Frazer, 1921) from Theoi (`theoi.com/Text/Apollodorus{1,2,3}.html` + `ApollodorusE.html`), concatenates 4 pages preserving `[book.chapter.section]` markers → saves as `corpus/apollodorus_bibliotheca_frazer1921.txt`; QA'd — no HTML artifacts, 386 markers ascending, no seam duplication
- [ ] Verify: `pytest ingestion/tests/` passes; `python main.py` populates `narrative_chunks`

→ [Detailed track-by-track checklist](TODO-stage2.md)

---

## Stage 3 — Full Corpus
**Done when:** All 6 sources indexed in `narrative_chunks`; row count per source is non-zero.

> ⚠️ Formerly Stage 4 — renumbered per ADR-004 (see Stage 2 note above).

- [ ] Developer manually downloads remaining 5 corpus files (Hesiod Theogony, Homeric Hymns, Homer Iliad, Homer Odyssey, Ovid Metamorphoses) from Project Gutenberg / sacred-texts.com into `ingestion/corpus/`
- [ ] Add `SourceConfig` entries for Hesiod Theogony, Homeric Hymns, Homer Iliad, Homer Odyssey, Ovid Metamorphoses to `source_registry.py`
- [ ] Implement passage ref extractors for each new source (homer_refs, ovid_refs, hesiod_refs, hymn_refs)
- [ ] Add extractor tests for all new sources in `test_passage_ref_extractors.py`
- [ ] Run full ingestion; verify per-source row counts in DB

---

## Stage 4 — Seed Data (Extraction-Assisted)
**Done when:** `GET /api/v1/entities` returns ≥60 entities; `GET /api/v1/sources` returns 6 rows; `VariantClaimRepositoryTest` finds ≥2 conflict rows for Aphrodite.

> ⚠️ Formerly Stage 2 — renumbered and redesigned per ADR-004 (`docs/adr/adr-004-seed-data-extraction-strategy.md`). `entities`/`relationships` are now LLM-extracted from the ingested corpus (Stage 2–3) with a developer spot-check; `variant_claims` candidates require explicit per-row review before promotion to `trust_tier=1`. `sources`, `myths`/`myth_participants`, and `entity_aliases` remain hand-curated, unaffected by this change.

- [ ] Build extraction pipeline (`ingestion/extraction/`): `schema.py`, `known_aliases.json`, `entity_resolver.py`, `claim_extractor.py`, `conflict_detector.py`, `run_extraction.py`
- [ ] Add `instructor`, `rapidfuzz` to `ingestion/requirements.txt`
- [ ] Tune extraction prompt against Apollodorus in `ingestion/notebooks/01_test_extraction.ipynb` before running the full corpus
- [ ] Run extraction against all 6 ingested sources → `entities_candidates.json`, `relationships_candidates.json`, `variant_claims_candidates.json`
- [ ] Flyway V9 — seed sources (6 slugs with `year_published`, `role`) — hand-curated, unaffected
- [ ] Flyway V10 — seed entities (~60–100) — merge spot-checked candidates from `entities_candidates.json`
- [ ] Flyway V11 — seed relationships (parent_of, married_to, killed_by with source attribution) — merge spot-checked candidates from `relationships_candidates.json`
- [ ] Flyway V12 — seed variant_claims — review candidates in `ingestion/notebooks/02_verify_conflicts.ipynb`, promote approved rows to `trust_tier=1`; confirm minimum coverage (Aphrodite parentage, Io parentage, Achilles death) is present, hand-add any the pipeline missed
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

- [ ] Tests first: `SqlSafetyValidatorTest` (SELECT/WITH allowed; DROP/DELETE/INSERT/UPDATE/`;` blocked)
- [ ] Tests first: `SqlQueryHandlerTest` (mock `TextToSqlAgent`, assert validator called before JdbcTemplate)
- [ ] `RouteDecision.kt` enum (SQL, RAG, MIXED, CONFLICT)
- [ ] `QueryRouter.kt` `@AiService` interface (temperature 0.0, returns `RouteDecision`)
- [ ] `TextToSqlAgent.kt` `@AiService` interface with `@V("schema")` + `@V("question")` params
- [ ] `SqlSafetyValidator.kt` — deny-list enforcement
- [ ] `SqlQueryHandler.kt` — generates SQL → validates → executes → formats rows + extracts citations
- [ ] `LangChain4jConfig.kt` routing + synthesis model beans
- [ ] `SchemaIntrospector.kt` — lazy-built schema prompt from `information_schema`
- [ ] `QueryService.kt` skeleton — routes SQL decision to `SqlQueryHandler`
- [ ] Log generated SQL at DEBUG level
- [ ] Wire `POST /api/v1/query` in `QueryController`

---

## Stage 6 — RAG Pipeline
**Done when:** FACT gold questions (Q1–Q5) return cited answers; `RagQueryHandlerTest` passes.

> ⚠️ Updated assumptions based on DEV-004 (see DEVIATIONS.md): LangChain4j is `1.0.0-beta5`. Before implementing, verify beta5 API shapes for `RagAgent @AiService`, `EmbeddingStore`, `ContentRetriever`, and `PgVectorEmbeddingStore` (including `createTable(false)` parameter shape).

- [ ] Tests first: `RagQueryHandlerTest` (mock `RagAgent`, assert `RagResponse.citations` returned without text parsing)
- [ ] `RagAgent.kt` `@AiService` interface — JSON structured return (`RagResponse`)
- [ ] `RagQueryHandler.kt`
- [ ] `LangChain4jConfig.kt` — `embeddingModel`, `embeddingStore` (`createTable(false)`), `contentRetriever` (maxResults=5, minScore=0.65) beans
- [ ] Add RAG route to `QueryService`
- [ ] Router fallback: catches router exceptions, defaults to RAG

---

## Stage 7 — Conflict Pipeline
**Done when:** Aphrodite question returns ≥2 attributed versions; `ConflictQueryHandlerTest` passes.

> ⚠️ Updated assumptions based on DEV-004 (see DEVIATIONS.md): LangChain4j is `1.0.0-beta5`. Before implementing, verify beta5 API shapes for `EntityExtractor @AiService` (temperature 0.0) and `ConflictSynthesizer @AiService` (temperature 0.3) — annotation and parameter injection shapes may differ from 1.0.0 GA.

- [ ] Tests first: `ConflictQueryHandlerTest` (all variant_claims rows passed to synthesizer; unknown entity returns graceful answer)
- [ ] `EntityExtractor.kt` `@AiService` interface (temperature 0.0)
- [ ] `ConflictSynthesizer.kt` `@AiService` interface (temperature 0.3)
- [ ] `ConflictQueryHandler.kt` — three-step name resolution (exact → alias → trigram); empty result graceful response
- [ ] `GET /api/v1/conflicts/{entityName}` endpoint
- [ ] Add CONFLICT route to `QueryService`

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
- [ ] `QueryControllerIntegrationTest` — HTTP 200; `routeDecision` present; CONFLICT populates `conflicts`
- [ ] Smoke test: Swagger UI loads at `/swagger-ui.html`

---

## Stage 10 — Evaluation
**Done when:** `EvaluationRunner` reports ≥75% on all 17 gold questions (≥13/17 at full score).

- [ ] Complete `evaluation/gold-questions.json` — all 17 questions with `required_keywords`, `required_authors`, `forbidden_patterns`, REFUSAL `refusal_criteria`
- [ ] `EvaluationRunner` (standalone `fun main()` or JUnit integration test)
- [ ] Score logic: route match (1pt), author/conflict check (1pt), content check (1pt)
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
