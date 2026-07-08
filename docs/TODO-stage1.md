# Stage 1 — Foundation: Detailed Checklist

Stage 1 is three commits. Within each commit, tasks are ordered; across commits, order is 1a → 1b → 1c.

---

## Stage 1a — Gradle project scaffold ✅

**Done when:** `./gradlew :core-api:compileKotlin` succeeds; module structure matches plan.

- [x] **A1** Create root `settings.gradle.kts`
  - `rootProject.name = "blame-zeus"`
  - `include("core-api", "telegram-bot")`
  - Comment excluding `ingestion/` from Gradle scanning
- [x] **A2** Create root `build.gradle.kts`
  - `plugins {}` block only (no `apply` calls, no code)
  - Versions: Spring Boot 3.3.13, io.spring.dependency-management 1.1.7; Kotlin 2.3.21 declared in settings pluginManagement
- [x] **A3** Create `gradle.properties`
  - `kotlin.code.style=official`
  - `org.gradle.jvmargs=-Xmx2g`
  - `javaVersion=21`
- [x] **A4** Create `buildSrc/` convention plugin
  - `buildSrc/build.gradle.kts` — apply `kotlin-dsl`, add `kotlin-gradle-plugin` + `kotlin-allopen` deps
  - `buildSrc/src/main/kotlin/blame-zeus.kotlin-conventions.gradle.kts`
    - Apply `kotlin("jvm")` + `kotlin("plugin.spring")`, set `jvmTarget = "21"`
    - Add `kotlin-reflect` + `jackson-module-kotlin` to all JVM modules
- [x] **A5** Create `core-api/build.gradle.kts`
  - All compile + test dependencies (LangChain4j 1.0.0-beta5, Flyway, pgvector, springdoc 2.8.3, Testcontainers BOM-managed, springmockk 4.0.2)
- [x] **A6** Create `telegram-bot/build.gradle.kts`
  - Apply `blame-zeus.kotlin-conventions` + `org.springframework.boot`; `spring-boot-starter-web` only (telegrambots commented out for Phase 2)
- [x] **A7** Create `core-api/src/main/kotlin/com/blamezeus/coreapi/CoreApiApplication.kt`
  - `@SpringBootApplication` main class, `fun main(args: Array<String>)` entry point
- [x] **A8** Create `core-api/src/main/resources/application.yml`
  - `spring.datasource` + Hikari `statement_timeout`, `spring.flyway` (superuser), `spring.jpa.hibernate.ddl-auto: validate`, `app.llm` block
- [x] **A9** Verify: `./gradlew :core-api:compileKotlin` succeeds ✅

---

## Stage 1b — Local dev infrastructure

**Done when:** `docker-compose up -d` starts Postgres; `docker-compose exec postgres pg_isready` returns success.

- [x] **B1** Create `docker-compose.yml` (DB-only)
  - Service `postgres` using `pgvector/pgvector:pg16`
  - Volumes: `postgres_data:/var/lib/postgresql/data`
  - Mount `./docker/init:/docker-entrypoint-initdb.d`
  - Env: `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` from `.env`
  - Healthcheck: `pg_isready -U ${POSTGRES_USER} -d ${POSTGRES_DB}`
  - Port mapping: `5432:5432`
- [x] **B2** Create `docker/init/01_readonly_user.sql`
  - `CREATE USER zeus_app WITH PASSWORD 'app_password';`
  - `GRANT CONNECT ON DATABASE blamezeus TO zeus_app;`
  - `GRANT USAGE ON SCHEMA public TO zeus_app;`
  - `GRANT SELECT ON ALL TABLES IN SCHEMA public TO zeus_app;`
  - `ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO zeus_app;`
- [x] **B3** Create `docker-compose.full.yml` (full stack placeholder)
  - Include `postgres` service (same as DB-only compose)
  - Add `core-api` service placeholder (image/build TBD, `depends_on: postgres`)
  - Add `telegram-bot` service placeholder (depends on core-api with `condition: service_healthy`)
- [x] **B4** Create `.env.example`
  - Placeholder values (no real keys): `OPENAI_API_KEY=sk-...`, `LLM_API_KEY=sk-...`, `LLM_CHAT_MODEL=gpt-4o-mini`, `POSTGRES_USER=zeus`, `POSTGRES_PASSWORD=olympus`, `POSTGRES_APP_USER=zeus_app`, `POSTGRES_APP_PASSWORD=app_password`, `POSTGRES_DB=blamezeus`, `TELEGRAM_BOT_TOKEN=...`, `TELEGRAM_BOT_USERNAME=BlameZeusBot`, `CORE_API_BASE_URL=http://core-api:8080`
- [x] **B5** Confirm `.env` is in `.gitignore` (add if missing) — already present
- [x] **B6** Verify: `docker-compose up -d` starts Postgres; `docker-compose exec postgres pg_isready` returns success

---

## Stage 1c — Database schema + foundation tests

**Done when:** Flyway applies V1–V8; `FlywayMigrationTest` + `SchemaIntrospectorTest` pass against Testcontainers; `zeus_app` SELECT works, DROP is denied.

> ⚠️ Updated based on DEV-003 (see DEVIATIONS.md): Flyway is 10.10.0 (not 9.x). `flyway-database-postgresql` is already declared as `runtimeOnly` in `core-api/build.gradle.kts`. Migration SQL syntax and `afterMigrate__*.sql` callback naming are unchanged in Flyway 10.x — the items below require no edits.

_Write tests in D1–D4 before implementing `SchemaIntrospector` in E1._

### Flyway migrations

_Directory:_ `core-api/src/main/resources/db/migration/`

- [ ] **C1** `V1__enable_pgvector.sql`
  ```sql
  CREATE EXTENSION IF NOT EXISTS vector;
  CREATE EXTENSION IF NOT EXISTS pg_trgm;
  ```
- [ ] **C2** `V2__create_sources.sql`
  - `sources(id TEXT PRIMARY KEY, author TEXT NOT NULL, work TEXT NOT NULL, passage_ref TEXT, translation TEXT, stance TEXT NOT NULL, year_published INTEGER NOT NULL, role TEXT NOT NULL)`
  - `CHECK (stance IN ('poetic-myth','mythographic-handbook','cosmological','hymnic'))`
  - `CHECK (role IN ('spine','primary','selective','stretch'))`
- [ ] **C3** `V3__create_entities.sql`
  - `entities(id SERIAL PRIMARY KEY, name TEXT NOT NULL UNIQUE, type TEXT NOT NULL, generation INTEGER, domain TEXT)`
  - `CHECK (type IN ('primordial','titan','olympian','other_god','hero','mortal','monster','nymph'))`
  - `CREATE INDEX idx_entities_name_trgm ON entities USING gin(name gin_trgm_ops);`
- [ ] **C4** `V4__create_relationships.sql`
  - `relationships(id SERIAL PRIMARY KEY, from_id INTEGER NOT NULL REFERENCES entities(id), relation TEXT NOT NULL, to_id INTEGER NOT NULL REFERENCES entities(id), source_id TEXT NOT NULL REFERENCES sources(id))`
  - Index on `(from_id)`, `(to_id)`, `(source_id)`
- [ ] **C5** `V5__create_myths.sql`
  - `myths(id SERIAL PRIMARY KEY, title TEXT NOT NULL, location TEXT, summary TEXT)`
  - No `source_id` FK — structural container only
- [ ] **C6** `V6__create_myth_participants.sql`
  - `myth_participants(myth_id INTEGER NOT NULL REFERENCES myths(id), entity_id INTEGER NOT NULL REFERENCES entities(id), role TEXT, PRIMARY KEY (myth_id, entity_id))`
- [ ] **C7** `V7__create_variant_claims.sql`
  - `variant_claims(id SERIAL PRIMARY KEY, subject_entity_id INTEGER NOT NULL REFERENCES entities(id), claim_type TEXT NOT NULL, claim_value TEXT NOT NULL, source_id TEXT NOT NULL REFERENCES sources(id), trust_tier SMALLINT NOT NULL DEFAULT 2)`
  - `CREATE INDEX idx_variant_claims_subject_type ON variant_claims(subject_entity_id, claim_type);`
- [ ] **C8** `V8__create_narrative_chunks.sql`
  - `narrative_chunks(id SERIAL PRIMARY KEY, content TEXT NOT NULL, content_hash TEXT GENERATED ALWAYS AS (md5(content)) STORED, embedding vector(1536) NOT NULL, source_id TEXT NOT NULL REFERENCES sources(id), passage_ref TEXT, metadata JSONB)`
  - `UNIQUE (source_id, passage_ref, content_hash)`
  - `CREATE INDEX ON narrative_chunks USING hnsw (embedding vector_cosine_ops) WITH (m=16, ef_construction=64);`
- [ ] **C9** `afterMigrate__grant_app_user.sql` (Flyway callback, not versioned)
  - `GRANT SELECT ON ALL TABLES IN SCHEMA public TO zeus_app;`

### Tests (write before SchemaIntrospector)

- [ ] **D1** Create `core-api/src/test/resources/application-test.yml`
  ```yaml
  spring:
    jpa:
      hibernate:
        ddl-auto: validate
    flyway:
      enabled: true
  ```
- [ ] **D2** Create Testcontainers base configuration
  - Abstract base class or `@TestConfiguration` that starts `PostgreSQLContainer` with `pgvector/pgvector:pg16` image
  - Expose container URL/credentials as Spring properties via `@DynamicPropertySource`
- [ ] **D3** Write `FlywayMigrationTest.kt` (should **fail** until C1–C8 migrations are applied)
  - `@SpringBootTest` + `@ActiveProfiles("test")` + `@Testcontainers`
  - Helper `columns(table: String): List<String>` using `information_schema.columns`
  - `@Test fun 'all expected tables exist'` — assert each of V1–V8 tables is present
  - `@Test fun 'variant_claims has required columns'` — assert `subject_entity_id`, `claim_type`, `claim_value`, `source_id`, `trust_tier`
  - `@Test fun 'narrative_chunks has content_hash and embedding'` — assert `content`, `content_hash`, `embedding`, `source_id`, `passage_ref`
  - `@Test fun 'sources has year_published and role'` — assert `author`, `work`, `translation`, `stance`, `year_published`, `role`
  - `@Test fun 'entity_aliases table does not exist yet'` — will be created in V14 (Stage 2)
- [ ] **D4** Write `SchemaIntrospectorTest.kt` (should **fail** until E1 is implemented)
  - `@SpringBootTest` + `@ActiveProfiles("test")` + `@Testcontainers`
  - `@Autowired lateinit var schemaIntrospector: SchemaIntrospector`
  - `@Test fun 'prompt contains all application tables'` — assert `entities`, `relationships`, `sources`, `variant_claims`, `narrative_chunks`
  - `@Test fun 'prompt contains known columns from critical tables'` — assert `subject_entity_id`, `trust_tier`, `year_published`, `content_hash`

### SchemaIntrospector

- [ ] **E1** Create `core-api/src/main/kotlin/com/blamezeus/coreapi/config/SchemaIntrospector.kt`
  - `@Component` with `JdbcTemplate` injection
  - `private val schemaPrompt: String by lazy { buildSchemaPrompt() }`
  - `fun get(): String = schemaPrompt`
  - `buildSchemaPrompt()` queries `information_schema.columns` for the 7 application tables; formats as `tableName(col1, col2, ...)` per line
  - Tables list: `entities`, `relationships`, `myths`, `myth_participants`, `sources`, `variant_claims`, `narrative_chunks`
- [ ] **E2** Verify `SchemaIntrospectorTest` passes (D4 tests turn green)

### Verification

- [ ] **INT1** `./gradlew :core-api:test --tests "*.FlywayMigrationTest"` — all tests pass
- [ ] **INT2** `./gradlew :core-api:test --tests "*.SchemaIntrospectorTest"` — all tests pass
- [ ] **INT3** Start `core-api` locally (with DB running): Flyway log shows V1–V8 applied, no errors
- [ ] **INT4** `psql -U zeus -d blamezeus -c "\dt"` — lists all 7 tables, no extras
- [ ] **INT5** `psql -U zeus_app -d blamezeus -c "SELECT 1 FROM entities LIMIT 1"` — succeeds
- [ ] **INT6** `psql -U zeus_app -d blamezeus -c "DROP TABLE entities"` — fails with permission denied
