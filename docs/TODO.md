# blame-zeus: Project TODO

Stages track `IMPLEMENTATION_PLAN.md §9`. Each stage's "done when" is the gate for starting the next.

---

## Stage 1a — Gradle project scaffold 
**Done when:** `./gradlew :core-api:compileKotlin` succeeds; module structure matches plan.

- [ ] Root `settings.gradle.kts` — `rootProject.name`, `include("core-api", "telegram-bot")`, comment excluding `ingestion/`
- [ ] Root `build.gradle.kts` — `plugins {}` block only; shared version declarations
- [ ] `gradle.properties` — `kotlin.code.style`, `org.gradle.jvmargs`, `javaVersion=21`
- [ ] `buildSrc/` convention plugin — apply `kotlin("jvm")`, `jvmTarget="21"`, `kotlin-reflect`, `jackson-module-kotlin`
- [ ] `core-api/build.gradle.kts` — all compile + test dependencies (LangChain4j, Flyway, pgvector, springdoc, Testcontainers, springmockk)
- [ ] `telegram-bot/build.gradle.kts` — placeholder (`spring-boot-starter-web`, `telegrambots-spring-boot-starter`; no production code)
- [ ] `CoreApiApplication.kt` — `@SpringBootApplication` main class
- [ ] `application.yml` — datasource + Flyway + JPA + `app.llm` blocks with env-var placeholders; `statement_timeout = '3s'` Hikari init SQL

---

## Stage 1b — Local dev infrastructure
**Done when:** `docker-compose up -d` starts Postgres; `docker-compose exec postgres pg_isready` returns success.

- [ ] `docker-compose.yml` — `pgvector/pgvector:pg16`, volume, init mount, healthcheck, port 5432
- [ ] `docker/init/01_readonly_user.sql` — create `zeus_app`, grant CONNECT + USAGE + SELECT
- [ ] `docker-compose.full.yml` — placeholder with `postgres` + `core-api` + `telegram-bot` services
- [ ] `.env.example` — all vars with placeholder values (no real keys)
- [ ] Confirm `.env` is in `.gitignore`

---

## Stage 1c — Database schema + foundation tests
**Done when:** Flyway applies V1–V8; `FlywayMigrationTest` + `SchemaIntrospectorTest` pass against Testcontainers; `zeus_app` SELECT works, DROP is denied.

- [ ] Flyway V1–V8 SQL files (extensions, sources, entities, relationships, myths, myth_participants, variant_claims, narrative_chunks)
- [ ] `afterMigrate__grant_app_user.sql` Flyway callback
- [ ] `application-test.yml` — `ddl-auto: validate`, `flyway.enabled: true`
- [ ] Testcontainers base config — `PostgreSQLContainer` with `pgvector/pgvector:pg16`, `@DynamicPropertySource`
- [ ] `FlywayMigrationTest.kt` — table presence + column verification for `variant_claims`, `narrative_chunks`, `sources`
- [ ] `SchemaIntrospector.kt` — lazy-built schema prompt from `information_schema`
- [ ] `SchemaIntrospectorTest.kt` — prompt contains all tables + critical columns

→ [Detailed track-by-track checklist](TODO-stage1.md)

---

## Stage 2 — Seed Data
**Done when:** `GET /api/v1/entities` returns ≥60 entities; `GET /api/v1/sources` returns 6 rows; `VariantClaimRepositoryTest` finds ≥2 conflict rows for Aphrodite.

- [ ] Flyway V9 — seed sources (6 slugs with `year_published`, `role`)
- [ ] Flyway V10 — seed entities (~60–100: primordials, titans, olympians, heroes, monsters)
- [ ] Flyway V11 — seed relationships (parent_of, married_to, killed_by with source attribution)
- [ ] Flyway V12 — seed variant_claims (Aphrodite parentage, Io parentage, Achilles death)
- [ ] Flyway V13 — seed myths + myth_participants
- [ ] Flyway V14 — create + seed entity_aliases (~20 cross-cultural aliases)
- [ ] JPA `@Entity` classes: `Source`, `Entity_`, `Relationship`, `Myth`, `MythParticipant`, `VariantClaim`, `NarrativeChunk`, `EntityAlias`
- [ ] Spring Data JPA repositories for all entities
- [ ] DTOs: `QueryRequest`, `QueryResponse`, `Citation`, `ConflictEntry`, `RagResponse`
- [ ] `GET /api/v1/entities` and `GET /api/v1/sources` read endpoints in `QueryController`
- [ ] Tests: `SourceRepositoryTest`, `EntityRepositoryTest`, `VariantClaimRepositoryTest` (Testcontainers)

---

## Stage 3 — Ingestion Setup (Apollodorus only)
**Done when:** `python main.py` ingests Apollodorus .txt without error; rows appear in `narrative_chunks` with correct `source_id`, `passage_ref`, and non-null `embedding`.

- [ ] Python venv + `requirements.txt` (`openai>=1.0`, `psycopg2-binary`, `pgvector`, `tenacity>=8.2`, `python-dotenv`)
- [ ] `pyproject.toml` (or keep `requirements.txt` only)
- [ ] `ingestion/config.py` — reads all env vars via `python-dotenv`
- [ ] `ingestion/loader/source_registry.py` — `SourceConfig` dataclass; Apollodorus entry only
- [ ] `ingestion/loader/text_cleaner.py` — footnote stripping, whitespace normalization, page-header removal
- [ ] `ingestion/chunker/text_chunker.py` — sentence-split + accumulate to 1500 chars with 2-sentence overlap; `_nearest_ref` lookup
- [ ] `ingestion/pipeline/embedding_pipeline.py` — `embed_batch` (batch=20, tenacity retry), `store_chunks`, `validate_source_ids`, `clear_source_chunks`
- [ ] `ingestion/main.py` — `load_dotenv()` first, then pipeline loop
- [ ] Python tests: `test_text_cleaner.py`, `test_text_chunker.py`, `test_passage_ref_extractors.py`
- [ ] Download 
plaintext → `corpus/apollodorus_bibliotheca_frazer1921.txt`
- [ ] Verify: `pytest ingestion/tests/` passes; `python main.py` populates `narrative_chunks`

---

## Stage 4 — Full Corpus
**Done when:** All 6 sources indexed in `narrative_chunks`; row count per source is non-zero.

- [ ] Download remaining 5 corpus files into `ingestion/corpus/`
- [ ] Add `SourceConfig` entries for Hesiod Theogony, Homeric Hymns, Homer Iliad, Homer Odyssey, Ovid Metamorphoses to `source_registry.py`
- [ ] Implement passage ref extractors for each new source (homer_refs, ovid_refs, hesiod_refs, hymn_refs)
- [ ] Add extractor tests for all new sources in `test_passage_ref_extractors.py`
- [ ] Run full ingestion; verify per-source row counts in DB

---

## Stage 5 — SQL Pipeline
**Done when:** DATA gold questions (Q6–Q10) answer correctly via `POST /api/v1/query`; `SqlSafetyValidatorTest` + `SqlQueryHandlerTest` pass.

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

- [ ] Tests first: `RagQueryHandlerTest` (mock `RagAgent`, assert `RagResponse.citations` returned without text parsing)
- [ ] `RagAgent.kt` `@AiService` interface — JSON structured return (`RagResponse`)
- [ ] `RagQueryHandler.kt`
- [ ] `LangChain4jConfig.kt` — `embeddingModel`, `embeddingStore` (`createTable(false)`), `contentRetriever` (maxResults=5, minScore=0.65) beans
- [ ] Add RAG route to `QueryService`
- [ ] Router fallback: catches router exceptions, defaults to RAG

---

## Stage 7 — Conflict Pipeline
**Done when:** Aphrodite question returns ≥2 attributed versions; `ConflictQueryHandlerTest` passes.

- [ ] Tests first: `ConflictQueryHandlerTest` (all variant_claims rows passed to synthesizer; unknown entity returns graceful answer)
- [ ] `EntityExtractor.kt` `@AiService` interface (temperature 0.0)
- [ ] `ConflictSynthesizer.kt` `@AiService` interface (temperature 0.3)
- [ ] `ConflictQueryHandler.kt` — three-step name resolution (exact → alias → trigram); empty result graceful response
- [ ] `GET /api/v1/conflicts/{entityName}` endpoint
- [ ] Add CONFLICT route to `QueryService`

---

## Stage 8 — Mixed Pipeline
**Done when:** MIXED gold questions (Q11–Q12) return both SQL rows and narrative answer; `MixedQueryHandlerTest` passes.

- [ ] Tests first: `MixedQueryHandlerTest` (SQL results injected into augmented question before RAG call)
- [ ] `MixedQueryHandler.kt` — SQL filter → inject results as context → `ragAgent.answer(augmented)`
- [ ] Add MIXED route to `QueryService`
- [ ] `QueryService` inner try-catch: handler failures return `serviceError=true` response

---

## Stage 9 — Web UI
**Done when:** Manual smoke test of all 17 gold questions in browser passes; route badge + citations render correctly.

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

- [ ] `telegram-bot/build.gradle.kts` — `telegrambots-spring-boot-starter:6.9.x` + `spring-boot-starter-web`
- [ ] `BlamezeusBot` extending `TelegramLongPollingBot`
- [ ] `CoreApiClient` — `RestClient` calling `POST /api/v1/query`
- [ ] `TelegramResponseFormatter` — MarkdownV2 formatting, message splitting at >4096 chars
- [ ] `docker-compose.full.yml` — add `telegram-bot` service with `depends_on: core-api: condition: service_healthy`
- [ ] Add `TELEGRAM_BOT_TOKEN` + `TELEGRAM_BOT_USERNAME` + `CORE_API_BASE_URL` to `.env.example`
