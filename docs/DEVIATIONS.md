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
