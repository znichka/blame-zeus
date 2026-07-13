# blame-zeus: Tech Stack Guardrails

Rules for keeping this PoC consistent, safe, and easy to reason about. These are constraints, not suggestions.

---

## Language & Runtime

| Rule | Detail |
|---|---|
| **Kotlin 2.3.21 + JVM 21** | `core-api` and `telegram-bot` modules. No Java source files. |
| **Spring Boot 3.3.13** | Jakarta namespace (`jakarta.*`), not `javax.*`. |
| **Gradle Kotlin DSL** | All JVM build files are `build.gradle.kts`. No Groovy `.gradle` files. |
| **Shared convention plugin** | `buildSrc/src/main/kotlin/blame-zeus.kotlin-conventions.gradle.kts` — applies `kotlin("jvm")`, sets `jvmTarget = "21"`, adds `kotlin-reflect` + `jackson-module-kotlin` to all JVM modules. |
| **Python 3.12+ for ingestion** | The `ingestion/` directory is a standalone Python project. No JVM, no Spring, no Gradle. Managed with `uv` (or `pip` + `venv`). Not part of the Gradle build. |

---

## LLM & AI

| Rule | Detail |
|---|---|
| **LangChain4j for all LLM calls in JVM services** | Applies to `core-api` and `telegram-bot` only. No direct Anthropic SDK, no direct OpenAI Java SDK (`com.openai:openai-java`), no plain `RestTemplate`/`WebClient` to LLM endpoints. The `ingestion` Python job is the only authorized exception — it uses provider Python SDKs directly for corpus-prep: the OpenAI SDK for **embedding**, and the Anthropic SDK (since ADR-004; model updated by ADR-008) for offline **seed-data extraction** (`ingestion/extraction/`, via `instructor` on a separate `anthropic` client — Claude Opus 4.8 — not the `openai` embedding client, and not a separate LLM framework). Both uses are corpus-prep tooling; extraction never runs at query time and never touches `LangChain4jConfig.kt`. |
| **`@AiService` interface pattern** | Every LLM role (routing, SQL generation, RAG synthesis, conflict synthesis, entity extraction) is an interface annotated with `@AiService`. No inline `ChatLanguageModel.generate()` calls in business logic. |
| **Chat model is provider-agnostic; embedding model is OpenAI-fixed** | All `@AiService` interfaces and handlers are provider-neutral — no chat provider is assumed or hardcoded outside `LangChain4jConfig.kt`. `LangChain4jConfig.kt` uses `AnthropicChatModel` (Claude Haiku 4.5) as the Phase 1 default since ADR-008; to change the chat provider, replace those beans with another LangChain4j `ChatLanguageModel` implementation and add the new provider's starter. Keep `langchain4j-open-ai-spring-boot-starter` regardless — the embedding bean always requires it. In ingestion, the OpenAI Python SDK is used directly for embedding only and is intentionally fixed: the embedding model (`text-embedding-3-large`, dimension 3072, since ADR-013) must match what was used during ingestion and cannot be swapped without re-ingesting the full corpus. |
| **No hardcoded API keys or model names** | All in `application.yml` backed by environment variables. Non-secret values (e.g. model names) may use an `${ENV_VAR:default}` form; the default is acceptable, but the property must live in `application.yml` — not as a string literal inside a `@Bean` method. |
| **Temperature discipline** | Routing and SQL generation: `0.0`. Synthesis (RAG, conflict): `0.3`. Use separate `@Qualifier` beans if you need both in the same app. |
| **AI Service interfaces are mockable** | Interfaces only — no concrete classes. Mock with `mockk<T>()` in unit tests and `@MockkBean` (springmockk) in Spring-context tests. Never wire a real `ChatLanguageModel` in the test profile. |
| **Log generated SQL** | Every SQL string produced by `TextToSqlAgent` must be logged at `DEBUG` level before execution. |

---

## SQL Safety

| Rule | Detail |
|---|---|
| **Validate before execute** | All LLM-generated SQL must pass through `SqlSafetyValidator` before `JdbcTemplate` execution. |
| **Read-only only** | SQL must begin with `SELECT` or `WITH`. Deny-list: `DROP`, `DELETE`, `INSERT`, `UPDATE`, `CREATE`, `ALTER`, `TRUNCATE`, `EXEC`, `EXECUTE`, `--`, `;`. |
| **Never use `execute()` for LLM SQL** | Use `JdbcTemplate.queryForList()` — read-only by contract. |
| **Read-only runtime DB user** | The Spring Boot runtime datasource connects as `zeus_app`, a restricted user with `SELECT` only on application tables. Created by `docker-entrypoint-initdb.d/01_readonly_user.sql`. Flyway uses the superuser credentials in a separate `spring.flyway.*` block. Two credential pairs in `application.yml` and `.env.example`. |
| **Query timeout** | `spring.datasource.hikari.connection-init-sql: "SET statement_timeout = '3s'"`. Applies to every Hikari-managed connection, capping LLM-generated SQL at 3 seconds and preventing runaway recursive CTEs from exhausting the connection pool. |

---

## Database

| Rule | Detail |
|---|---|
| **Flyway owns all DDL** | `spring.jpa.hibernate.ddl-auto: validate` in all profiles. Never `create`, `create-drop`, or `update` — Testcontainers destroys the container after tests, so Flyway running on startup against the fresh container handles all DDL without Hibernate needing to drop anything. |
| **No raw DDL at runtime** | No `CREATE TABLE` / `ALTER TABLE` anywhere in application code. All schema changes go through a new Flyway migration file. |
| **Embedding dimension = 3072** | Tied to OpenAI `text-embedding-3-large` (native dims, no `dimensions=` truncation — ADR-013; was 1536/`text-embedding-3-small` before V8_4). Ingestion writes these embeddings; retrieval must use the same model and dimension. Every `narrative_chunks` row records its `embedding_model` (V8_4, ex-ADR-006 V15) for the startup drift check. The embedding model in `LangChain4jConfig.kt` is intentionally OpenAI-specific and not swappable without re-ingesting the full corpus. The chat model, by contrast, is provider-configurable. |
| **`pg_trgm` extension required** | `V1__enable_pgvector.sql` enables both `vector` and `pg_trgm`. `V3__create_entities.sql` adds a GIN trigram index on `entities.name`. Used by `ConflictLookup`'s third entity-resolution step (exact → alias → trigram) for fuzzy entity name matching (spelling variants, typos). (Per ADR-007/DEV-014, this resolution moved from the deleted `ConflictQueryHandler` into the shared `ConflictLookup`.) |
| **Flyway afterMigrate callback re-grants SELECT** | `afterMigrate__grant_app_user.sql` runs `GRANT SELECT ON ALL TABLES IN SCHEMA public TO zeus_app;` after every Flyway execution. Idempotent. Compensates for the fact that `ALTER DEFAULT PRIVILEGES` in `01_readonly_user.sql` only applies to tables created by the user who ran it — new Flyway migrations adding tables would otherwise leave `zeus_app` without SELECT, causing `PSQLException: permission denied` at runtime. |
| **`sources.id` is TEXT, not SERIAL** | Sources use human-readable slug PKs (e.g. `'apollodorus-bibliotheca'`). All FK columns referencing `sources(id)` are `TEXT`. This ensures the Python `SourceConfig.source_id: str` values remain stable across DB resets and do not depend on Postgres sequence state. |
| **`createTable(false)` on `PgVectorEmbeddingStore`** | Flyway created `narrative_chunks`; the store must not try to recreate it. |
| **HNSW index** | HNSW, not IVFFlat (IVFFlat requires a minimum number of rows to build; HNSW works at any size). Since V8_4 (ADR-013) the index is a **halfvec expression index** — `USING hnsw ((embedding::halfvec(3072)) halfvec_cosine_ops)` — because plain-vector HNSW caps at 2000 dims. Retrieval SQL must use the same cast (`ORDER BY embedding::halfvec(3072) <=> (?::vector(3072))::halfvec(3072)`) or Postgres silently falls back to a seq scan. |
| **`ON CONFLICT DO NOTHING` in seed SQL** | All seed INSERT statements must be idempotent. Re-running migrations (e.g., in test) must not fail. |
| **`NOT NULL` on `source_id`** in `narrative_chunks` | No anonymous chunks. Every embedded text segment traces to a source. |
| **Idempotent ingestion via `content_hash`** | `narrative_chunks` carries `content_hash TEXT GENERATED ALWAYS AS (md5(content)) STORED` with a `UNIQUE (source_id, passage_ref, content_hash)` constraint. All `INSERT` statements in `embedding_pipeline.py` must use `ON CONFLICT (source_id, passage_ref, content_hash) DO NOTHING` — re-running ingestion after a partial failure must not create duplicate rows or error out. |
| **`sources` rows must include `year_published` and `role`** | `year_published` is required for full citations (e.g. "Evelyn-White, 1914"). `role` controls ingestion priority (`spine` → fully indexed; `stretch` → optional). Never insert a source row without both fields. |
| **`variant_claims` seed rows use `trust_tier=1`** | All Phase 1 seed data promoted into `V12` is `trust_tier=1` (reviewed). Do not insert provisional or auto-extracted rows without setting `trust_tier=3` and a comment explaining the source. |

---

## Seed Data Extraction (ADR-004)

Full decision record: `docs/adr/adr-004-seed-data-extraction-strategy.md`.

| Rule | Detail |
|---|---|
| **Extraction is offline, corpus-prep tooling only** | Lives in `ingestion/extraction/`. Never a runtime `@AiService`, never called at query time, never wired into `LangChain4jConfig.kt`. |
| **Tiered review by table** | `entities`/`relationships` (V10/V11): LLM-extracted, developer spot-check before merging into the migration. `variant_claims` (V12): every candidate staged at `trust_tier=3`; requires explicit developer promotion to `trust_tier=1` before it enters the migration. Never insert extraction output directly into any seed migration unreviewed. |
| **`sources`, `myths`/`myth_participants`, `entity_aliases` stay hand-curated** | Not corpus-derived — bibliographic metadata, editorial groupings, and cross-cultural name maps aren't extraction targets. ADR-004 does not change V9/V13/V14. |
| **Minimum `variant_claims` coverage is a hard floor** | Aphrodite parentage, Io parentage, and Achilles death variants (`IMPLEMENTATION_PLAN.md §3`) must be present in `V12` regardless of what extraction surfaces — hand-add if the pipeline misses one. |
| **`instructor` and `rapidfuzz` are approved ingestion-only dependencies** | `instructor` wraps the same `openai` client for Pydantic-validated structured output with automatic retry-on-invalid-schema — it is not a second LLM framework. `rapidfuzz` is local, in-memory fuzzy matching for corpus-time entity dedup during extraction; it is a different concern from `ConflictLookup`'s runtime `pg_trgm` fuzzy match against the already-seeded `entities` table (§ Data Model) — both exist, neither replaces the other. |
| **Extraction segments by passage-ref boundary, not RAG chunk size** | Reuses the same `passage_ref_extractor` scan as the RAG chunker, but groups whole sections between consecutive refs so a full genealogical statement isn't split mid-claim. |

---

## Code Structure

| Rule | Detail |
|---|---|
| **No LLM calls in controllers** | Controllers receive HTTP requests and delegate to the service layer. `QueryService` calls handlers. Handlers call AI services. |
| **Service classes ≤ 300 lines** | Split by responsibility if you approach this. |
| **Ingestion is Python, not JVM** | `ingestion/` is a standalone Python 3.12+ project. Not a Gradle module. No Spring, no LangChain4j. Uses `openai` Python SDK + `psycopg2` + `pgvector` directly. |
| **One handler per route** | `SqlQueryHandler`, `RagQueryHandler`, `MixedQueryHandler` — each in its own file. `QueryService` is the only place that knows about all three handlers plus the router-independent conflict-enrichment step. **Amended by ADR-007 (`DEVIATIONS.md` DEV-014):** there is no `CONFLICT` route and no `ConflictQueryHandler` — conflict surfacing is a `QueryService` enrichment step (`ConflictProbe` → shared `ConflictLookup` → `ConflictSynthesizer`), not a route. |

---

## Testing

| Rule | Detail |
|---|---|
| **TDD — tests before production code** | Every handler, validator, and service must have a failing test before its implementation. No implementation phase is complete until the tests listed in `IMPLEMENTATION_PLAN.md §8` pass. |
| **No live LLM calls in tests** | All `@AiService` interfaces must be mocked. Use `mockk<T>()` for pure unit tests and `@MockkBean` (`com.ninja-squad:springmockk`) for Spring-context tests. |
| **Testcontainers for DB integration tests** | Any test that hits the database uses Testcontainers with PostgreSQL 16 + pgvector. No H2, no in-memory fakes, no manual setup. |
| **`test` profile uses `validate`** | `application-test.yml` sets `ddl-auto: validate`, same as production. Flyway runs on startup against the fresh Testcontainers DB and owns all DDL. `create-drop` is not permitted — it conflicts with the "Flyway owns DDL" rule and is redundant since Testcontainers destroys the container after tests. |
| **HTTP layer via MockMvc or `RANDOM_PORT`** | Never test controller behaviour through a direct service call. Use `@WebMvcTest` + `MockMvc` for unit-level controller tests, or `@SpringBootTest(webEnvironment = RANDOM_PORT)` for full integration tests. |
| **Python tests use pytest, no I/O calls** | `ingestion/tests/` uses pytest. Tests for `text_cleaner.py` and `text_chunker.py` are required. Pass raw strings directly — do not read from `corpus/` or make network calls in tests. |

---

## PoC Boundaries — Do Not Add

These are explicitly out of scope. Adding them without a deliberate decision wastes time and complexity.

| Do NOT add | Reason |
|---|---|
| Spring Security / auth | No users, no sessions needed for PoC. |
| Redis or any caching layer | Response times are acceptable without it at demo scale. |
| Kafka, RabbitMQ, or any message queue | No async processing pipeline needed. |
| Spring Cloud (Gateway, Config Server, Eureka) | Two services + a DB. No service mesh needed. |
| Spring AI | Library decision was LangChain4j. Mixing both causes confusion and duplicate beans. |
| Direct OpenAI SDK (`com.openai:openai-java`) | Everything goes through LangChain4j. |
| Any modern copyrighted translation | Only Frazer 1921, Evelyn-White 1914, Murray 1919–1924. Check before adding any text source. |
| Auto-promoting extracted `variant_claims` to `trust_tier=1` without review | See "Seed Data Extraction (ADR-004)" below — this table is the one place accuracy is worth the manual review cost. |
| A broader extraction schema (`numerical_claim`, `place`, `creature`, `event`, generic `conflict` table) | Considered and rejected in ADR-004 — doesn't match the already-built V1–V8 schema and reintroduces breadth this PoC deliberately scoped away from. |

---

## Data & Content

| Rule | Detail |
|---|---|
| **Public domain translations only** | Frazer 1921 (Apollodorus), Evelyn-White 1914 (Hesiod, Homeric Hymns), Murray 1919–1924 (Homer), plus older PD Ovid/Hyginus translations. Verify before ingesting any new source. |
| **No HTML scraping** | Corpus text is loaded from local .txt files in `ingestion/corpus/`. Do not add `html_scraper.py`, `requests`, or `BeautifulSoup4`. Download plaintext exports once (Project Gutenberg, sacred-texts.com text versions) and store locally. |
| **No LLM calls during loading** | `text_cleaner.py` uses plain `re` operations only. LLM is used at embed time and at query time — not during loading or cleaning. |
| **`source_id` in every chunk metadata** | `TextSegment` metadata must carry `source_id`, `author`, `work`, `passage_ref` so RAG citations are attributable. |

---

## Environment & Secrets

| Rule | Detail |
|---|---|
| **`.env` is gitignored** | Commit `.env.example` with placeholder values; `.env` is never committed. |
| **No secrets in `application.yml`** | All secrets (`OPENAI_API_KEY`, `LLM_API_KEY`, `POSTGRES_PASSWORD`, `TELEGRAM_BOT_TOKEN`) come from environment variables referenced as `${VAR_NAME}`. `OPENAI_API_KEY` is used by ingestion and by the embedding bean (`app.llm.embedding-api-key`). `LLM_API_KEY` is used by the chat model bean (`app.llm.chat-api-key`) — set it to the same value as `OPENAI_API_KEY` for Phase 1. |
| **Docker Compose for local dev** | `docker-compose.yml` (DB only) and `docker-compose.full.yml` (full stack). No manual postgres setup instructions. |

---

## Docker Compose Environment Variables

```
OPENAI_API_KEY=sk-...                    # used by ingestion and by core-api embedding bean (app.llm.embedding-api-key)
LLM_API_KEY=sk-ant-...                   # used by core-api chat model bean (app.llm.chat-api-key); Anthropic key since ADR-008 — a different key from OPENAI_API_KEY
LLM_CHAT_MODEL=claude-haiku-4-5-20251001 # example value only — no default is set in application.yml; update LangChain4jConfig.kt beans when using a different chat provider
EMBEDDING_MODEL=text-embedding-3-large   # single source of truth (ADR-006) shared by ingestion + core-api embedding bean; -large since ADR-013
ANTHROPIC_API_KEY=sk-ant-...             # Stage 4 offline extraction only (ADR-008); may be the same key as LLM_API_KEY — separate var because the Anthropic Python SDK reads it by convention
EXTRACTION_MODEL=claude-opus-4-8         # Stage 4 offline extraction model (ADR-008); never used at query time
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_DB=blamezeus
POSTGRES_USER=zeus
POSTGRES_PASSWORD=olympus
POSTGRES_APP_USER=zeus_app
POSTGRES_APP_PASSWORD=app_password
TELEGRAM_BOT_TOKEN=...
TELEGRAM_BOT_USERNAME=BlameZeusBot
CORE_API_BASE_URL=http://core-api:8080
```
