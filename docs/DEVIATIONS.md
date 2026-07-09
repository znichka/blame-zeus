# blame-zeus: Implementation Deviations

This file records every deviation from `IMPLEMENTATION_PLAN.md` that occurred during implementation. It is append-only — entries are never edited after being written.

See `CLAUDE.md §Deviation Tracking Protocol` for the rules governing when and how to write here.

---

## Stage 1a — Gradle project scaffold (2026-07-08)

### DEV-001 — Kotlin version: 1.9.x → 2.3.21

| Field | Detail |
|---|---|
| **Stage** | 1a |
| **Original Plan** | Kotlin 1.9.x |
| **What Changed** | Kotlin 2.3.21 |
| **Reason** | Gradle 9.6.1 (the installed build tool) bundles Kotlin 2.3.21 inside `kotlin-dsl`. Pre-compiled convention plugins in `buildSrc/` are compiled by `kotlin-dsl`'s embedded Kotlin (2.3.21). Declaring `kotlin("jvm") version "1.9.25"` in the main build causes a classpath version conflict: the convention plugin bytecode (compiled against KGP 2.3.21 APIs) runs against a KGP 1.9.x runtime in subprojects, leading to `NoSuchMethodError` and incompatible class errors. Using 2.3.21 throughout eliminates the conflict. |
| **Impact** | All production Kotlin code should continue to compile unchanged (2.x is backward-compatible for the code patterns used in this project). Future stages that reference Kotlin plugin API types in convention plugins should use `compilerOptions {}` (2.x API) instead of the deprecated `kotlinOptions {}` (1.x API). Kotlin 2.x K2 compiler is the default — no K1 flag needed. |

---

### DEV-002 — Spring Boot version: 3.2.x → 3.3.13

| Field | Detail |
|---|---|
| **Stage** | 1a |
| **Original Plan** | Spring Boot 3.2.x |
| **What Changed** | Spring Boot 3.3.13 |
| **Reason** | Spring Boot 3.3.x was the latest stable 3.x line at implementation time and is better-tested against JDK 26 (the only JDK available on the dev machine). Spring Boot 3.2.x reached EOL in November 2024. The Spring Boot 3.3.x BOM also manages Testcontainers 1.19.8 (matching the plan spec) directly, simplifying dependency management. |
| **Impact** | Spring Boot 3.3.x bundles Flyway 10.10.0 (see DEV-003). All future stage tests and Spring Boot auto-configuration use 3.3.x APIs. Jakarta namespace is unchanged (same as 3.2.x). No Stage 2+ TODOs need updating — the JPA entity and repository patterns are identical between 3.2 and 3.3. |

---

### DEV-003 — Flyway version and PostgreSQL module: 9.x → 10.10.0 + flyway-database-postgresql

| Field | Detail |
|---|---|
| **Stage** | 1a |
| **Original Plan** | `flyway-core` only (Flyway 9.x via Spring Boot 3.2.x) |
| **What Changed** | `flyway-core` managed at 10.10.0 (via Spring Boot 3.3.x BOM) + `flyway-database-postgresql` added as `runtimeOnly` |
| **Reason** | Flyway 10.x split PostgreSQL support into a separate module (`flyway-database-postgresql`) to reduce core artifact size. Without it, Flyway 10.x throws at startup: "No database found to handle jdbc:postgresql://...". The `runtimeOnly` scope is correct — the module is not needed at compile time. |
| **Impact** | `flyway-database-postgresql` is already declared in `core-api/build.gradle.kts`. Flyway migration SQL syntax (V1–V14) and callback naming (`afterMigrate__*.sql`) are unchanged between v9 and v10. Stage 1c migration files can be written as planned with no changes. |

---

### DEV-004 — LangChain4j version: 1.0.x (stable) → 1.0.0-beta5

| Field | Detail |
|---|---|
| **Stage** | 1a |
| **Original Plan** | LangChain4j 1.0.x (implied stable GA) |
| **What Changed** | LangChain4j 1.0.0-beta5 (latest available on Maven Central at time of implementation) |
| **Reason** | LangChain4j 1.0.0 GA was not yet published to Maven Central. 1.0.0-beta5 is the latest pre-release in the 1.0.x line. |
| **Impact** | **Affects Stages 5–8 (AI pipeline implementation).** The `@AiService` annotation API, `@V` parameter injection, `@SystemMessage`/`@UserMessage`, and `EmbeddingStore` interfaces in `1.0.0-beta5` may differ from the 1.0.0 GA API. Before writing Stage 5 code, verify the current beta5 API shapes for: `@AiService`, `@V`, `EmbeddingStore`, `ContentRetriever`, and `PgVectorEmbeddingStore`. Update Stage 5 TODO items with: "Updated Stage 5 assumptions based on Stage 1 deviation DEV-004 (see DEVIATIONS.md)". |

---

### ~~DEV-005 — JDK version: 21 (required) → 26 (dev machine only)~~ RESOLVED

| Field | Detail |
|---|---|
| **Stage** | 1a |
| **Original Plan** | JVM 21 |
| **What Changed** | ~~JDK 26 on dev machine~~ — **resolved**: OpenJDK 21.0.11 (`/opt/homebrew/opt/openjdk@21`) was confirmed to be installed. Initial implementation mistakenly pointed `JAVA_HOME` at the `openjdk` symlink (which resolves to 26) instead of `openjdk@21`. |
| **Reason** | Operator error in JDK selection; `openjdk@21` was present all along. |
| **Resolution** | `JAVA_HOME=/opt/homebrew/opt/openjdk@21`. `./gradlew :core-api:compileKotlin` re-verified clean with Java 21 — no warnings, BUILD SUCCESSFUL. |
| **Impact** | No deviation from plan. This entry is kept for audit purposes only. |

---

### DEV-006 — springdoc-openapi version: 2.5.x → 2.8.3

| Field | Detail |
|---|---|
| **Stage** | 1a |
| **Original Plan** | `springdoc-openapi-starter-webmvc-ui:2.5.x` |
| **What Changed** | `springdoc-openapi-starter-webmvc-ui:2.8.3` |
| **Reason** | 2.5.x availability was not confirmed; 2.8.3 was the latest stable version verified on Maven Central. springdoc 2.x is fully backward-compatible across minor versions for the annotations used in this project (`@Operation`, `@Tag`). |
| **Impact** | No impact on future stages. The `OpenApiConfig.kt` class (Stage 9) uses the same springdoc annotations in 2.8.x as in 2.5.x. |

---

### DEV-007 — telegrambots-spring-boot-starter: declared → commented out

| Field | Detail |
|---|---|
| **Stage** | 1a |
| **Original Plan** | `telegram-bot/build.gradle.kts` includes `telegrambots-spring-boot-starter:6.9.x` as a Phase 2 placeholder dependency |
| **What Changed** | Dependency is commented out; `telegram-bot` only has `spring-boot-starter-web` |
| **Reason** | The correct artifact coordinates and version for telegrambots 6.9.x were not verified. Adding an unresolvable dependency would break `./gradlew dependencies` for the `telegram-bot` module. The placeholder comment (`// Phase 2: implementation(...)`) preserves the intent without blocking Stage 1a verification. |
| **Impact** | **Affects Stage 11.** When implementing Stage 11, the telegrambots dependency must be added back. Verify correct coordinates (likely `org.telegram:telegrambots-spring-boot-starter:6.9.7`) before adding. Mark Stage 11 TODO item: `[DEVIATED - see DEVIATIONS.md DEV-007]`. |

---

## Stage 1c — Database schema + foundation tests (2026-07-08)

### DEV-008 — Testcontainers version: Spring Boot 3.3.13 BOM default (1.19.x) → 1.21.4 pinned override

| Field | Detail |
|---|---|
| **Stage** | 1c |
| **Original Plan** | Use Testcontainers as managed by the Spring Boot 3.3.13 BOM, no explicit version override |
| **What Changed** | `core-api/build.gradle.kts` sets `extra["testcontainers.version"] = "1.21.4"`, overriding the BOM-managed version |
| **Reason** | The BOM-managed Testcontainers line (1.19.x/1.20.x) ships a docker-java client that falls back to Docker Engine API version 1.32 when negotiation fails. Recent Docker Engine releases (29+, and current Docker Desktop) hard-reject any client below API 1.40, causing every `PostgreSQLContainer` start to fail with `client version 1.32 is too old`. Testcontainers `1.21.4` backports the fix within the 1.x line (same groupId/artifact coordinates, no breaking API changes), avoiding a riskier jump to the 2.x major line. |
| **Impact** | All future Testcontainers-based integration tests (Stage 2+ repository tests, etc.) are unaffected — same `PostgreSQLContainer` API. If the BOM's default Testcontainers version is bumped past `1.21.4` in a future Spring Boot upgrade, this override can likely be removed; verify with `./gradlew :core-api:dependencies --configuration testRuntimeClasspath` before removing. |

---

### DEV-009 — springdoc-openapi version: 2.8.3 (DEV-006) → 2.6.0 (corrects DEV-006)

| Field | Detail |
|---|---|
| **Stage** | 1c |
| **Original Plan** | `springdoc-openapi-starter-webmvc-ui:2.5.x` (per original plan); DEV-006 changed this to `2.8.3` during Stage 1a |
| **What Changed** | `springdoc-openapi-starter-webmvc-ui:2.6.0` — corrects DEV-006, which picked an incompatible version |
| **Reason** | `springdoc-openapi 2.8.3` requires Spring Boot 3.4.x / Spring Framework 6.2.x (its own POM depends on `spring-boot-autoconfigure:3.4.1` and `spring-webmvc:6.2.1`). This project pins Spring Boot 3.3.13 (Spring Framework 6.1.21) per DEV-002, so Gradle's dependency management silently downgraded springdoc's transitive Spring dependencies to 6.1.21/3.3.13. `spring-webmvc:6.1.21` does not contain `org.springframework.web.servlet.resource.LiteWebJarsResourceResolver` (added in Spring Framework 6.2), which springdoc's autoconfiguration references — causing every `@SpringBootTest` (and the running app) to fail with `ClassNotFoundException: ...LiteWebJarsResourceResolver` and `ApplicationContext failure threshold exceeded`. This was discovered while getting `FlywayMigrationTest`/`SchemaIntrospectorTest` to pass in Stage 1c — the failure only surfaces when a full `@SpringBootTest` context loads, so it was invisible at `compileKotlin` time. `2.6.0` is the last release in the line compatible with Spring Boot 3.3.x (2.7.0+ requires 3.4.0+). |
| **Impact** | **Corrects DEV-006.** `OpenApiConfig.kt` (Stage 9) must target springdoc 2.6.0's API surface, not 2.8.3's — no breaking changes affect basic `@Operation`/`@Tag` annotation usage between these lines. If Spring Boot is ever upgraded to 3.4.x+, springdoc can be bumped back to the 2.8.x/2.7.x line at that time. |

---

## Stage 2 — Ingestion Setup (2026-07-09)

### DEV-010 — Ingestion venv interpreter: python3.12 → python@3.14 (Homebrew)

| Field | Detail |
|---|---|
| **Stage** | 2 (Track A) |
| **Original Plan** | `python3.12 -m venv .venv` (per `docs/TODO-stage2.md` A3 and `CLAUDE.md`'s "Python 3.12+" tech stack line) |
| **What Changed** | Used Homebrew's `python@3.14` (`/opt/homebrew/opt/python@3.14/bin/python3.14`) to create `ingestion/.venv/` |
| **Reason** | No `python3.12` binary is installed on the dev machine (only system `/usr/bin/python3` at 3.9.6, and Homebrew's `python@3.14`). `CLAUDE.md` specifies "Python 3.12+", so 3.14 satisfies the constraint; installing a second Python minor version via `pyenv`/Homebrew solely to match the plan's literal example was judged unnecessary. |
| **Impact** | All `ingestion/` code must avoid any syntax/stdlib feature introduced after 3.12 if strict 3.12 compatibility is later required (none currently used — the package only relies on `openai`, `psycopg2-binary`, `pgvector`, `tenacity`, `python-dotenv`, `pytest`, all of which support 3.12–3.14). If a teammate's machine has `python3.12` available, recreating `ingestion/.venv/` with it instead is fine and requires no code changes. |
