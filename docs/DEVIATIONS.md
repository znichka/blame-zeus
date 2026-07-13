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

---

### DEV-011 — `apollodorus_refs` regex extended to match Epitome (`E.x.y`) markers

| Field | Detail |
|---|---|
| **Stage** | 2 (Track D) |
| **Original Plan** | `r'(?m)^\s*\[?(\d+\.\s*\d+\.\s*\d+)\]?'` (`docs/IMPLEMENTATION_PLAN.md` §4, "Extractor helper pattern") — matches only purely numeric `book.chapter.section` markers |
| **What Changed** | `r'(?m)^\s*\[?((?:E|\d+)\.\s*\d+\.\s*\d+)\]?'` — also matches the Epitome's `E.chapter.section` markers (e.g. `[E.1.1]`) |
| **Reason** | The real ingested corpus (`ingestion/corpus/apollodorus_bibliotheca_frazer1921.txt`, from Track B) includes Frazer's Epitome (summary of lost books), whose passage markers use an `E.` prefix instead of a leading book number — a format that didn't exist in the plan's abstract example and wasn't covered by its literal regex. Without this fix, all 177 Epitome markers (verified by direct extraction against the real corpus text: 209 numeric-only matches vs. 386 total once `E.` is included) would fail to match, and every Epitome-derived chunk would silently inherit `passage_ref = "3.16.2"` (the last real Book 3 marker) via `text_chunker.py`'s `_nearest_ref` fallback — a source-attribution accuracy bug that directly undermines this project's core citation feature. Confirmed by decision with the user rather than deviating unilaterally. |
| **Impact** | `ingestion/loader/source_registry.py`'s `apollodorus_refs` now returns 386 refs (209 numeric + 177 Epitome) against the real corpus, strictly ascending, matching the true structure of the source text. `ingestion/tests/test_passage_ref_extractors.py` covers both the numeric and `E.x.y` cases (including OCR-noise variants). No impact on other sources' extractors (Homer/Hesiod/Ovid, Stage 3) — those use unrelated marker formats (`[ll. ...]`, `BOOK ...`). |

---

### DEV-012 — `text_chunker.py`'s `chunk()` loop: fixed infinite loop + unbounded chunk-size overshoot

| Field | Detail |
|---|---|
| **Stage** | 2 (Track E) |
| **Original Plan** | `docs/IMPLEMENTATION_PLAN.md` §4, "`text_chunker.py`" — literal loop: inner `while i < len(sentences) and sum(len(s) for _, s in buf) < CHUNK_SIZE: buf.append(...); i += 1`, then unconditional `i -= OVERLAP_SENTENCES; if i < 0: break` after every chunk |
| **What Changed** | Two independent fixes to `chunk()` in `ingestion/chunker/text_chunker.py`: (1) the outer loop now checks `if i >= len(sentences): break` **before** rolling back for overlap, and the rollback amount is clamped to `min(OVERLAP_SENTENCES, len(buf) - 1)` instead of always subtracting the full `OVERLAP_SENTENCES`; (2) the inner accumulation loop now stops **before** adding a sentence that would push the running length past `CHUNK_SIZE` (unless the chunk is still empty), instead of always admitting one full sentence after the sum first crosses `CHUNK_SIZE`. |
| **Reason** | (1) **Infinite loop**: whenever the tail of a document leaves ≤ `OVERLAP_SENTENCES` sentences remaining, the inner loop exits because `sentences` is exhausted, not because `CHUNK_SIZE` was reached — the unconditional `i -= OVERLAP_SENTENCES` then returns `i` to the exact same index every outer iteration, hanging forever (reproduced directly: a 200-sentence synthetic document hung indefinitely; confirmed via a manual iteration-capped trace showing `i` stuck at the same value from iteration 10 onward). This is not a rare edge case — it triggers on the last chunk of essentially any document, including the real Apollodorus corpus. (2) **Size overshoot**: the literal "admit one more sentence after crossing `CHUNK_SIZE`" rule has no bound on how far over it can go — on the real corpus, a few chunks landed at 1834–2254 chars, exceeding the checklist's own `CHUNK_SIZE * 1.2` (1800) requirement (`docs/TODO-stage2.md` E5), driven by a genealogical passage with several 1000+ char run-on sentences. Both bugs were caught by running the planned tests to completion (the first hung the test run entirely) and by verifying end-to-end against the real ingested corpus rather than only synthetic short-sentence fixtures. |
| **Impact** | `ingestion/tests/test_text_chunker.py` gained two regression tests (`test_terminates_when_tail_has_exactly_overlap_sentences_left`, `test_terminates_when_a_single_sentence_exceeds_chunk_size`) alongside the originally planned E5 cases. Verified end-to-end against the real corpus: 260 chunks, max size 1508 chars (well under the 1800 cap), zero infinite loops, fully deterministic across repeated runs. No impact on `Chunk`'s field shape, `split_sentences()`, `_nearest_ref()`, or any other track's code — the fix is contained entirely within `chunk()`'s loop control. |

---

### DEV-013 — `embedding_pipeline.py`: dropped `numpy`, added real `embed_batch` batching

| Field | Detail |
|---|---|
| **Stage** | 2 (Track G) |
| **Original Plan** | `docs/IMPLEMENTATION_PLAN.md` §4, "`embedding_pipeline.py`" — snippet imports `numpy as np` and wraps each embedding in `np.array(embedding)` before the `INSERT`; `store_chunks(conn, chunks)` calls `embed_batch(texts)` once on the full `chunks` list with no batching loop, even though the plan's own prose directly below the snippet states "Batch size: 20 chunks per `embed_batch` call" |
| **What Changed** | (1) Removed `import numpy as np` / `np.array(...)` entirely — `embedding` (already `list[float]`, per `embed_batch`'s own return type) is passed straight to `cur.execute(...)`. (2) `store_chunks` now loops over `chunks` in slices of `BATCH_SIZE = 20`, calling `embed_batch` once per slice, matching the plan's stated batching requirement (and `docs/TODO-stage2.md` G2). |
| **Reason** | (1) `numpy` was never added to `ingestion/requirements.txt` in Track A (matching `CLAUDE.md`'s stated Python dependency list, which also omits it) — the module couldn't even be imported without it. Inspecting the installed `pgvector` package (`pgvector/vector.py`, `Vector.__init__`) confirmed it already handles a plain `list[float]` directly (`array('f', value)`) and only imports `numpy` lazily, inside a `try/except ImportError`, when actually given an `ndarray` — so wrapping in `np.array()` was both unsupported by the installed deps and functionally unnecessary. (2) The literal snippet's single unbatched `embed_batch(texts)` call contradicts the plan's own stated reasoning immediately below it ("100 chunks × 1500 chars ≈ 37,500 tokens and risks hitting OpenAI's per-request token limit") — verified with a mocked `embed_batch`/DB connection that batching was in fact missing from the snippet as written. |
| **Impact** | No new dependency added to `requirements.txt` (numpy dropped instead of added). Verified via mocked `psycopg2` connection + mocked `embed_batch`: 45 synthetic chunks correctly split into 3 `embed_batch` calls of `[20, 20, 5]`; `INSERT` executed once per chunk with correct `ON CONFLICT` clause and metadata JSON; `embedding` param is a plain list. `@retry` on `embed_batch` verified separately (2 simulated transient failures, succeeded on 3rd attempt). `validate_source_ids` and `clear_source_chunks` implemented as literally specified (only the `source_id` type hint corrected from the plan's stray `int` to `str`, matching `CLAUDE.md`'s documented TEXT-slug schema and `SourceConfig.source_id: str` from Track F — a trivial, non-functional annotation fix, not logged as its own entry). |

---

## Stages 4–8 — Conflict detection & surfacing pivot (2026-07-10)

### DEV-014 — Conflict becomes data-driven and router-independent (ADR-007)

| Field | Detail |
|---|---|
| **Stage** | 4 (extraction) and 5–8 (runtime) — pre-implementation amendment, none of the affected code was built at decision time |
| **Original Plan** | `IMPLEMENTATION_PLAN.md §4/§5`: conflict is a property of the *question*, decided by routing. `RouteDecision` includes a `CONFLICT` value; a dedicated `ConflictQueryHandler` is the only path that queries `variant_claims`; `conflict_detector.py` scans **relationships only**; the LLM `is_contested` flag drives which claims get stored. |
| **What Changed** | Conflict is reframed as a property of the *data* per **ADR-007** (`docs/adr/adr-007-conflict-detection-and-surfacing.md`, Accepted): **detection** is offline (a single GROUP-BY over *all* candidate claims keyed on `(subject, normalize(claim_type))` `HAVING count(DISTINCT source_id) >= 2`, backed by an open free-text `claim_type` + a `claim_type_aliases.json` normalization map), and the extractor stores **all** attributed claims, not only `is_contested` ones. **Surfacing** is a router-independent query-time enrichment in `QueryService`: after any answer, `ConflictProbe` → `ConflictLookup` (claim-type-filtered `variant_claims` fetch) → `ConflictSynthesizer`, writing only `conflicts[]`. `RouteDecision` becomes `SQL \| RAG \| MIXED` (drop `CONFLICT`); `ConflictQueryHandler` is deleted, its entity-resolution + fetch moving into a shared `ConflictLookup`; `RagAgent` gains a conflict-aware disagreement backstop instruction; contested relationships keep **one canonical edge** (spine-preferred) in `V11`, with the contradiction recorded in `V12`. |
| **Reason** | Routing cannot detect a data property it can only guess from question phrasing; a conflict-shaped question misrouted to SQL/RAG silently dropped its stored conflict — the exact failure the product exists to prevent. See ADR-007 §Context (three flaws) and §Rationale. |
| **Impact** | **Amends ADR-004** (open `claim_type` + generalized detector + store-all candidates; review gate and `trust_tier` semantics unchanged) and **ADR-005** (`QueryRouter` no longer emits `CONFLICT`; schema-boundary → RAG retained). Affects Stage 4 (`ingestion/extraction/`: `schema.py`, new `claim_type_aliases.json`, `claim_extractor.py`, `conflict_detector.py`; V11/V12 curation) and Stages 5–8 (`RouteDecision`, `QueryRouter` prompt, delete `ConflictQueryHandler`, add `ConflictLookup` + `ConflictProbe`, `QueryService` enrichment, `RagAgent` prompt) and Stage 10 (Q13–15 re-point `expected_route`; conflict scoring keys on `conflicts[]`, not a route match). `V7__create_variant_claims.sql` already satisfies the open-`claim_type` requirement (no CHECK) — no migration change needed. Affected TODO items are marked `[DEVIATED - see DEVIATIONS.md DEV-014]`; `IMPLEMENTATION_PLAN.md §3, §4 (incl. the Extraction-Pipeline subsection), §5, §7, §8, and the Stage 9 sequence block` and `ADR-005 §Decision.1` carry `⚠️ Amended by ADR-007` banners. `docs/TECH_GUARDRAILS.md` is reconciled directly: the "One handler per route" row now names three handlers plus the enrichment step (no `ConflictQueryHandler`), and the `pg_trgm`/`rapidfuzz` rows re-point their fuzzy-match reference from `ConflictQueryHandler` to the shared `ConflictLookup`. |

### DEV-018 — `V12` stores normalized canonical `claim_type`; Homeric Hymns author corrected to Anonymous

| Field | Detail |
|---|---|
| **Stage** | 4 (V12 curation) — pre-implementation clarification; V12 not yet built |
| **Original Plan** | (1) ADR-007 §5 / `IMPLEMENTATION_PLAN.md §3` specify runtime `ConflictLookup` as an exact-match `WHERE subject_entity_id = X AND claim_type = normalize(probeClaimType)`, but nothing stated how the stored `variant_claims.claim_type` is written at promotion — the detector's `GROUP BY normalize(claim_type)` framing implied surface variants could remain in the rows. (2) `IMPLEMENTATION_PLAN.md §3` V9 seed row sets the Homeric Hymns source `author='Hesiod'`. |
| **What Changed** | (1) `V12` promotion now **writes the normalized canonical `claim_type`** (applies `claim_type_aliases.json`'s `normalize()` to each candidate's surface label before insert), so both rows of a conflict share one `claim_type` and the runtime exact-match lookup returns them. Documented in CLAUDE.md's `variant_claims` comment, `IMPLEMENTATION_PLAN.md §3` ADR-007 banner, ADR-007 §5, and `TODO-stage4.md` C4. (2) The Homeric Hymns source `author` is corrected from `Hesiod` to `Anonymous ("Homeric")` in `TODO-stage4.md` C1 — the Hymns are conventionally anonymous; Evelyn-White's *volume* bundles them with Hesiod, but `sources.author` is the work's author, not the translator's volume. The `id` slug `hesiod-homeric-hymns` is **retained** as the plan specifies (it must match `SourceConfig.source_id`), so only the `author` field changes. |
| **Reason** | (1) Without the normalize-on-promotion rule, a reviewer could promote a conflict's two rows under different surface labels (e.g. `death_manner` + `manner_of_death`); the exact-match `ConflictLookup` would then return one row, silently dropping the conflict — the exact failure ADR-007 exists to prevent. (2) The product's core promise is accurate source attribution; mis-attributing the Homeric Hymns to Hesiod undermines it. |
| **Impact** | No schema change (V7 unchanged). `V12__seed_variant_claims.sql`, when written, must normalize `claim_type` at insert; `ConflictLookup` normalizes only the probe input, never the stored column. `V9__seed_sources.sql` uses `author='Anonymous'` (or `'Homeric'`) for `hesiod-homeric-hymns`. `IMPLEMENTATION_PLAN.md §3`'s V9 row keeps its original `author='Hesiod'` text per the deviation protocol (not overwritten); this entry records the correction. `TODO-stage4.md` C1/C4 marked `[DEVIATED - see DEVIATIONS.md DEV-018]`. |

### DEV-019 — Floor conflicts reframed as extraction-preferred (guaranteed seed presence, not guaranteed extraction) + separate extraction-quality metric

| Field | Detail |
|---|---|
| **Stage** | 4 (Track B review) — pre-implementation refinement; extraction not yet run |
| **Original Plan** | `TODO-stage4.md` B6 (and its source, ADR-007 §2 / ADR-004): the Aphrodite/Io/Achilles minimum-coverage floor is enforced by "hand-add any of these three that extraction missed; this floor is non-negotiable regardless of pipeline output." A single instruction conflated two concerns — (a) the runtime seed must contain these conflicts (a *surfacing* guarantee the demo and gold Q13–15 depend on), and (b) whether the extraction pipeline actually found them (a *quality* signal). Hand-adding silently satisfied (a) while erasing any measurement of (b). |
| **What Changed** | B6 is reframed to **extraction-preferred**: promote extracted floor conflicts as-is, hand-add only the misses, and record per conflict which path was used. The floor stays a hard guarantee **about the seeded data**, explicitly *not* a claim that extraction found them. A new **B7** adds a non-blocking extraction-quality metric that measures, against the raw `variant_claims_candidates.json` *before* any hand-add, how many of the **cross-source** floor conflicts the pipeline detected unaided (`N/2` — Aphrodite and Achilles only; misses named). **Io is structurally excluded from B7** because both its variants (Inachus vs Piren) are attributed to the single source Apollodorus (`IMPLEMENTATION_PLAN.md §7` Q14; ADR-004), so the `count(DISTINCT source_id) >= 2` detector can never emit it — Io is always hand-added and is not a pipeline miss. B7 is Python/offline (a `02_verify_conflicts.ipynb` cell or a small `ingestion/extraction/` pytest), never a core-api Testcontainers test. B6 also now names the death-key unification requirement explicitly (see below). |
| **Reason** | Conflating the two hid pipeline quality behind hand-curation and made the gold-question eval a test of extraction luck rather than of the surfacing pipeline. Splitting the layers keeps the eval deterministic (floor guaranteed in the seed) while giving an honest, separate read on extraction, and makes a pipeline miss diagnosable as such instead of surfacing as a red eval or a silent hand-patch. |
| **Impact** | No change to the floor's status as a hard requirement — ADR-007 §2 ("the minimum-coverage floor … remains a hard requirement") still holds for *seed presence*, so **no ADR amendment is needed**; this entry only refines how B6 is satisfied and adds B7's measurement. `TODO-stage4.md` B6/B7 marked `[DEVIATED - see DEVIATIONS.md DEV-019]`. **Open dependency:** B7 will report Achilles as a false miss until the death `claim_type` fragmentation is resolved — under the pre-DEV-020 draft, free-text death claims normalized to `death_manner` while relationship candidates mapped `killed_by → slaying` (`IMPLEMENTATION_PLAN.md §4`, DEV-014), so a single death disagreement split across two GROUP-BY keys and was never detected as a conflict. (ADR-007 §1 now maps both to a single `death` canonical; the `death_manner`/`slaying` split described here is the superseded state.) That canonical-key unification is **not** fixed by this entry — **→ resolved by DEV-020** (`killed_by` and free-text death claims both normalize to a single `death` canonical). |

### DEV-020 — Unify the death conflict-grouping key: `killed_by → death` (not `slaying`), one shared canonical namespace

| Field | Detail |
|---|---|
| **Stage** | 4 (extraction) / 7 (runtime lookup) — pre-implementation fix; resolves the open dependency flagged in DEV-019 |
| **Original Plan** | Per DEV-014 (ADR-007 §1, `IMPLEMENTATION_PLAN.md §4`, `TODO-stage4.md` A6), `conflict_detector.py` maps relationship candidates as `parent_of → parentage`, `married_to → marriage`, **`killed_by → slaying`**, while the `claim_type_aliases.json` example (A2b, ADR-007 §1) collapses free-text death prose (`death`, `manner_of_death`, `how he died`) to canonical **`death_manner`**. The death dimension therefore had two disjoint canonical keys — `slaying` (from typed `killed_by` edges) and `death_manner` (from free-text claims). |
| **What Changed** | The relation→claim_type map and the alias map are declared **one shared canonical namespace**: every relationship mapping must target a canonical that also owns the corresponding free-text surface forms. `killed_by` now maps to **`death`**, and `death` is the alias-map canonical collapsing both manner forms (`manner_of_death`, `how he died`) and killer forms (`slaying`, `slain by`, `killed by`). `parent_of → parentage` and `married_to → marriage` were already consistent and are unchanged. Edited: ADR-007 §1 (canonical value + a new shared-namespace paragraph), `IMPLEMENTATION_PLAN.md §4` extraction banner, `TODO-stage4.md` A2b/A6/B6/B7. |
| **Reason** | With two keys, the offline `GROUP BY (subject, normalize(claim_type)) HAVING count(DISTINCT source_id) >= 2` never groups a death disagreement that arrives half as a `killed_by` edge and half as free-text prose — each key holds one source, so **no conflict is detected**; and at query time the exact-match `ConflictLookup` fetches only one key, dropping the other version. This defeats the Achilles death floor conflict (B6, non-negotiable) and the re-pointed death gold question (Q13–15, scored on `conflicts[]`) — precisely the silent-flatten failure ADR-007 exists to prevent. It was also an internal inconsistency *within* ADR-007 (§1's `death_manner` vs its own `killed_by → slaying`). |
| **Impact** | No schema change (`variant_claims.claim_type` is open free-text; V7 unchanged). Unifying killer + manner under `death` is a **conflict-grouping** decision and is **orthogonal to ADR-005's routing split** — ADR-005 still routes "who killed whom" to SQL (`killed_by`) and "manner of death" to RAG; because surfacing is router-independent (ADR-007 §5), both phrasings probe to `death` and surface the same conflict. `V12` seeds the Achilles death versions under `claim_type='death'` (never `slaying`), consistent with DEV-018's normalize-on-promotion rule. `claim_type_aliases.json` (A2b) and its shared `normalize()` remain the single source of truth for both the offline detector and query-time `ConflictLookup`. Resolves the DEV-019 open dependency, so B7's `N/2` metric (Aphrodite, Achilles; Io structurally excluded as single-source — see DEV-019) now reflects true extraction coverage. The `killed_by → slaying` mapping is amended in place to `killed_by → death` in ADR-007 §1 and `TODO-stage4.md` A6 (ADR-007 §1 preserves the superseded `slaying` value in an explanatory note); per the deviation protocol `IMPLEMENTATION_PLAN.md`'s original body is not overwritten — its new §4 extraction banner records the `death` mapping. This entry supersedes the earlier mapping. |
| **Date** | 2026-07-10 |

---

## ADR-008 — Model selection update (2026-07-10)

### DEV-015 — Chat & extraction models → Anthropic; embedding reaffirmed (ADR-008)

| Field | Detail |
|---|---|
| **Stage** | 4 (offline extraction) and 5–8 (runtime chat) — pre-implementation amendment; the chat beans (`LangChain4jConfig.kt`) and the extraction pipeline (`claim_extractor.py`) are not yet built at decision time |
| **Original Plan** | `ADR-003` / `IMPLEMENTATION_PLAN.md §4, §5`: runtime chat model `gpt-4o-mini` (all five `@AiService` roles), offline seed-data extraction `gpt-4o`, embedding `text-embedding-3-small`. Single-vendor OpenAI; `LLM_API_KEY` and `OPENAI_API_KEY` point at the same key in Phase 1. |
| **What Changed** | Per **ADR-008** (`docs/adr/adr-008-model-selection-update.md`, amends ADR-003): runtime chat → **Claude Haiku 4.5** (`claude-haiku-4-5-20251001`) via a LangChain4j Anthropic bean; offline extraction → **Claude Opus 4.8** (`claude-opus-4-8`) via `instructor.from_anthropic`; embedding **reaffirmed** `text-embedding-3-small` (OpenAI, locked). The AI architecture is unchanged (five `@AiService` roles, per-role temps 0.0/0.3, provider-agnostic chat, locked embeddings). Now two vendors: `LLM_API_KEY` → Anthropic (chat), `OPENAI_API_KEY` → OpenAI (embeddings + ingestion) — no longer the same key. |
| **Reason** | The `gpt-4o` family is dated by mid-2026 and the swap is cheap. Concentrate quality where trust lives: cheap/fast Haiku 4.5 on the high-volume runtime path (strongest small-tier instruction-following / structured-output reliability, which this workload stresses), frontier Opus 4.8 on the one-time offline extraction (the attribution differentiator — a misattributed conflict undermines trust). See ADR-008 §Rationale. |
| **Impact** | **Applied now (existing files only, per the edit-existing-files-only scope):** `.env.example` (LLM_CHAT_MODEL + key split), `application-test.yml` chat-model, amendment banners on `ADR-003` and `IMPLEMENTATION_PLAN.md §4/§5`, `CLAUDE.md` + `TECH_GUARDRAILS.md` wording, `TODO-stage4.md` A5/A8, `TODO-stage1.md`. **Deferred to build stages (new files / unbuilt components):** add `langchain4j-anthropic-spring-boot-starter` to `core-api/build.gradle.kts` and wire `AnthropicChatModel` beans when `LangChain4jConfig.kt` is written (Stage 5); add `anthropic` to `ingestion/requirements.txt` and use `instructor.from_anthropic` + `ANTHROPIC_API_KEY` + `EXTRACTION_MODEL=claude-opus-4-8` when `claim_extractor.py` is written (Stage 4 A5/A8). **Keep `langchain4j-open-ai-spring-boot-starter` regardless** — the embedding bean still requires it. Embedding **escalation lever** unchanged: move to `-large` only if a pre-ingestion retrieval check on the hardest (list/numeric) questions shows `-small` is the bottleneck (ADR-008 §3). **Swap-after-eval:** run the gold set before committing to either Anthropic model (ADR-008 §5). **Companion — ADR-006 partial application:** the embedding single-source-of-truth `EMBEDDING_MODEL` wiring (`.env.example`, `ingestion/config.py`, `ingestion/pipeline/embedding_pipeline.py`, `application.yml`, `docker-compose.full.yml`) is applied now (ADR-006 §1); ADR-006's remaining, new-file items stay deferred to their build stages — `V15__add_embedding_model_tracking.sql` + the `embedding_model` column in `store_chunks()`'s INSERT, `EmbeddingConsistencyChecker.kt`, `canary-aphrodite.json` + `EmbeddingConsistencyTest.kt`, `LangChain4jConfig.kt` embedding-model injection, and the §10 `EXPLAIN ANALYZE` index-usage check. |
| **Date** | 2026-07-10 |

---

## Cross-stage design review fixes (2026-07-12)

> DEV-016 and DEV-017 are reserved by ADR-009 and ADR-010's action items and intentionally skipped here.

### DEV-021 — `variant_claims` and `relationships` gain a `passage_ref` provenance column (V8_1)

| Field | Detail |
|---|---|
| **Stage** | 1c (schema, post-hoc migration) / 4 (extraction models, V11/V12 — pre-implementation) |
| **Original Plan** | `IMPLEMENTATION_PLAN.md §3` V4/V7: `relationships` and `variant_claims` carry only `source_id` — attribution stops at the work level. `TODO-stage4.md` A1's Pydantic models (`ExtractedRelationship`, `ExtractedVariantClaim`) have no passage field. |
| **What Changed** | New `V8_1__add_claim_provenance.sql` adds nullable `passage_ref TEXT` to both tables (a new migration, not an edit to committed V4/V7 — the dev DB already carries their checksums). Stage 4's extraction models gain a `passage_ref` field **populated mechanically from the A4 segment boundaries, never by the LLM**; V11/V12 seed rows carry it through. |
| **Reason** | Provenance gap in the flagship feature: extraction runs on passage-ref-aligned segments, so the ref is known at extraction time but was dropped at the exact point that matters most. A RAG answer could cite "Apollodorus, Bibliotheca 2.1.3" while a surfaced conflict — the product's differentiator — could only cite the whole work. The B5 review workflow also needs the ref to verify each candidate against its passage. Adding the column after V12 is seeded would mean re-reviewing every promoted row; adding it now is nearly free. |
| **Impact** | `TODO-stage4.md` A1/A7/C3/C4 updated (extraction output and V11/V12 inserts carry `passage_ref`); `FlywayMigrationTest` asserts the new columns; `Citation`/`ConflictEntry` DTOs (Track E) may surface it in Stage 7+ but are not required to yet. Nullable, so hand-added rows without a precise ref remain valid. |
| **Date** | 2026-07-12 |

### DEV-022 — `claim_type_aliases.json` → `claim_type_aliases` DB table (V8_2)

| Field | Detail |
|---|---|
| **Stage** | 4 (extraction/detector) / 7 (runtime `ConflictLookup`) — pre-implementation |
| **Original Plan** | ADR-007 §1 / `TODO-stage4.md` A2b (per DEV-014): the canonical→surface-variant map lives in `ingestion/extraction/claim_type_aliases.json` with a shared `normalize()` helper, used by the offline Python detector **and** query-time Kotlin `ConflictLookup` — "keep it a single shared source of truth". |
| **What Changed** | The map is a Postgres table, `claim_type_aliases(alias PRIMARY KEY, canonical)`, created and seeded by `V8_2__create_claim_type_aliases.sql` with the documented namespace (DEV-020: `parent_of`/`parents` → `parentage`, `married_to` → `marriage`, `killed_by`/`killed by`/`slain by`/`slaying`/`death_manner`/`manner_of_death`/`how he died` → `death`). `normalize(x)` = canonical where `alias = lower(trim(x))`, identity otherwise. Python (extraction) and Kotlin (`ConflictLookup`) each implement the trivial lookup but read the **same rows**. Surface variants discovered during Stage 4 extraction are appended via follow-up migrations. |
| **Reason** | A JSON file under `ingestion/extraction/` is not naturally readable from `core-api` — the "single shared source of truth" instruction would in practice have produced two copies and two drifting `normalize()` implementations across languages. Both sides already talk to the same Postgres; the DB is the project's declared single source of truth. Each future claim type lands in one place. |
| **Impact** | `TODO-stage4.md` A2b/A6/B6/C4 and `TODO.md` Stage 4/7 re-pointed from the JSON file to the table; `CLAUDE.md` data model updated. `known_aliases.json` (A2, entity aliases) is unaffected — it feeds hand-curated V14. ADR-007's normalize-at-promotion rule (DEV-018) is unchanged; only the map's storage moves. `afterMigrate__grant_app_user.sql` already grants `zeus_app` SELECT on all tables, covering the new one. |
| **Date** | 2026-07-12 |

### DEV-023 — `SchemaIntrospector`: auto-enumerated tables + self-describing schema prompt

| Field | Detail |
|---|---|
| **Stage** | 1c (implemented class) / 5 (text-to-SQL prompt consumer) |
| **Original Plan** | `IMPLEMENTATION_PLAN.md §5`: `SchemaIntrospector` iterates a **hardcoded** `listOf("entities", …)` and emits only column names per table. ADR-009's action items include "register the table in SchemaIntrospector" — a hand-maintained list. |
| **What Changed** | Tables are now enumerated from `information_schema` (public base tables minus an `EXCLUDED_TABLES` set holding only `flyway_schema_history`), so new migrations appear in the prompt automatically. Each table now also emits: column **types**, foreign keys (`col references table(col)`), CHECK constraint clauses (surfacing the `entities.type` / `sources.stance`/`role` vocabularies), `COMMENT ON` text (new `V8_3__add_schema_comments.sql` adds query-semantics comments, e.g. "entities attributes carry NO source attribution — never join sources"), and live `SELECT DISTINCT` value vocabularies for `relationships.relation` and `variant_claims.claim_type`. `SchemaIntrospectorTest` gains a parity test (every non-excluded public table must appear) plus FK/CHECK/comment/vocabulary assertions. |
| **Reason** | The hardcoded list was the expansion mechanism's weakest link — a forgotten registration silently hides a new table from the router/text-to-SQL, exactly the drift failure ADR-005 rejected for the router. And a names-only prompt forces the model to guess magic strings (`married_to` vs `spouse_of`) and hand-listed join rules; emitting CHECKs, comments, and live vocabularies makes those derivable from the schema itself. |
| **Impact** | ADR-009's "register the table in SchemaIntrospector" action item becomes a no-op (the table self-registers; only its `COMMENT ON` guidance is worth adding). The `TextToSqlAgent` prompt (Stage 5) can lean on schema comments instead of accumulating hand-written per-table rules. The vocabulary and check clause emission runs once at startup (lazy cache), after Flyway seeds. |
| **Date** | 2026-07-12 |

### DEV-024 — `embedding_pipeline.py`: skip-before-embed + per-batch commits

| Field | Detail |
|---|---|
| **Stage** | 2 (amends the implemented Track G code; follows DEV-013) |
| **Original Plan** | `IMPLEMENTATION_PLAN.md §4`: re-run safety relies on `ON CONFLICT (source_id, passage_ref, content_hash) DO NOTHING`, with a single `conn.commit()` at the end of `store_chunks`. |
| **What Changed** | `store_chunks` now (1) pre-computes `md5(content)` in Python (`content_hash()`, matching the Postgres generated column byte-for-byte), fetches existing `(source_id, passage_ref, content_hash)` keys, and **filters already-stored chunks out before calling the OpenAI embeddings API**; (2) commits **per 20-chunk batch** instead of once at the end. `ON CONFLICT DO NOTHING` stays as the race/edge backstop. New `tests/test_embedding_pipeline.py` covers hash parity, skip behavior, and per-batch commit counts. |
| **Reason** | `ON CONFLICT` dedupes at insert time, but embeddings are computed *before* the insert — every re-run paid the full OpenAI bill for the whole corpus, and the single end-of-run commit meant a crash lost everything (the plan's own "mid-run crash recovery" rationale for the UNIQUE constraint never actually worked: nothing was committed until the end). Matters more as the corpus grows past Apollodorus in Stage 3. |
| **Impact** | Re-running ingestion on an unchanged corpus now makes zero OpenAI calls. A mid-run crash loses at most one batch. Behavior after changing chunk params still requires `clear_source_chunks()` first, unchanged. No interface changes — `main.py` (still unbuilt) calls `store_chunks` exactly as planned. |
| **Date** | 2026-07-12 |

### DEV-025 — Stage 6 drops `PgVectorEmbeddingStore` for a custom `ContentRetriever` over `JdbcTemplate`

| Field | Detail |
|---|---|
| **Stage** | 6 (RAG pipeline) — pre-implementation |
| **Original Plan** | `IMPLEMENTATION_PLAN.md §5` LangChain4j beans: `PgVectorEmbeddingStore.builder().table("narrative_chunks").dimension(1536).createTable(false).build()` + `EmbeddingStoreContentRetriever`. |
| **What Changed** | Stage 6 will implement a small custom `ContentRetriever` (embed the query via the `EmbeddingModel` bean, then `JdbcTemplate` cosine query `ORDER BY embedding <=> ? LIMIT 5` with a `minScore` filter over `narrative_chunks`) instead of the `PgVectorEmbeddingStore`/`EmbeddingStoreContentRetriever` beans. `langchain4j-pgvector` can be dropped from `build.gradle.kts` at that point. |
| **Reason** | **Verified against the pinned `langchain4j-pgvector:1.0.0-beta5` jar** (string constants in `PgVectorEmbeddingStore.class`): the store hardcodes its own schema — `embedding_id UUID PRIMARY KEY, embedding, text, metadata` — in `CREATE TABLE`, `INSERT`, and retrieval `SELECT` statements, with no column-name mapping. Our table has `id SERIAL` and `content`; every retrieval would fail with `column "text" does not exist`. A custom retriever also gives source filtering and citation columns (`source_id`, `passage_ref`) directly in the retrieval query, which the generic store cannot. |
| **Impact** | `TODO.md` Stage 6 bean item replaced. The `EmbeddingModel` bean and `RagAgent` wiring are unchanged; `maxResults=5` / `minScore=0.65` move into the custom retriever. The ADR-006 `EXPLAIN ANALYZE` HNSW check applies to the custom query. Alternative (a mapping view or renaming our columns) rejected: the store's `embedding_id UUID` PK is incompatible with `id SERIAL` regardless of names. |
| **Date** | 2026-07-12 |

### DEV-026 — ADR-005 empty-result fallback extended to aggregate-zero results

| Field | Detail |
|---|---|
| **Stage** | 5 (`SqlQueryHandler`) — pre-implementation |
| **Original Plan** | ADR-005 §Decision.3: `SqlQueryHandler` falls back to RAG when the generated SQL returns **zero rows**. |
| **What Changed** | The fallback also treats an **aggregate-zero** result as empty: a single row whose values are all `0` / `NULL` (e.g. `COUNT(*)` = 0, `SUM(...)` = NULL). Added as an explicit Stage 5 TODO bullet (the fallback itself was missing from `TODO.md` Stage 5 entirely — also fixed). |
| **Reason** | Aggregations never return zero rows: `COUNT` over an empty match returns one row containing `0`. Once ADR-009's numeric data lands, "how many ships from ⟨place not in the table⟩" would return a confident "0" instead of falling back — the exact silent-wrong-answer failure ADR-005 §Decision.3 exists to catch. |
| **Impact** | ADR-005 §Decision.3 carries an amendment note. Genuine zeros (a real count of 0 among matched rows) are indistinguishable from no-data zeros at this layer; falling back to RAG for both is acceptable for the PoC — RAG answers with cited text or refuses, which beats a fabricated-confidence number. |
| **Date** | 2026-07-12 |

## Stage 2 — Ingestion verification (2026-07-13)

### DEV-027 — Track I verified standalone via hand-inserted `sources` row (ordering gotcha resolved)

| Field | Detail |
|---|---|
| **Stage** | 2 (Ingestion Setup) — Track I verification |
| **Original Plan** | `main.py`'s `validate_source_ids()` requires `apollodorus-bibliotheca` to already exist in `sources`, but the migration that seeds `sources` (`V9__seed_sources.sql`) belongs to Stage 4, which runs after Stage 2. `docs/TODO-stage2.md`'s "ordering gotcha" note pre-approved hand-inserting the row to verify Stage 2 standalone, rather than pulling `V9` forward. |
| **What Changed** | Ran `docker exec blame-zeus-postgres-1 psql -U zeus -d blamezeus` with `INSERT INTO sources (id, author, work, translation, stance, year_published, role) VALUES ('apollodorus-bibliotheca', 'Apollodorus', 'Bibliotheca', 'Frazer', 'mythographic-handbook', 1921, 'spine') ON CONFLICT (id) DO NOTHING;` against the local dev DB (Flyway V1–V8_3 applied by booting `core-api` once with placeholder LLM env vars, since no standalone `flywayMigrate` Gradle task is configured — only `flyway-core` as a library dependency). `python main.py` then ran successfully: 260 chunks written to `narrative_chunks` for `apollodorus-bibliotheca`, all embeddings populated, 0 fallback `passage_ref`s. A second run confirmed idempotency (`Skipping 260 of 260 chunks already embedded`, row count unchanged). |
| **Reason** | Exactly the workaround `TODO-stage2.md` flagged in advance — this entry just confirms it was executed and verified, per `CLAUDE.md`'s Deviation Tracking Protocol requirement to log it "when Stage 2 is actually implemented." |
| **Impact** | None on schema or code. The local dev DB now has one manually-inserted `sources` row; Stage 4's `V9` will later insert the identical row with the same `ON CONFLICT DO NOTHING`, so no cleanup is needed. Track I (`docs/TODO-stage2.md`) is now fully verified: I1–I7 complete. |
| **Date** | 2026-07-13 |

## Stage 2 follow-up — embedding model switch (2026-07-13)

### DEV-028 — Embedding model switched to `text-embedding-3-large` (3072-dim); ADR-006's `V15` renumbered into `V8_4`

| Field | Detail |
|---|---|
| **Stage** | 2 (post-verification, cross-cutting: schema + ingestion + config) |
| **Original Plan** | `text-embedding-3-small`, 1536 dims, "fixed — not swappable without re-ingesting the full corpus" (ADR-003, reaffirmed by ADR-008 §3); `V8`'s plain-vector HNSW index; ADR-006 §2's `embedding_model` tracking column deferred as a future `V15__add_embedding_model_tracking.sql`. |
| **What Changed** | Switched to `text-embedding-3-large` at native 3072 dims per **ADR-013** (supersedes the embedding portion of ADR-003/ADR-008; chat model untouched). New migration `V8_4__switch_embedding_to_3large_3072.sql`: `TRUNCATE narrative_chunks` → `vector(3072)` → HNSW rebuilt as a **halfvec expression index** (`(embedding::halfvec(3072)) halfvec_cosine_ops`, named `narrative_chunks_embedding_hnsw_idx`) → adds `embedding_model TEXT NOT NULL` (no default). ADR-006's `V15` thereby lands early, **renumbered into the `V8_x` amendment series** — resolving `TODO.md` Stage 3's flagged ordering hazard (a `V15` applied before the unwritten `V9`–`V14` breaks Flyway's in-order validation) via the renumber option that item pre-authorized. `store_chunks()`'s INSERT now stamps `embedding_model = config.EMBEDDING_MODEL` (TDD: `test_insert_stamps_embedding_model`). `EMBEDDING_MODEL` flipped to `text-embedding-3-large` in `.env`/`.env.example` and the defaults in `application.yml`, `application-test.yml`, `docker-compose.full.yml`. Corpus re-embedded (260 Apollodorus chunks, ~$0.01). |
| **Reason** | pgvector's plain-`vector` HNSW caps at 2000 dims, so `-large`'s 3072 dims can't reuse `V8`'s index shape (local pgvector is 0.8.4, which supports halfvec indexing). Escalating now is the cheapest it will ever be: 260 chunks, one source, and no Kotlin embedding consumer built yet (`LangChain4jConfig.kt` is Stage 6). The `TRUNCATE` is required because DEV-024's skip-before-embed dedup keys on model-agnostic `content_hash` — without it a re-run would skip all chunks and re-embed nothing. Truncating to 1536 via the `dimensions` param was rejected as institutionalizing ADR-006's "dimension match ≠ model match" trap (full alternatives in ADR-013). |
| **Impact** | **Stage 6's custom `ContentRetriever` (DEV-025) must cast in the ORDER BY** — `ORDER BY embedding::halfvec(3072) <=> ($1::vector(3072))::halfvec(3072)` — or the expression index is silently bypassed (seq scan); DEV-025's query sketch and `TODO.md` Stage 6 updated accordingly, and ADR-006 §5's `EXPLAIN` check now applies to the cast form. The `canary-aphrodite.json` golden fixture (Stage 6) must be generated with `-large`. `TODO.md` Stage 3's `V15` item closes as done-in-`V8_4`. `NarrativeChunk.kt` (Stage 4, D6) must leave `embedding_model` unmapped like `embedding`, or map it read-only. Storage: 12 KB/vector vs 6 KB (~3 MB total today). Embedding cost $0.02→$0.13/M tokens — irrelevant at PoC scale. |
| **Date** | 2026-07-13 |

## Stage 3 — Full corpus indexing (2026-07-13)

### DEV-029 — Real corpus uses bare `[N]` line markers, not the plan's `[ll. N-M]` ranges; `text_cleaner` collided with them; extractors emit standard citation form instead of raw scraped form

| Field | Detail |
|---|---|
| **Stage** | 3 (Full Corpus) — Tracks B, C, D |
| **Original Plan** | `IMPLEMENTATION_PLAN.md §4`'s marker table assumed `[ll. 116-138]`-style range markers for Theogony/Hymns/Homer, with a literal `ll?\.` prefix, `HYMN\s+([IVXLCDM]+)\.\s+TO\s+(\w+)` for hymn headers, and `BOOK\s+([IVXLCDM]+)` (Roman numerals) for Homer/Ovid book headers. `TODO-stage3.md` Track B additionally planned a `preserve_line: re.Pattern` parameter threaded through `SourceConfig`/`clean()`/`main.py` to fix the header-stripping collision it had already flagged in Gotcha #2. |
| **What Changed** | Inspected the real downloaded corpus files (all 6, via `theoi.com`) directly instead of continuing to build against the plan's unverified regex table. Findings: (1) every source but Apollodorus marks line-starts with a **bare bracketed integer** (`[90]`, `[1]`, `[21]`) — no `ll.`/`l.` prefix, no ranges. (2) Homeric Hymns headers are `I. TO DIONYSUS`, `II. TO DEMETER`, … — no literal word "HYMN" per entry. (3) Iliad/Odyssey/Ovid `BOOK` headers are **Arabic** (`BOOK 1`, not `BOOK I`). (4) `text_cleaner.py`'s `_FOOTNOTE_MARKER = r"\[\d+\]"` was therefore silently deleting every one of these bare line markers before any extractor could run (footnotes and line markers are the same bracket-digit shape; the only structural difference in the source is that footnotes are always attached directly to the preceding word/punctuation with no space, while line markers sit at true line-start) — fixed via a lookbehind (`(?<=\S)\[\d+\]`) instead of the planned `preserve_line` parameter (no `SourceConfig`/`clean()`/`main.py` signature change needed). (5) `_PAGE_HEADER_LINE`'s ALL-CAPS filter was also deleting legitimate in-body section titles in **every** source, not just Ovid (Theogony's `THE TITANOMACHY`, the Iliad's `THE CATALOGUE OF SHIPS`, etc.) — fixed by restricting the filter to the metadata preamble before the first structural marker, rather than per-source pattern lists. (6) Extractors (`hesiod_theogony_refs`, `hesiod_homeric_hymns_refs`, `book_line_refs` — one function shared by Iliad/Odyssey/Ovid, not three) emit the **standard modern citation form** for each work instead of echoing the scraped bracket shape: plain line number for Theogony (no book division; `"116"`), `"{hymn}.{line}"` for the Hymns with the header's Roman numeral converted to Arabic (`"2.90"`), and `"{book}.{line}"` for Iliad/Odyssey/Ovid (`"1.194"`, `"9.105"`, `"1.89"`) — matching Perseus/OCD/TLG citation practice (`Il. 1.194`, `Met. 1.89`, etc.), which the plan's raw-range format did not. (7) Registered all 5 `SourceConfig` entries against the **actual** file names on disk, which differ from the plan/TODO-stage3 in two ways the corpus download already resolved correctly: Murray's translation years are `homer_iliad_murray1924.txt` / `homer_odyssey_murray1919.txt` (the plan's `V9` seed and `TODO-stage3.md` A3/A4 have these years swapped — real-world Loeb history is Iliad 1924, Odyssey 1919), and Ovid is `ovid_metamorphoses_more1922.txt` (Brookes More, 1922) rather than the plan's placeholder `ovid_metamorphoses_pd.txt`/`translation='PD'`. |
| **Reason** | The plan's regex table and `TODO-stage3.md`'s Track A/B/C design were, by the project's own admission (`TODO-stage3.md`'s opening note, echoing DEV-011), "hypotheses about file formats the plan's author never inspected." Verifying against the real files first — rather than implementing the planned regexes and discovering at Track F ingestion that 5 of 6 sources emit zero refs — avoided exactly the "every chunk silently falls back to `f'{author}, {work}'`" failure `TODO-stage3.md` Gotcha #2 and Track G2 warn about. Emitting standard citation form (vs. the raw scraped shape) was a direct requirement: the product's differentiator is source attribution, and `"1.194"`/`"Il. 1.194"`-style refs are how these works are actually cited in scholarship, not `"[194]"`. |
| **Impact** | `ingestion/loader/text_cleaner.py`: `_FOOTNOTE_MARKER` and `_PAGE_HEADER_LINE` changed as described; no new parameters, `SourceConfig` unchanged from Stage 2's shape (`preserve_line` from `TODO-stage3.md` Track B is not needed and not added). `ingestion/loader/source_registry.py`: 3 new extractor functions + all 6 `SOURCE_REGISTRY` entries now present. `ingestion/tests/test_text_cleaner.py` and `test_passage_ref_extractors.py` extended accordingly; `test_text_chunker.py` unaffected. Apollodorus's `apollodorus_refs`/existing 260 stored chunks are untouched (its markers are dotted, never matched the footnote regex either before or after this fix). Full-corpus dry run (`clean()` → extractor, no DB writes) against the real files: Apollodorus 386 refs (unchanged), Theogony 85 refs (`"1"`…`"1021"`, matching the poem's real ~1022-line length), Hymns 166 refs (`"1.1"`…`"33.1"`), Iliad 1138 refs (`"1.1"`…`"24.788"`), Odyssey 882 refs (`"1.1"`…`"24.545"`), Ovid 669 refs (`"1.1"`…`"15.871"`) — book/line ranges all land within each poem's known real extent, cross-checked as a sanity signal. `V9__seed_sources.sql` (Stage 4, not yet written) must use the corrected Murray years and a real Ovid translator/year, not the plan's placeholders. `TODO-stage3.md` Tracks B, C, D, and Gotcha #1's insert (Ovid row) are superseded by this entry — mark them `[DEVIATED - see DEVIATIONS.md #DEV-029]` rather than followed literally. **Addendum (2026-07-13):** the citation-notation choice in point (6) — standard scholarly form over the raw scraped shape — is now formalized as **ADR-014**, since no prior doc had ever stated a citation-standard rationale for `passage_ref`. |
| **Date** | 2026-07-13 |

### DEV-030 — Track E `sources` hand-insert executed; Gotcha #1's own SQL template had the same Murray-year swap DEV-029 already fixed elsewhere

| Field | Detail |
|---|---|
| **Stage** | 3 (Full Corpus) — Track E |
| **Original Plan** | `TODO-stage3.md` Gotcha #1 pre-authorized (per the DEV-027 precedent) hand-inserting the 5 non-Apollodorus `sources` rows ahead of Stage 4's `V9__seed_sources.sql`, so `main.py`'s `validate_source_ids()` fast-fail doesn't block Track F (full ingestion run). Its SQL template used placeholder `<TRANSLATOR>`/`<YEAR>` for the Ovid row and, independently, gave `homer-iliad`/`homer-odyssey` `year_published` 1919/1924. |
| **What Changed** | Before executing the insert, noticed the Gotcha #1 template's Iliad/Odyssey years were swapped — the exact same bug DEV-029 already corrected in `TODO-stage4.md` C1 (real files are `homer_iliad_murray1924.txt` / `homer_odyssey_murray1919.txt`), just not propagated to this second copy of the same 5 rows. Corrected the template in place (Iliad→1924, Odyssey→1919, Ovid→`'Brookes More'`/1922) before running it, then executed via `docker exec blame-zeus-postgres-1 psql -U zeus -d blamezeus`. Verified `SELECT id, author, work, translation, stance, year_published, role FROM sources ORDER BY id` returns all 6 rows with the corrected values. Also added the `stance` column (previously undocumented) to `TODO-stage4.md` C1's row list per Gotcha #1's own E2 instruction, so `V9` has one authoritative copy of all 7 columns instead of two partially-diverging copies. |
| **Reason** | Two independent hand-written copies of the same 5 rows (Gotcha #1's SQL template and `TODO-stage4.md` C1's prose list) drifted out of sync after DEV-029 fixed only one of them — a direct instance of the class of bug DEV-029 itself was about (plan data not verified/propagated). Fixing it before, not after, executing the INSERT avoids seeding the dev DB with wrong `year_published` values that Track F's ingestion and later `V9` would then have to reconcile against. |
| **Impact** | Dev DB `sources` table now has all 6 rows (Apollodorus from DEV-027, 5 more from this entry). `TODO-stage3.md` Track E marked done (E1, E2); `[DEVIATED]` tag added to Track E's header pointing here. `TODO-stage4.md` C1 now carries `stance` alongside `author`/`work`/`translation`/`year_published`/`role`, and is flagged `[DEVIATED - see DEVIATIONS.md #DEV-030]` — `V9__seed_sources.sql` must reproduce these 6 rows verbatim (its `ON CONFLICT DO NOTHING` then no-ops against the hand-inserted ones, same pattern as DEV-027's Apollodorus row). No schema or code change. |
| **Date** | 2026-07-13 |

### DEV-031 — Full-corpus ingestion run (Track F); DEV-029's "Apollodorus untouched" claim was wrong — `_PAGE_HEADER_LINE`'s widened class also strips Apollodorus's own title line

| Field | Detail |
|---|---|
| **Stage** | 3 (Full Corpus) — Track F (ingestion run) + Track G (verification) |
| **Original Plan** | `TODO-stage3.md` F2 expected console output `Skipping 260 of 260…` for Apollodorus (proving DEV-029's cleaning change was byte-identical for it) followed by fresh inserts for the 5 new sources. G4 pre-authorized the remedy if that invariant broke: `clear_source_chunks()` + re-embed once, logged as a DEV entry. |
| **What Changed** | Ran `python main.py` against all 6 sources (env: `ingestion/.venv`, `.env` at repo root). Apollodorus printed `Skipping 236 of 260…`, not `260 of 260` — row count came out as 284, not 260. Root-caused by diffing `clean()` output byte-for-byte between the pre-DEV-029 version (recovered via `git show ddce25f:ingestion/loader/text_cleaner.py`) and the current version, both run against the real `apollodorus_bibliotheca_frazer1921.txt`: the first divergence is character 0 — DEV-029's widened `_PAGE_HEADER_LINE` (`^[A-Z\s]+$` → `^[A-Z\s,()'\-]+$`, added to strip punctuated preamble titles like `"OVID, METAMORPHOSES"`) now *also* strips Apollodorus's own title line, `"APOLLODORUS, THE LIBRARY (BIBLIOTHECA)"` (which the old, narrower regex left in place — it contains a comma and parens the old class didn't match). DEV-029's claim that Apollodorus was untouched only checked the footnote-marker regex change; it never re-verified the page-header regex change against Apollodorus specifically. Stripping that line shifts every downstream character offset by ~39 chars, desyncing chunk boundaries for a stretch of the document until the chunker naturally resyncs on a later paragraph break — producing 24 chunks with new `content_hash`es that `ON CONFLICT DO NOTHING` inserted as *extra* rows (stale + fresh side by side for the same `passage_ref`s) rather than replacing the old ones, since the constraint dedupes exact matches only. Confirmed via `SELECT passage_ref, count(*) ... HAVING count(*) > 1` (e.g. `1.6.3` had 5 rows) and inspecting two rows directly — same passage, different chunk boundaries, both attributed correctly but overlapping. Remediated per G4's pre-authorized path: user confirmed proceeding, then `clear_source_chunks(conn, 'apollodorus-bibliotheca')` (260 old rows deleted) followed by a re-run, which re-embedded Apollodorus fresh under the corrected cleaning logic — landed back at exactly 260 rows (the shift this time resynced to the same total, though individual chunk boundaries/hashes differ from the original Stage-2 embedding). Confirmed idempotent: a third `python main.py` run skipped all 3037 rows across all 6 sources with no changes. |
| **Reason** | The new page-header behavior is correct — Apollodorus's title line is exactly the same class of preamble boilerplate DEV-029 already strips for the other 5 sources (Ovid's `"OVID, METAMORPHOSES"` is the direct precedent, covered by `test_preserves_all_caps_section_titles_after_first_structural_marker`). The bug was in DEV-029's *verification*, not its code: the claim "never matched the footnote regex either before or after" was true but incomplete — it didn't check the page-header regex against Apollodorus at all. This is exactly the gap Track G's `G4` (Apollodorus immutability re-run check) was written to catch, and it did. |
| **Impact** | No code or schema change — the DEV-029 regex behavior stands as correct; this entry only corrects the record and documents the DB remediation. Final state, all verified against the live DB: **3037 total chunks** — Apollodorus 260, Theogony 57, Homeric Hymns 126, Iliad 1112, Odyssey 724, Ovid 758 (`TODO-stage3.md` G1). `G2`'s corrected per-source fallback-ref audit (see DEV-030's sibling fix in `TODO-stage3.md`) found exactly one suspicious row per source (two for Theogony) — all confirmed legitimate metadata-preamble fallback chunks (translator credit + source URL, before each file's first structural marker), zero extractor misses (`G2`). Spot-checked 6 real refs across all 6 sources against their actual passage content — all correct (`G3`, e.g. Iliad `9.114` embassy-gifts passage, Theogony `116` cosmogony hills passage, Odyssey `24.520` Athena-invocation passage). `G5`: single `embedding_model = text-embedding-3-large` across all 3037 rows; `EXPLAIN` confirms `Index Scan using narrative_chunks_embedding_hnsw_idx` is used for the halfvec-cast similarity query. `TODO-stage3.md` F1/F2/G1–G5 marked done; the Stage-3 "Done when" bar (all 6 sources indexed, non-zero, real passage refs) is met. |
| **Date** | 2026-07-13 |

### DEV-032 — Raw `[N]`-shaped passage markers were leaking into stored/embedded `narrative_chunks.content`; stripped post-ref-resolution in the chunker, all 6 sources re-embedded

| Field | Detail |
|---|---|
| **Stage** | 3 (Full Corpus) — `chunker/text_chunker.py`, post-Track-F data quality |
| **Original Plan** | Neither `IMPLEMENTATION_PLAN.md §4` nor any test ever specified whether the raw scraped marker (`[90]`, `[1.1.1]`, etc.) should be stripped from a chunk's stored `content` once its `passage_ref` is resolved — the plan only describes using markers to *compute* offsets/refs (`"the chunker uses these to assign the most-recently-seen ref to each chunk"`). `text_chunker.py`'s `chunk()` builds `chunk_text` by directly joining sentence slices from the marker-preserved cleaned text (a DEV-029 prerequisite — extractors need the markers present to compute offsets) and never removed them afterward. |
| **What Changed** | User manually inspecting query output noticed markers embedded mid-sentence in stored content (e.g. Iliad `9.114`'s chunk contained `"...Argive Helen. [141] \"And if we return to Achaean Argos..."`). Quantified across the live DB: 90%+ of chunks in the 5 non-Apollodorus sources contained at least one leaked bare `[N]` marker (avg 1.2–2.1 per chunk, up to 7 in one chunk); Apollodorus was affected identically in kind but far less visibly (its `[book.chapter.section]` markers only land once, at a chunk's own start, since it marks section starts rather than every verse line). Fixed in `chunker/text_chunker.py`: added `_EMBEDDED_MARKER = re.compile(r"\[+(?:E\.)?\d+(?:\.\d+)*[a-z]?\]\s*")`, applied via `.sub("", ...)` to the joined chunk text (plus `.strip()`) right after `passage_ref` is resolved via `_nearest_ref`, so ref-computation still runs against the original marker-intact text (offsets/sentence-overlap logic untouched) and only the *stored* text is post-processed. The regex was built and validated against every real bracket shape actually present in the 6 corpus files (checked via `grep -ohE '\[[^]0-9][^]]*\]'` and similar) before wiring it in: matches bare `[90]`, dotted `[1.1.1]`/`[E.1.1]`, trailing-letter `[E.6.15a]`/`[929a]`, and the `[[219]`/`[[713]`-style doubled-open-bracket OCR glitches found in the Ovid file (`\[+` — one-or-more leading brackets) — while leaving genuine translator editorial brackets untouched (`[Jason]`, `[Medea]`, `[Zeus speaking:]`, `[from Euboea]`, and a full-sentence stage direction in Apollodorus's Epitome), since none of those start with a digit or `E.`. Added `test_embedded_markers_stripped_from_stored_chunk_text` and `test_editorial_brackets_are_not_stripped` to `test_text_chunker.py` (48 tests passing total). Dry-run against all 6 real corpus files confirmed: identical chunk counts to before (260/57/126/1112/724/758 — the fix changes chunk *content*, not chunk *boundaries*), zero leftover digit-brackets in any chunk, both editorial-bracket examples survived verbatim. Cleared and re-embedded all 6 sources (not just the 5 visibly-affected ones, for consistency — Apollodorus had already been re-embedded once this session per DEV-031, so the marginal cost of doing it again was small). Post-re-embed: same 3037-row total and per-source counts as DEV-031's baseline, zero leftover markers confirmed via DB query, idempotent re-run confirmed (`Skipping N of N` for all 6), `G2` fallback-audit counts unchanged from DEV-031's verified baseline. |
| **Reason** | This directly undermines ADR-014's stated goal — `passage_ref` exists precisely so the raw scraped marker doesn't need to appear in user-facing text, but the marker was leaking into `content` anyway, which is both (a) noise in the text actually sent to the embedding model, and (b) a real risk of a visible artifact (`"...[141] \"And if..."`) if `RagAgent` ever quotes `content` verbatim in a synthesized answer — exactly the kind of rough edge the product's "clean, attributed citation" positioning is meant to avoid. The bug predates this session (Apollodorus has had the same issue since Stage 2), but was low-visibility there since Apollodorus's markers are sparse (once per section); DEV-029 made it far more damaging by adding 5 sources whose markers appear on *every verse line*, raising the leak rate from roughly 1-in-260 chunks to 90%+. |
| **Impact** | `chunker/text_chunker.py`: new module-level `_EMBEDDED_MARKER` pattern; `chunk_text` now passes through `.sub("", ...).strip()` before being stored on the `Chunk`. No `Chunk`/`SourceConfig`/DB schema change — `content_hash` recalculates naturally since `content` changed for virtually every chunk across all 6 sources (full re-embed, not incremental — same order of cost as DEV-029/DEV-031's runs, well under $1 total for the whole corpus at `text-embedding-3-large` pricing). `test_text_chunker.py` extended (46→48 total ingestion tests when combined with earlier stage counts). No impact on `passage_ref` values themselves (unchanged) or on chunk boundaries/counts (unchanged) — this is a content-cleanliness fix only. Downstream: Stage 6's `RagAgent`/`ConflictSynthesizer` (not yet built) can now quote `content` directly without risk of a stray `[141]`-style artifact reaching a user-facing answer. |
| **Date** | 2026-07-13 |
