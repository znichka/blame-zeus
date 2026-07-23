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

## Stage 3 — Full Corpus ✅ done (2026-07-13)
**Done when:** All 6 sources indexed in `narrative_chunks`; row count per source is non-zero. — **Met.**

> ⚠️ Formerly Stage 4 — renumbered per ADR-004 (see Stage 2 note above).
> ⚠️ Deviations occurred in this stage. See `DEVIATIONS.md` #DEV-029, #DEV-030, #DEV-031, #DEV-032, #DEV-033, #DEV-034.
> ⚠️ **Row counts below are the DEV-031 baseline, since superseded twice** — DEV-032 (marker-leak
> fix, same 3037-row total) then DEV-033/034 (containment-range refs, then paragraph-aligned
> chunking) changed both chunk boundaries and `passage_ref` notation. Current live state: **3,524
> chunks** — Apollodorus 427, Theogony 91, Homeric Hymns 173, Iliad 1,195, Odyssey 905, Ovid 733;
> `passage_ref` is now the paragraph's corpus-native range (`"3.38-3.57"`, bare points for
> Apollodorus sections), not the point-only shape this stage originally shipped. See DEV-033/034
> and the ADR-014 amendments for the full story — this stage's own done-when bar (non-zero rows,
> real structural refs) still holds, just at different numbers.

- [x] Developer manually downloads remaining 5 corpus files (Hesiod Theogony, Homeric Hymns, Homer Iliad, Homer Odyssey, Ovid Metamorphoses) from theoi.com into `ingestion/corpus/` `[DEVIATED - see DEVIATIONS.md #DEV-029]` — not Project Gutenberg/sacred-texts.com as planned; theoi.com transcriptions for all 5 (see DEV-011's Apollodorus precedent for why)
- [x] Add `SourceConfig` entries for Hesiod Theogony, Homeric Hymns, Homer Iliad, Homer Odyssey, Ovid Metamorphoses to `source_registry.py`
- [x] Implement passage ref extractors for each new source `[DEVIATED - see DEVIATIONS.md #DEV-029, ADR-014]` — 3 functions (`hesiod_theogony_refs`, `hesiod_homeric_hymns_refs`, `book_line_refs` shared by Iliad/Odyssey/Ovid), not the 4 originally named (`homer_refs`/`ovid_refs`/`hesiod_refs`/`hymn_refs`), emitting standard classical citation notation instead of raw scraped shapes
- [x] Add extractor tests for all new sources in `test_passage_ref_extractors.py` — 20 tests
- [x] Flyway `V15__add_embedding_model_tracking.sql` + add `embedding_model` to `store_chunks()`'s INSERT (ADR-006, deferred per DEV-015) — ideally rows are stamped at ingestion time, but `V15` numerically follows Stage 4's unwritten `V9`–`V14` (applying it first breaks Flyway's default in-order validation). Resolve at implementation time (renumber, out-of-order, or land with Stage 4 + backfill the ingested rows) and log a DEV entry `[DEVIATED - see DEVIATIONS.md #DEV-028]` — landed early, renumbered into `V8_4__switch_embedding_to_3large_3072.sql` alongside the ADR-013 embedding upgrade; `store_chunks()` stamps `embedding_model`; no backfill needed (table truncated + re-embedded)
- [x] Run full ingestion; verify per-source row counts in DB `[DEVIATED - see DEVIATIONS.md #DEV-031]` — first run surfaced a real regression (Apollodorus 260→284 rows from an unverified interaction between DEV-029's cleaner fix and Apollodorus's own title line); root-caused, remediated (clear + re-embed), and re-verified idempotent. Final: 3037 chunks total — Apollodorus 260, Theogony 57, Homeric Hymns 126, Iliad 1112, Odyssey 724, Ovid 758

→ [Detailed track-by-track checklist](TODO-stage3.md) — includes two pre-identified gotchas:
the `sources` hand-insert repeat (DEV-027 pattern, plus the Ovid `year_published NOT NULL` plan bug)
and the `text_cleaner` all-caps stripping that would silently delete Homer/Ovid `BOOK`/story markers.

---

## Stage 4 — Seed Data (Extraction-Assisted)
**Done when:** `GET /api/v1/entities` returns ≥60 entities; `GET /api/v1/sources` returns 6 rows; `VariantClaimRepositoryTest` finds ≥2 conflict rows for Aphrodite.

> ⚠️ Formerly Stage 2 — renumbered and redesigned per ADR-004 (`docs/adr/adr-004-seed-data-extraction-strategy.md`). `entities`/`relationships` are now LLM-extracted from the ingested corpus (Stage 2–3) with a developer spot-check; `variant_claims` candidates require explicit per-row review before promotion to `trust_tier=1`. `sources`, `myths`/`myth_participants`, and `entity_aliases` remain hand-curated, unaffected by this change.
>
> ⚠️ Amended further by ADR-007 (DEV-014, DEV-018, DEV-019, DEV-020: open `claim_type` + shared `claim_type_aliases.json` normalization, store-all extraction, one canonical edge for contested relationships, normalize-on-promotion, extraction-preferred floor conflicts, unified `death` canonical) and ADR-008 (DEV-015: extraction runs on Claude Opus 4.8 via `instructor.from_anthropic`). Full detail in `TODO-stage4.md`.

- [x] Build extraction pipeline (`ingestion/extraction/`): `schema.py` (models carry `passage_ref`, populated mechanically from the segment — DEV-021), `known_aliases.json`, `entity_resolver.py`, `claim_extractor.py`, `conflict_detector.py`, `run_extraction.py`; the claim-type normalization map is the `claim_type_aliases` **DB table** (V8_2), not a JSON file `[DEVIATED - see DEVIATIONS.md DEV-014, DEV-020, DEV-021, DEV-022]`
- [x] Add `instructor`, `rapidfuzz`, `anthropic` to `ingestion/requirements.txt` `[DEVIATED - see DEVIATIONS.md DEV-015]`
- [x] Tune extraction prompt against Apollodorus in `ingestion/notebooks/01_test_extraction.ipynb` before running the full corpus
- [x] Run extraction against all 6 ingested sources → `entities_candidates.json`, `relationships_candidates.json`, `variant_claims_candidates.json`
- [x] Extraction-quality metric (diagnostic, non-blocking): before any hand-add, log how many cross-source floor conflicts the raw candidates contain unaided (`N/2` — Aphrodite, Achilles; Io is single-source, structurally excluded) `[DEVIATED - see DEVIATIONS.md DEV-019]`
- [x] Flyway V9 — seed sources (6 slugs with `year_published`, `role`) — hand-curated; Homeric Hymns `author` is `Anonymous ("Homeric")`, not Hesiod `[DEVIATED - see DEVIATIONS.md DEV-018]`
- [x] Flyway V10 — seed entities (~60–100) — merge spot-checked candidates from `entities_candidates.json`
- [ ] Flyway V11 — seed relationships (parent_of, married_to, killed_by with source attribution + `passage_ref` per DEV-021) — merge spot-checked candidates from `relationships_candidates.json`; a contested relationship keeps exactly **one** canonical spine-preferred edge — the contradiction is recorded in V12 instead `[DEVIATED - see DEVIATIONS.md DEV-014, DEV-021]` — _generated & applied (2,496 rows, verified in Track H); unchecked pending B4's spot-check of the 203 held-out ambiguous-direction rows (see TODO-stage4.md C3/B4)._
- [ ] Flyway V12 — seed variant_claims — review candidates in `ingestion/notebooks/02_verify_conflicts.ipynb`, promote approved rows to `trust_tier=1` **writing the normalized canonical `claim_type`** (per the `claim_type_aliases` table, DEV-022) and carrying each row's `passage_ref` (DEV-021) at insert; floor conflicts (Aphrodite parentage, Io parentage, Achilles death) are extraction-preferred — hand-add only the ones extraction missed, recording which path each took; Achilles death seeds under canonical `death`, never `slaying` `[DEVIATED - see DEVIATIONS.md DEV-018, DEV-019, DEV-020, DEV-021, DEV-022]` — _generated & applied (44 rows: all 3 floor conflicts, verified in Track H); unchecked pending B5's full review of the remaining ~838 groups (see TODO-stage4.md C4/B5)._
- [x] Flyway V13 — seed myths + myth_participants — hand-curated, unaffected
- [x] Flyway V14 — create + seed entity_aliases (~20 cross-cultural aliases) — hand-curated, unaffected; may reuse `known_aliases.json` as a source list
- [x] JPA `@Entity` classes: `Source`, `EntityRecord`, `Relationship`, `Myth`, `MythParticipant`, `VariantClaim`, `NarrativeChunk`, `EntityAlias`
- [x] Spring Data JPA repositories for all entities
- [x] DTOs: `QueryRequest`, `QueryResponse`, `Citation`, `ConflictEntry`, `RagResponse`
- [x] `GET /api/v1/entities` and `GET /api/v1/sources` read endpoints in `QueryController`
- [x] Tests: `SourceRepositoryTest`, `EntityRepositoryTest`, `VariantClaimRepositoryTest` (Testcontainers)

→ [Detailed track-by-track checklist](TODO-stage4.md)

---

## Stage 5 — SQL Pipeline ✅ done (2026-07-15)
**Done when:** DATA gold questions (Q6–Q10) answer correctly via `POST /api/v1/query`; `SqlSafetyValidatorTest` + `SqlQueryHandlerTest` pass. — **Pipeline mechanics met** (all 5 route `SQL`, execute, no `serviceError`, Q9's `WITH RECURSIVE` and Q10's ≥12-row bar both hold); `required_keywords` content coverage on Q6–Q9 is capped by pre-existing Stage 4 seed-data gaps (see note below), not a Stage 5 defect.

> ⚠️ Updated assumptions based on DEV-004 (see DEVIATIONS.md): LangChain4j is `1.0.0-beta5` (not 1.0.0 GA). Before implementing, verify current beta5 API shapes for `@AiService`, `@V` parameter injection, `@SystemMessage`/`@UserMessage`, and `QueryRouter`/`TextToSqlAgent` interface construction.
>
> ⚠️ Amended by ADR-008 (DEV-015): the chat beans are `AnthropicChatModel` (Claude Haiku 4.5, `LLM_CHAT_MODEL=claude-haiku-4-5-20251001`), not `OpenAiChatModel`; `LLM_API_KEY` holds an Anthropic key. Run the gold set before committing to the swap (swap-after-eval discipline, ADR-008 §5).
>
> ⚠️ Deviations occurred in this stage. See DEVIATIONS.md for details (DEV-046, DEV-047).
> DEV-046: the beta5 pin only covers the Spring-integration artifacts — `@AiService`/`@V`/`@SystemMessage`/`AiServices` machinery is pulled transitively from GA `langchain4j-core:1.0.0` and matches current GA docs; the implemented chat-model interface is `ChatModel`, not `ChatLanguageModel`; and with two `ChatModel` beans in context, each `@AiService` interface needs `@AiService(wiringMode = EXPLICIT, chatModel = "routingModel")` — a LangChain4j bean-name-string lookup, not Spring `@Qualifier`. DEV-047: live testing against the real Anthropic API found the model occasionally wraps SQL in a ` ```sql ` fence despite instructions (now stripped defensively in `SqlQueryHandler`) and that no schema comment documented `relationships.from_id`/`to_id` direction (fixed via `V15__clarify_relationship_direction_comments.sql`); it also confirmed the remaining Q6–Q9 keyword gaps trace to Stage 4 seed-data completeness (Perseus has zero `relationships` rows, no `Cetus` entity, Hades/Hestia seeded as `type='other_god'`, a likely `Heaven`/`Uranus`-`Ouranos` duplicate-entity split with no edge to `Chaos`) — flagged for a Stage 4 follow-up, not patched here to avoid fabricating unverified source attribution.

- [x] Tests first: `SqlSafetyValidatorTest` (SELECT/WITH allowed; DROP/DELETE/INSERT/UPDATE/`;` blocked) — 15/15 passing
- [x] Tests first: `SqlQueryHandlerTest` (mock `TextToSqlAgent`, assert validator called before JdbcTemplate) — 11/11 passing, incl. markdown-fence stripping and empty/aggregate-zero cases
- [x] Tests first: `QueryRouterTest` — assert the router only ever emits `SQL`/`RAG`/`MIXED`, never `CONFLICT` `[DEVIATED - see DEVIATIONS.md DEV-014]`
- [x] `RouteDecision.kt` enum (`SQL`, `RAG`, `MIXED` — **no `CONFLICT`**) — already correct from Stage 4, confirmed unchanged `[DEVIATED - see DEVIATIONS.md DEV-014]`
- [x] `QueryRouter.kt` `@AiService` interface (temperature 0.0, returns `RouteDecision`); prompt keeps schema-boundary → RAG, **omits** any "route to CONFLICT" instruction `[DEVIATED - see DEVIATIONS.md DEV-014]`
- [x] `TextToSqlAgent.kt` `@AiService` interface with `@V("schema")` + `@V("question")` params (plus a required `@UserMessage` — see DEV-046)
- [x] `SqlSafetyValidator.kt` — deny-list enforcement
- [x] `SqlQueryHandler.kt` — generates SQL → strips markdown fences (DEV-047) → validates → executes → formats rows + extracts citations
- [x] Empty-result fallback in `SqlQueryHandler` (ADR-005 §Decision.3): zero rows → Stage-5 placeholder (real RAG fallback wired in Stage 6); also treats **aggregate-zero** as empty — a single row whose values are all `0`/`NULL` (`COUNT`=0, `SUM`=NULL) `[DEVIATED - see DEVIATIONS.md DEV-026]`
- [x] Added `langchain4j-anthropic-spring-boot-starter` to `core-api/build.gradle.kts` (kept `langchain4j-open-ai-spring-boot-starter` — the embedding bean needs it) `[DEVIATED - see DEVIATIONS.md DEV-015]`
- [x] `LangChain4jConfig.kt` routing + synthesis model beans — `AnthropicChatModel`, temps 0.0/0.3, model name from `LLM_CHAT_MODEL` `[DEVIATED - see DEVIATIONS.md DEV-015, DEV-046]`
- [x] `SchemaIntrospector.kt` — already built and self-describing since Stage 1c; Stage 5 only consumed it, plus added `V15` column comments documenting `relationships.from_id`/`to_id` direction (DEV-047) `[DEVIATED - see DEVIATIONS.md DEV-023]`
- [x] `QueryService.kt` — routes SQL decision to `SqlQueryHandler`; RAG/MIXED get a Stage-5 placeholder; router failure defaults to RAG; handler failure returns `serviceError=true`
- [x] Log generated SQL at DEBUG level — confirmed live for all 5 gold questions
- [x] Wired `POST /api/v1/query` in `QueryController`

→ [Detailed track-by-track checklist](TODO-stage5.md)

---

## Stage 6 — RAG Pipeline ✅ done (2026-07-15)
**Done when:** FACT gold questions (Q1–Q5) return cited answers; `RagQueryHandlerTest` passes. — **Met**,
after two rounds of live-verification fixes (see DEV-049/DEV-050 below): all 5 FACT questions route
`RAG`, return real (non-fabricated) citations, clear their `required_keywords`/`required_authors`, and
hit no `forbidden_patterns`; `RagQueryHandlerTest` and the full suite pass.

> ⚠️ Updated assumptions based on DEV-004 (see DEVIATIONS.md): LangChain4j is `1.0.0-beta5`. Before implementing, verify beta5 API shapes for `RagAgent @AiService`, `EmbeddingStore`, `ContentRetriever`, and `PgVectorEmbeddingStore` (including `createTable(false)` parameter shape).
>
> ⚠️ Updated based on DEV-033/DEV-034 (see DEVIATIONS.md): chunks are **paragraph-aligned** and `narrative_chunks.passage_ref` is the paragraph's **corpus-native range** (`"3.38-3.57"`; points for Apollodorus sections; ADR-014 Amendments 1–2) — the chunk's ref IS the citation, exact at both ends; display may elide it classically (`Il. 3.38–57`) but the stored form keeps the full prefix. `metadata.sentence_refs` entries all carry the paragraph's start marker (audit/forward-compat; no finer resolution exists in the corpus). Retrieval-time near-duplicate handling is **no longer a concern**: cross-chunk overlap was dropped (mean redundancy now 1–3%); the only near-duplicates are sub-chunks of the ~160 oversized paragraphs, which share a `passage_ref` — dedupe retrieved chunks by `passage_ref` when building the prompt if two sub-chunks of one paragraph both rank in top-k.

- [x] Tests first: `RagQueryHandlerTest` (mock `RagAgent`, assert `RagResponse.citations` returned without text parsing)
- [x] `RagAgent.kt` `@AiService` interface — JSON structured return (`RagResponse`); system message includes the conflict-aware backstop instruction: if retrieved passages give different accounts of the same point from different sources, present each with its attribution rather than merging or picking one (ADR-007 §3) `[DEVIATED - see DEVIATIONS.md DEV-014, DEV-046, DEV-049]`
- [x] `RagQueryHandler.kt`
- [x] `LangChain4jConfig.kt` — `embeddingModel` bean only; **no `PgVectorEmbeddingStore`/`EmbeddingStoreContentRetriever` beans** — beta5's store hardcodes its own `embedding_id UUID`/`text` schema and cannot read `narrative_chunks(id, content, …)` (verified against the pinned jar). Instead: small custom `ContentRetriever` over `JdbcTemplate` (embed query → `ORDER BY embedding::halfvec(3072) <=> (?::vector(3072))::halfvec(3072) LIMIT 5` — the halfvec cast is REQUIRED to hit V8_4's expression index, a plain `embedding <=> ?` silently seq-scans (updated based on DEV-028, see DEVIATIONS.md); minScore=0.5 filter (retuned from the 0.65 starting value, DEV-050), returning `source_id`/`passage_ref`/`author`/`work`/`stance` for citations, joined from `sources` (DEV-049)); drop `langchain4j-pgvector` from `build.gradle.kts`. Embedding model name injected from `app.llm.embedding-model` (`EMBEDDING_MODEL` env var, now `text-embedding-3-large` per ADR-013), not hardcoded (ADR-006, deferred per DEV-015) `[DEVIATED - see DEVIATIONS.md DEV-025, DEV-049, DEV-050]`
- [x] `EmbeddingConsistencyChecker.kt` — `ApplicationReadyEvent` check that the configured embedding model matches what the corpus rows were embedded with (the `narrative_chunks.embedding_model` column exists since V8_4/DEV-028 — compares against `text-embedding-3-large`); logs errors, never blocks startup (ADR-006, deferred per DEV-015)
- [x] `canary-aphrodite.json` golden-vector fixture (generated once via the Python pipeline, with `EMBEDDING_MODEL=text-embedding-3-large` per DEV-028) + `EmbeddingConsistencyTest.kt` (ADR-006, deferred per DEV-015)
- [x] `EXPLAIN ANALYZE` index-usage check on the HNSW retrieval query, once ingested data exists — must show `narrative_chunks_embedding_hnsw_idx` (the V8_4 halfvec expression index), which only matches the cast form of the query (ADR-006 §10 addition, deferred per DEV-015; updated based on DEV-028) `[DEVIATED - see DEVIATIONS.md DEV-050 — at the current ~3,524-row corpus size Postgres' planner prefers a seq scan by default regardless of the cast; forcing enable_seqscan=off confirms the cast is still load-bearing/required]`
- [x] Add RAG route to `QueryService`
- [x] Router fallback: catches router exceptions, defaults to RAG (already implemented in Stage 5 — now yields a real RAG answer instead of the placeholder; verify)
- [x] Author FACT gold questions Q1–Q5 in `evaluation/gold-questions.json` (currently holds only DATA Q6–Q10; added as this pipeline lands) `[DEVIATED - see DEVIATIONS.md DEV-048, DEV-050]`

→ [Detailed track-by-track checklist](TODO-stage6.md)

---

## Stage 7 — Conflict Enrichment (router-independent)
**Done when:** the Aphrodite question returns ≥2 attributed versions in `conflicts[]` **even though it routes to SQL/RAG, not a CONFLICT route**; `ConflictLookupTest` + enrichment test pass.

> ⚠️ Recast by ADR-007 (`[DEVIATED - see DEVIATIONS.md DEV-014]`): there is **no `CONFLICT` route and no `ConflictQueryHandler`**. Conflict surfacing is a router-independent enrichment step in `QueryService`, invoked after *any* answer, that writes only `conflicts[]` (never `answer`) and is wrapped so it can never break the primary answer.
>
> ⚠️ Updated assumptions based on DEV-004 (see DEVIATIONS.md): LangChain4j is `1.0.0-beta5`. Before implementing, verify beta5 API shapes for `EntityExtractor`/`ConflictProbe @AiService` (temperature 0.0) and `ConflictSynthesizer @AiService` (temperature 0.3) — annotation and parameter injection shapes may differ from 1.0.0 GA.

- [x] Tests first: `ConflictLookupTest` (all matching `variant_claims` rows returned for a subject + normalized `claim_type`; unknown entity / empty result handled gracefully) `[DEVIATED - see DEVIATIONS.md DEV-014]`
- [x] Tests first: `QueryService` enrichment test — a conflict-shaped question routed to SQL/RAG still yields a populated `conflicts[]`; a claim-type mismatch (e.g. appearance question on a subject with a stored death conflict) yields empty `conflicts[]`; enrichment failure leaves the primary answer intact `[DEVIATED - see DEVIATIONS.md DEV-014]`
- [x] `ConflictProbe.kt` `@AiService` interface (temperature 0.0) → `{subject, claimType}` — **no separate `EntityExtractor`**; one interface serves both this enrichment probe and any future Stage 8 entity-only lookup (Track B1, not a deviation — the plan/ADR-007 left the naming open). Returns the literal sentinel `"none"` when the question maps to no modeled attribute `[DEVIATED - see DEVIATIONS.md DEV-014]`
- [x] `ConflictSynthesizer.kt` — `[DEVIATED - see DEVIATIONS.md DEV-051]` a deterministic, **non-`@AiService`** `@Component` (row → `List<ConflictEntry>`), not an LLM interface — `conflicts[]` presentation is data-driven per ADR-007 §5, so no chat-model round trip is needed to just structure fetched rows.
- [x] `ConflictLookup.kt` (shared component, **not** an `@AiService`) — three-step entity resolution (exact → alias → trigram), then two fetches over that resolution: (a) a **claim-type-filtered** fetch for enrichment (`subject_entity_id = ? AND claim_type = normalize(probeClaimType)`, using `idx_variant_claims_subject_type` — confirmed actually chosen by the planner via live `EXPLAIN ANALYZE`, Track H9), and (b) a **subject-only** fetch (all `claim_type`s for the entity) backing the `/conflicts/{entityName}` endpoint; reads the shared `claim_type_aliases` DB table (V8_2) for `normalize()` — same rows the offline detector reads; never a code-side copy of the map `[DEVIATED - see DEVIATIONS.md DEV-014, DEV-022]`
- [x] `QueryService` enrichment step — after `dispatch(route)`, skip on `serviceError`, else `conflictProbe.extract` → `conflictLookup.find` → `conflictSynthesizer.synthesize`; write only `conflicts[]`, wrapped in try/catch so it never breaks the primary answer `[DEVIATED - see DEVIATIONS.md DEV-014]`
- [x] `GET /api/v1/conflicts/{entityName}` endpoint — backed by `ConflictLookup`'s **subject-only** fetch (no claim-type context at the URL), not a handler; returns all stored `variant_claims` for the entity across claim_types, **200 + empty list for an unknown name (not 404)** since the lookup can't distinguish "no such entity" from "a real entity with zero conflicts" `[DEVIATED - see DEVIATIONS.md DEV-014]`
- [x] Live-verified (Track H, `[DEVIATED - see DEVIATIONS.md DEV-053]`): Aphrodite conflict surfaces with **13** attributed versions on **both** a direct SQL route and a direct RAG route; the Io single-source floor case (Inachus vs. Piren, both Apollodorus) surfaces via the SQL-empty→RAG fallback path; the Achilles claim-type-mismatch guard holds (probe correctly resolves `subject: "Achilles"` even when the question also names `"Agamemnon"`); `GET /conflicts/Venus` resolves via alias to the identical response as `GET /conflicts/Aphrodite`. Gold `evaluation/gold-questions.json` Q13–15 + Q18 authored (Track G, `[DEVIATED - see DEVIATIONS.md DEV-052]`); Q14's `expected_route` corrected from the plan's predicted `SQL` to the live-observed `RAG`.

→ [Detailed track-by-track checklist](TODO-stage7.md)

---

## Stage 8 — Mixed Pipeline
**Done when:** MIXED gold questions (Q11–Q12) return both SQL rows and narrative answer; `MixedQueryHandlerTest` passes.

> ⚠️ Updated assumptions based on DEV-004 (see DEVIATIONS.md): LangChain4j is `1.0.0-beta5`. `MixedQueryHandler` calls `ragAgent.answer(augmented)` — confirm the `RagAgent @AiService` interface verified in Stage 6 is unchanged before building on it.
>
> ⚠️ Handler shipped and unit-verified (126 tests green: `MixedQueryHandler` + `QueryService` dispatch),
> and Stage 5's three prompt/schema findings are fixed and confirmed live (DEV-054). **But Q11/Q12 still
> do not pass end-to-end** — live runs surfaced two deeper `TextToSqlAgent` SQL-generation gaps that also
> break DATA **Q9**. Boxes below stay unchecked pending **[Stage 8.5 — Debug SQL-Generation Errors](#stage-85--debug-sql-generation-errors-deferred)**.

- [ ] Tests first: `MixedQueryHandlerTest` (SQL results injected into augmented question before RAG call)
- [ ] `MixedQueryHandler.kt` — SQL filter → inject results as context → `ragAgent.answer(augmented)`
- [ ] Add MIXED route to `QueryService`
- [ ] `QueryService` inner try-catch: handler failures return `serviceError=true` response

→ [Detailed track-by-track checklist](TODO-stage8.md)

---

## Stage 8.5 — Debug SQL-Generation Errors (deferred)
**Done when:** DATA **Q9**, MIXED **Q11**, and MIXED **Q12** answer end-to-end via `POST /api/v1/query` with `serviceError: false` and their `required_keywords` present; no regression on the rest of the gold set (full-set route match stays ≥ current 15/16, no new `serviceError`s).

> ⚠️ **Not part of `IMPLEMENTATION_PLAN.md §9`** — a developer-added remediation stage tracking live bugs
> found while landing Stage 8 (all detailed in **DEVIATIONS.md #DEV-054**, gaps (i)/(ii)).
>
> ⚠️ **Sequencing (developer decision):** Stage 9 (Web UI) is bootstrapped **first**, then this stage.
> This stage does **NOT** gate Stage 9 — all three failures degrade gracefully (`serviceError: true`
> friendly message, or A3 empty-filter → RAG fallback), so the Web UI renders correctly over the working
> questions (FACT Q1–5, DATA Q6–8/Q10, CONFLICT Q13–15/18) and shows the error banner for the three
> broken ones. Return here after Stage 9.
>
> ⚠️ All three are **pre-existing `TextToSqlAgent` (Stage 5) SQL-generation gaps**, not regressions from
> DEV-054's fixes and not `MixedQueryHandler`/`QueryService` defects (those are unit- and live-verified).

**Live evidence (2026-07-16 full gold-set run, real Postgres + Anthropic, temp 0):** route match 15/16;
two `serviceError`s — Q9 and Q12 — plus Q11's empty-filter fallback. Details below.

- [ ] **Gap (ii) — `WITH RECURSIVE` unreliability (breaks Q9 + Q12).** `TextToSqlAgent` generates invalid
      or runaway recursive CTEs despite the existing anchor-column rule: Q9 ("Trace Zeus's lineage back to
      Chaos") hits the 3s `statement_timeout` (cyclic/unbounded recursion over `relationships`); Q12's
      MIXED filter produced "bad SQL grammar" (anchor `SELECT` referenced `r.relation` without joining
      `relationships` in the anchor branch) on one run and a rejected `;`-containing statement on another.
      Likely fix: add a correct few-shot `WITH RECURSIVE` example to the prompt + a cycle guard
      (visited-path array or depth bound in the generated SQL) so upward parent-walks terminate. Also
      confirm whether the `relationships` graph has cycles that need breaking at query time.
- [ ] **Gap (i) — MIXED over-constraint (breaks Q11).** For "Which heroes had a divine parent and died at
      Troy?" the model encodes the *narrative* predicate "died at Troy" as structured SQL
      (`myths.title ILIKE '%Troy%'` AND `mp.role ILIKE '%died%'`); the seed has no Troy-titled myth and no
      "died" role, so the filter returns 0 rows. The divine-parent filter *alone* returns 21 heroes (incl.
      Achilles, Aeneas, Memnon). Likely fix: give the MIXED path (shared `TextToSqlAgent`, called by
      `MixedQueryHandler`) guidance to emit only the *structured/relational* filter and leave narrative
      predicates (locations, causes, deaths, motivations) to the RAG half — without regressing pure-SQL
      questions that legitimately filter on those tables.
- [ ] **Watch — Q14 route fragility (not a failure).** Q14 ("Who was Io's father?") routed `SQL` this run
      (answer correct, no error) vs. its gold `expected_route: RAG` (set in DEV-053 when SQL fell back
      empty). Route label depends on whether SQL returns rows; possibly nudged by DEV-054's better schema
      grounding. Decide during this stage whether the gold label or the fallback behavior is authoritative
      (ties into DEV-053's `SqlQueryHandler` raw-row-dump formatting follow-up).
- [ ] Re-run the full gold set live after fixes; confirm Q9/Q11/Q12 pass and nothing else regresses, then
      flip the **Stage 8** boxes (Q11/Q12 are its `Done when`).

→ Detail & root-cause in **DEVIATIONS.md #DEV-054** (Impact gaps (i)/(ii)) and **#DEV-053** (Q14, SQL formatting).

---

## Stage 9 — Web UI ✅ done (2026-07-16)
**Done when:** Manual smoke test of all 17 gold questions in browser passes; route badge + citations render correctly.

> ⚠️ **Sequenced before [Stage 8.5](#stage-85--debug-sql-generation-errors-deferred) (developer decision).**
> Until Stage 8.5 lands, **Q9/Q11/Q12 will not answer correctly** — they hit `serviceError` or an
> empty-filter RAG fallback (DEV-054). For this stage, the smoke test verifies that the UI *renders* every
> response shape correctly, **including the `serviceError` error banner** for those three; correct answers
> to all 17 are re-confirmed after Stage 8.5, not here.

> ⚠️ Updated based on DEV-009 (see DEVIATIONS.md): springdoc-openapi is `2.6.0` (not `2.8.3` — DEV-006 picked a version requiring Spring Boot 3.4.x, which broke `@SpringBootTest` context loading under Spring Boot 3.3.13). `OpenApiConfig.kt` should target `2.6.0`'s API surface; `@Operation`/`@Tag` usage is unaffected.

- [x] `WebController.kt` — `GET /` + `POST /web/query`
- [x] `templates/index.html` — form, route badge (color-coded), answer block, citations footnotes, conflicts section, collapsible SQL block, error banner for `serviceError`
- [x] Tailwind CSS via CDN (no build step)
- [x] `OpenApiConfig.kt` — Springdoc customization
- [x] `QueryControllerIntegrationTest` — HTTP 200; `routeDecision` present (`SQL`/`RAG`/`MIXED`); a conflict-shaped question populates `conflicts[]` via enrichment regardless of route `[DEVIATED - see DEVIATIONS.md DEV-014]`. `WebControllerTest`/`QueryControllerIntegrationTest` both mock `QueryService` via `@MockkBean` rather than exercising a live `@AiService` `[DEVIATED - see DEVIATIONS.md #DEV-055]`.
- [x] Smoke test: Swagger UI loads at `/swagger-ui.html`. Live-verified against real `bootRun` + seeded Postgres: all 16 gold questions currently in `evaluation/gold-questions.json` (ids 16/17 REFUSAL deferred to Stage 10 per DEV-052) render every UI block correctly, incl. the `serviceError` banner for Q9/Q12 (DEV-054's `WITH RECURSIVE` fragility) — no Stage 9 bugs found; see `TODO-stage9.md` Track F3/F4 for full detail.

→ [Detailed track-by-track checklist](TODO-stage9.md)

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

## Stage 11 — Telegram Bot (Phase 2, optional) — ❌ REMOVED (see ADR-016 / DEVIATIONS.md DEV-058)
**Done when:** ~~Bot answers questions in Telegram chat; `/start` command works.~~

> ❌ **REMOVED — the product is web-only (ADR-016 / DEV-058).** The `telegram-bot` module and all its
> wiring are being removed; this stage is withdrawn. The checklist below is retained for history only.
> (DEV-007, about the commented-out starter, is superseded.)

- [ ] `telegram-bot/build.gradle.kts` — add `telegrambots-spring-boot-starter:6.9.x` (verify coordinates first) + `spring-boot-starter-web` `[DEVIATED - see DEVIATIONS.md DEV-007]`
- [ ] `BlamezeusBot` extending `TelegramLongPollingBot`
- [ ] `CoreApiClient` — `RestClient` calling `POST /api/v1/query`
- [ ] `TelegramResponseFormatter` — MarkdownV2 formatting, message splitting at >4096 chars
- [ ] `docker-compose.full.yml` — add `telegram-bot` service with `depends_on: core-api: condition: service_healthy`
- [ ] Add `TELEGRAM_BOT_TOKEN` + `TELEGRAM_BOT_USERNAME` + `CORE_API_BASE_URL` to `.env.example`

---

## Post-MVP Enhancements

Work decided **after** the MVP (`IMPLEMENTATION_PLAN.md §9`, Stages 1–11) shipped. **Not part of
§9** — each item is backed by its own ADR and an ADR-named detail doc (not a numbered stage), so
the §9 stage history stays untouched.

### ADR-015 — Unified Answer Composition
**Done when:** every non-error route returns prose `answer` with inline `[n]` markers + one unified
References list where `[n]` indexes `citations[n-1]`; conflict-shaped questions **weave** each
attributed version into the prose without picking a winner (`conflictsInProse=true`); on composer
failure or a `serviceError` draft, `QueryService` falls back to the pre-composition draft with
structured `conflicts[]` (`conflictsInProse=false`); `conflicts[]` stays populated on every
response; `:core-api:test` green.

> ⚠️ Implements `docs/adr/adr-015-unified-answer-composition.md`. **Amends ADR-007 §5** (prose
> presentation only — the conflict *data model* is unchanged). **Closes the user-facing half of
> DEV-053** (SQL raw-row-dump → prose); does **not** touch DEV-054/Stage 8.5 (`WITH RECURSIVE`
> Q9/Q11/Q12 still fail → `serviceError` → composer fallback). Cost: **one extra LLM call per
> query**, on every non-error route incl. plain RAG (accepted quality-first trade-off).

- [x] `AnswerComposer.kt` `@AiService` (`synthesisModel`, EXPLICIT wiring per DEV-046) + `ComposedAnswer` DTO — no new bean, no new provider surface
- [x] `SqlQueryHandler.formatAnswer` → column-named material (`name=Zeus, type=olympian`)
- [x] `QueryService` reorder: `route → dispatch (DRAFT) → claims → answerComposer.compose (FINAL)`, wrapped fallback to the draft
- [x] `QueryResponse.conflictsInProse` + template (single unified References list; legacy "Sources disagree" box rendered **only** when `conflictsInProse=false`)
- [x] Tests: `QueryServiceTest` (uniform composition + `conflictsInProse` + fallback), `SqlQueryHandlerTest` (column-named), controller/web tests (`@MockkBean`, DEV-055)
- [x] Traceability: log `DEV-056`; annotate ADR-007 §5 "Amended by ADR-015"; add stage-note pointer `[DEVIATED - see DEVIATIONS.md DEV-056]`

→ [Detailed track-by-track checklist](TODO-adr-015.md)

### ADR-016 — Web-Only Direction + Mosaic Frontend Redesign
**Done when:** the `telegram-bot` module + all wiring (build/compose/env) are removed and
`./gradlew projects` lists only `core-api` (`./gradlew build` green, no telegram reference in
code/build/compose/env); the single web page renders the self-contained Greek/Roman **mosaic** theme
(cream base, steel-blue serif "Blame Zeus" header + tagline, pure-CSS meander/wave border strips,
pale-blue input + terracotta submit arrow, "Verdict" answer label) with **no Tailwind-CDN/web-font
request**; curated example-question **chips** fill+submit the input; citations render in a
first-class **"Sources" panel** paired with the "Sources disagree" conflict panel; every
`QueryResponse` binding and the `!conflictsInProse && !conflicts.isEmpty()` gate preserved; `:core-api:test` green; stale
telegram doc references cleaned up.

> ⚠️ Implements `docs/adr/adr-016-web-only-direction-mosaic-frontend.md`. **Supersedes DEV-007** and
> withdraws `IMPLEMENTATION_PLAN.md §6` + roadmap Stage 11. Documentation landed as **DEV-058**;
> this is the deferred **implementation**. Presentation + subtraction only — no backend/DTO changes;
> example questions are **hardcoded** (no runtime read of `evaluation/gold-questions.json`).

- [ ] Remove `telegram-bot` module: delete `telegram-bot/`, edit `settings.gradle.kts`, `docker-compose.full.yml`, `.env`/`.env.example`
- [ ] New `static/css/blame-zeus.css` (palette vars, meander/wave strips, serif) + `static/js/examples.js` (chip fill+submit) — self-contained, no CDN
- [ ] Rewrite `index.html` into the mosaic theme (Verdict + first-class Sources panel + gated "Sources disagree"); preserve all bindings and the `!conflictsInProse` gate
- [ ] Docs cleanup: README, CLAUDE.md, TECH_GUARDRAILS, TODO-stage1, ADR-003/012 telegram references
- [ ] Tests: keep `WebControllerTest` green (`@MockkBean`, DEV-055; update markup assertions); `:core-api:test` green
- [ ] Manual browser smoke: mosaic renders, no-CDN network check, chips work, DATA question shows Sources (DEV-057 guard), conflict question weaves prose (no dup box)

→ [Detailed track-by-track checklist](TODO-adr-016.md)

### Phase 2 — Data Quality & Evaluation Program (ADR-017 / ADR-018 / ADR-019)
**Done when:** an offline evaluation harness produces a committed, per-category-scored baseline;
wrong answers are diagnosable (DEBUG logging + a `debug` response surface); the two known runtime
defects (Q13 formatting / DEV-053, Q9/Q12 `WITH RECURSIVE` / DEV-054) are fixed; the existing seed is
audited and corrected (duplicates, relation-label canonicalization via `relation_aliases`, the 29-pair
+ 203-row backlogs); and an eval-gated batch loop grows conflict depth and new data types with the
gold set expanding in lockstep — all with **≥75% sustained** across 3-run evals and zero stable
regressions.

> ⚠️ Implements **ADR-017** (measurement-first, eval-gated direction), **ADR-018** (evaluation
> harness as an offline Python operator tool + the "no live LLM in tests" scoping clause), and
> **ADR-019** (relation-label canonicalization). Design detail in `IMPLEMENTATION_PLAN_PHASE2.md`;
> stage roadmap + "Done when" gates in `TODO2.md`. Activates **ADR-010** (Accepted now) and, at P5a,
> **ADR-009**. Documentation landed as **DEV-059**. Not part of `IMPLEMENTATION_PLAN.md §9`.

- [ ] Stage P1 — Evaluation harness + committed baseline (ADR-018; ADR-010 accepted)
- [ ] Stage P2 — Debuggability (`DebugInfo`, DEBUG logging, `reseed-local.sh`) + DEV-053/DEV-054 fixes
- [ ] Stage P3 — Data audit & fixing (`ingestion/audit/`, `relation_aliases`, backlogs) — priority
- [ ] Stage P4 — Iterative conflict-depth loop; gold set grows in lockstep (ADR-010 questions)
- [ ] Stage P5 — New data types (P5a numeric/ADR-009, P5b myths, P5c geography/epithets) + gap
      discovery. Revisit the P2-deferred `query_history` skip here if real web usage has appeared
      by then (`IMPLEMENTATION_PLAN_PHASE2.md §3.5`, `DEVIATIONS.md` DEV-064).

→ [Phase-2 roadmap](TODO2.md) · [Phase-2 design](IMPLEMENTATION_PLAN_PHASE2.md)
