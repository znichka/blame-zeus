# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**blame-zeus** is a Greek Mythology Lore Assistant PoC. Its defining feature is **source attribution and conflict awareness**: rather than giving a single confident answer about a myth, it surfaces disagreements between ancient sources and attributes each version to the text it came from.

Key docs:
- `docs/CONCEPT.md` — full product concept and design rationale
- `docs/IMPLEMENTATION_PLAN.md` — architecture, module layout, data model, handler logic, evaluation, implementation sequence
- `docs/TECH_GUARDRAILS.md` — hard constraints on stack, LLM usage, SQL safety, testing, and what NOT to add
- `docs/DEVIATIONS.md` — every deviation from the plan that occurred during implementation (append-only)

## Tech Stack

- **Language:** Kotlin 2.3.21 + JVM 21 (`core-api`); Python 3.12+ (`ingestion`)
- **Framework:** Spring Boot 3.3.13 (Jakarta namespace, not `javax.*`)
- **Build:** Gradle Kotlin DSL; shared convention plugin in `buildSrc/`
- **LLM framework:** LangChain4j (JVM services only) — all LLM calls in `core-api` go through `@AiService` interfaces; no direct OpenAI/Anthropic Java SDK in JVM code. The `ingestion` Python job is the only authorized exception, using provider Python SDKs directly for corpus-prep tooling: the OpenAI SDK for **embedding** and (since ADR-008) the Anthropic SDK via `instructor` for **offline seed-data extraction**. Both are offline, never run at query time, and never touch `LangChain4jConfig.kt`.
- **LLM provider:** OpenAI for **embedding** (fixed — must match `text-embedding-3-large` used during ingestion (native 3072-dim since ADR-013); not swappable without re-ingesting the full corpus). **Chat model is provider-agnostic** — all `@AiService` interfaces and handlers are provider-neutral; the only provider-specific code is the beans in `LangChain4jConfig.kt` (default since ADR-008: `AnthropicChatModel`, Claude Haiku 4.5). Swap those beans and add the new provider's LangChain4j starter to change the chat provider (keep `langchain4j-open-ai-spring-boot-starter` regardless — the embedding bean needs it). Two separate API key env vars across **two providers** since ADR-008: `OPENAI_API_KEY` for ingestion + embedding, `LLM_API_KEY` for the (Anthropic) chat model — these are now different keys, not the same one. Chat model name injected via `LLM_CHAT_MODEL` env var — no default in `application.yml`, must always be set explicitly. Offline extraction uses Claude Opus 4.8 via `EXTRACTION_MODEL` (Python, `instructor.from_anthropic`), whose client reads a third key env var, `ANTHROPIC_API_KEY` — it may hold the same Anthropic key as `LLM_API_KEY`, but stays a separate var because the Anthropic Python SDK reads `ANTHROPIC_API_KEY` by convention. Embedding model name shared via `EMBEDDING_MODEL` (ADR-006).
- **Storage:** Postgres 16 + pgvector — relational tables and `narrative_chunks` vector store in one DB
- **Deployment:** Docker Compose for Phase 1 (DB-only: `docker-compose.yml`; full stack: `docker-compose.full.yml`)

## Service Layout

| Unit | Type | Phase | Responsibility |
|---|---|---|---|
| **core-api** | Spring Boot service | Phase 1 | Q&A brain: route → SQL/RAG → synthesize → cite. REST API + Thymeleaf web UI + Swagger UI. |
| **ingestion** | Offline Python job | Phase 1 | One-time data prep: load .txt files → clean → chunk → embed → populate DB. Runs and exits; not deployed. Not part of Gradle build. |

`core-api` shares the Postgres + pgvector instance with the offline `ingestion` job. `springdoc-openapi` exposes Swagger UI at `/swagger-ui.html`.

> **Web-only since ADR-016** (`docs/adr/adr-016-web-only-direction-mosaic-frontend.md`, DEV-058): the
> `telegram-bot` module was removed; `core-api`'s Thymeleaf page (`index.html`) is the only client.

## Module Layout

```
blame-zeus/
├── buildSrc/                   (shared Kotlin convention plugin)
├── core-api/
│   ├── build.gradle.kts
│   └── src/main/
│       ├── kotlin/com/blamezeus/coreapi/
│       │   ├── config/         (LangChain4jConfig, SchemaIntrospector, OpenApiConfig)
│       │   ├── controller/     (QueryController, WebController)
│       │   ├── domain/         (JPA entities, DTOs)
│       │   ├── repository/
│       │   ├── routing/        (QueryRouter, RouteDecision — SQL|RAG|MIXED)
│       │   ├── ai/             (TextToSqlAgent, RagAgent, ConflictSynthesizer, ConflictProbe)
│       │   ├── handler/        (SqlQueryHandler, RagQueryHandler, MixedQueryHandler)
│       │   ├── conflict/       (ConflictLookup — shared entity-resolution + variant_claims fetch; not an @AiService)
│       │   ├── safety/         (SqlSafetyValidator)
│       │   └── service/        (QueryService — central orchestrator)
│       └── resources/
│           ├── application.yml
│           └── db/migration/   (Flyway V1–V14 incl. V8_1–V8_4, V9_1–V9_2 + afterMigrate callback; V10–V12 generated by ingestion/seedgen)
├── ingestion/                  (Python — excluded from Gradle build)
│   ├── corpus/                 (.txt files — not committed to git)
│   ├── loader/                 (source_registry.py, text_cleaner.py)
│   ├── chunker/                (text_chunker.py)
│   ├── pipeline/               (embedding_pipeline.py)
│   └── main.py
└── evaluation/
    └── gold-questions.json
```

## Query Routing & Conflict Enrichment

> Data-driven conflict surfacing per **ADR-007** (`docs/adr/adr-007-conflict-detection-and-surfacing.md`).
> Routing selects a retrieval strategy only — it never decides conflict. There is **no `CONFLICT` route**.

`QueryRouter` classifies each question at runtime (temperature 0.0) into one of **three** retrieval strategies, each handled by a dedicated handler:

| Question type | Handler | Example |
|---|---|---|
| Fact-based | `RagQueryHandler` — RAG over `narrative_chunks` | "Why did Athena turn Arachne into a spider?" |
| Data | `SqlQueryHandler` — LLM text-to-SQL over entity/relationship tables | "Which Olympians are children of Cronus?" |
| Mixed | `MixedQueryHandler` — SQL filter → inject results → RAG narration | "Which heroes had a divine parent and died at Troy?" |

**Conflict surfacing is a router-independent enrichment step, not a route.** After any handler answers, `QueryService` runs `ConflictProbe` (→ `{subject, claimType}`) → `ConflictLookup` (claim-type-filtered `variant_claims` fetch) → `ConflictSynthesizer`, writing only `conflicts[]` (never `answer`), wrapped so it can never break the primary answer. A conflict-shaped question like "Who were Aphrodite's parents?" therefore surfaces every stored version regardless of which route it took. `RagAgent` additionally carries a conflict-aware backstop for disagreements that were never structured into `variant_claims`. `QueryService` is the only class that knows about all three handlers plus the enrichment step.

## Data Model

**SQL tables (Flyway V1–V14, plus V8_1–V8_3 provenance/normalization additions per DEV-021/022/023, V8_4 embedding upgrade per DEV-028/ADR-013, and V9_1 `entities.subtype` + V9_2 `birth`→`parentage` alias per DEV-040/DEV-042):**
```
entities(id, name, type, generation, domain, subtype)
  -- type ∈ {primordial, titan, olympian, other_god, hero, mortal, monster, nymph}
  -- subtype (V9_1): free-text fine-grained kind (e.g. 'Nereid', 'river god') preserved from
  --   extraction that doesn't fit the coarse type enum; nullable, no CHECK (DEV-040)

relationships(id, from_id→entities, relation, to_id→entities, source_id TEXT→sources, passage_ref)
  -- passage_ref (V8_1): passage-level provenance, populated mechanically from the extraction segment

myths(id, title, location, summary)
myth_participants(myth_id, entity_id, role)

sources(id TEXT PRIMARY KEY, author, work, passage_ref, translation, stance, year_published INT, role TEXT)
  -- id is a human-readable slug e.g. 'apollodorus-bibliotheca'
  -- stance ∈ {poetic-myth, mythographic-handbook, cosmological, hymnic}
  -- role ∈ {spine, primary, selective, stretch}

variant_claims(id, subject_entity_id→entities, claim_type, claim_value, source_id TEXT→sources, trust_tier SMALLINT, passage_ref)
  -- multiple rows per question when sources conflict; Phase 1 seed uses trust_tier=1
  -- passage_ref (V8_1): passage-level provenance so surfaced conflicts cite like RAG answers do (DEV-021)
  -- claim_type is OPEN free-text (no CHECK constraint) by design (ADR-007) — the claim_type_aliases DB table
  --   (V8_2, replaces the planned claim_type_aliases.json per DEV-022) collapses surface variants;
  --   conflict = GROUP BY (subject, normalize(claim_type)) HAVING count(DISTINCT source_id) >= 2
  -- NOTE: the >=2-distinct-sources rule is the OFFLINE DETECTION heuristic only (which conflicts the extractor
  --   emits). Runtime surfacing applies NO source-count gate: ConflictLookup fetches every row for the
  --   subject+claim_type and ConflictSynthesizer formats them. So a hand-added single-source floor case
  --   (Io: Inachus vs Piren, both Apollodorus) is not "detected" as a conflict yet still surfaces at query time.
  -- STORED rows are written with the NORMALIZED canonical claim_type (V12 applies normalize() at promotion),
  --   so runtime ConflictLookup can match by exact equality (claim_type = normalize(probeClaimType)) and both
  --   rows of a conflict share one claim_type value. Surface variants live only in the extraction candidates.
  -- contested relationships keep ONE canonical edge in `relationships` (spine-preferred); the contradiction lives here

narrative_chunks(id, content, content_hash GENERATED AS md5(content), embedding vector(3072), source_id TEXT→sources, passage_ref, metadata JSONB, embedding_model TEXT)
  -- UNIQUE(source_id, passage_ref, content_hash)
  -- chunks are PARAGRAPH-ALIGNED (DEV-034/ADR-014 Amendment 2): one chunk per marker interval, so
  --   passage_ref is the paragraph's corpus-native range ("3.38-3.57", end = next-marker-minus-1, full
  --   prefix on both ends — classical elision is display-only), a bare point for Apollodorus sections /
  --   single-interval paragraphs / book-final+EOF paragraphs (end underivable there), or "Author, Work"
  --   for pre-marker preamble chunks. Oversized paragraphs (>1.2x CHUNK_SIZE) split into sub-chunks that
  --   SHARE the paragraph ref (the only duplicate refs; corpus precision floor); overlap exists only
  --   between such sub-chunks, never across paragraphs.
  --   Shared range helper: ingestion/loader/ref_ranges.py — Stage 4 extraction must reuse it, not re-derive.
  -- metadata.sentence_refs (DEV-033): per-sentence [{ref, start, end}] with char offsets into content;
  --   under paragraph alignment every entry carries the paragraph's start marker (kept for audits/forward-compat)
  -- embedding is vector(3072) since V8_4 (ADR-013, text-embedding-3-large); the HNSW index is a halfvec
  --   EXPRESSION index ((embedding::halfvec(3072)) halfvec_cosine_ops) because plain-vector HNSW caps at
  --   2000 dims — retrieval MUST cast: ORDER BY embedding::halfvec(3072) <=> (?::vector(3072))::halfvec(3072),
  --   or the index is silently bypassed (seq scan)
  -- embedding_model (V8_4, ex-ADR-006 V15): model provenance per row, checked at startup against
  --   app.llm.embedding-model to detect drift

claim_type_aliases(alias TEXT PRIMARY KEY, canonical)
  -- V8_2 (DEV-022): shared normalize() map — Python extraction and Kotlin ConflictLookup both read this
  -- table; normalize(x) = canonical where alias = lower(trim(x)), identity otherwise. Never duplicate in code/JSON.
  -- New surface variants discovered during review are appended via follow-up migrations (e.g. V9_2:
  -- 'birth'→'parentage' per DEV-042), never hardcoded elsewhere.

entity_aliases(id, entity_id→entities, alias TEXT UNIQUE)
  -- cross-cultural aliases: Venus→Aphrodite, Hercules→Heracles, Odysseus→Ulysses
```

**`sources.id` is TEXT (slug), not SERIAL** — stable across DB resets; Python `SourceConfig.source_id: str` must match exactly.

## AI Services (LangChain4j `@AiService`)

Every LLM role is an interface — no inline `ChatLanguageModel.generate()` calls in business logic:

| Interface | Temperature | Role |
|---|---|---|
| `QueryRouter` | 0.0 | Classifies question → `RouteDecision` enum (`SQL`/`RAG`/`MIXED`) |
| `TextToSqlAgent` | 0.0 | Generates SQL from schema prompt + question |
| `RagAgent` | 0.3 | Retrieves narrative chunks, returns `RagResponse{answer, citations}`; conflict-aware backstop for unstructured disagreements |
| `ConflictProbe` | 0.0 | Extracts `{subject, claimType}` for enrichment; no separate `EntityExtractor` interface — Stage 8's `MixedQueryHandler` reuses this bean and reads only `.subject` (Stage 7 Track B1) |

`ConflictSynthesizer` (`ai/ConflictSynthesizer.kt`) is **not** an `@AiService` — `[DEVIATED - see
DEVIATIONS.md #DEV-051]` it is a deterministic, non-LLM mapper (`variant_claims` rows → `List<ConflictEntry>`),
since `conflicts[]` presentation is data-driven (ADR-007 §5) and the DTO already carries every field a
prose pass would add. Formats all attributed versions without picking a winner, same as originally
planned, just without a chat-model round trip.

`ConflictLookup` (in `conflict/`) is a shared component, **not** an `@AiService` — it resolves the entity (exact → alias → trigram) and exposes two fetches over that resolution: a **claim-type-filtered** fetch (`subject_entity_id = ? AND claim_type = normalize(probeClaimType)`) used by the enrichment step, and a **subject-only** fetch (all `claim_type`s for the entity) used only by the `GET /api/v1/conflicts/{entityName}` browse endpoint, which carries no claim-type context. `QueryService`'s enrichment step wires `ConflictProbe` → `ConflictLookup` (claim-type-filtered) → `ConflictSynthesizer` after any route.

`SchemaIntrospector` queries `information_schema` at startup and caches the schema string used in `TextToSqlAgent`'s system prompt. All LLM-generated SQL must pass `SqlSafetyValidator` (SELECT/WITH only; deny-list: DROP, DELETE, INSERT, UPDATE, `;`) before `JdbcTemplate` execution.

## Key Tech Guardrails

Full rules in `docs/TECH_GUARDRAILS.md`. Critical ones:
- **No Spring Security, Redis, Kafka, Spring Cloud, Spring AI, direct OpenAI Java SDK (`com.openai:openai-java`)** — explicitly out of scope for JVM modules; Python ingestion uses the OpenAI Python SDK for embedding only
- **Flyway owns all DDL** — `spring.jpa.hibernate.ddl-auto: validate` in all profiles
- **Read-only runtime DB user** (`zeus_app`) — Flyway uses superuser credentials separately
- **`statement_timeout = '3s'`** on all Hikari connections (cap LLM-generated SQL)
- **TDD** — write failing tests before production code for every handler/service
- **No live LLM calls in tests** — mock all `@AiService` interfaces
- **Testcontainers** for all DB integration tests (PostgreSQL 16 + pgvector); no H2
- **Public-domain translations only** — Frazer 1921, Evelyn-White 1914, Murray 1919–1924; no modern translations
- **No HTML scraping** — corpus loaded from local .txt files in `ingestion/corpus/`
- **Review-gated `variant_claims`** — LLM-extracted candidates (ADR-004), but no row enters the runtime table without explicit per-row developer review and promotion to `trust_tier=1`; no unreviewed automated insertion

## Corpus & Data Sources

Handbook sources (Apollodorus, Hesiod *Theogony*) → primarily SQL + RAG.
(The Phase 1 seed is exactly 6 sources — see `docs/TODO-stage4.md` C1. Hyginus is a *stretch* source per `CONCEPT.md §122`, **not** in the Phase 1 seed.)
Narrative sources (Homer *Iliad*/*Odyssey*, Homeric Hymns, Ovid) → primarily RAG, key relationships also in SQL.

Structured tables: ~60–100 entities (Olympians, Titans, major heroes) hand-curated. Depth of `variant_claims` matters more than breadth.

## Evaluation

16 gold questions across four categories (FACT, DATA, MIXED, CONFLICT) in `evaluation/gold-questions.json`; scored at 3 pts each. Target ≥75% overall. REFUSAL is a fifth planned category whose questions are authored in Phase 2 P4 (ADR-010, per DEV-059). See `docs/IMPLEMENTATION_PLAN.md §7` for full schema and scoring rules.

## Deviation Tracking Protocol

When implementing any planned stage:

1. **Never overwrite** `IMPLEMENTATION_PLAN.md` — it is the authoritative plan; deviations are recorded separately.
2. **Log all deviations** in `docs/DEVIATIONS.md` (append-only) using this format:
   - Stage, Original Plan, What Changed, Reason, Impact, Date
3. **Mark affected TODO items** with `[DEVIATED - see DEVIATIONS.md #DEV-NNN]` inline.
4. **Add a note** to the relevant stage in `IMPLEMENTATION_PLAN.md` of the form:
   `> ⚠️ Deviations occurred in this stage. See DEVIATIONS.md for details.`
5. **Update future stage plans** in `TODO.md` / `TODO-stage1.md` if the deviation changes their input assumptions — be explicit: `"Updated based on DEV-NNN (see DEVIATIONS.md)"`.
6. **Before starting any stage**, re-read `DEVIATIONS.md` to understand what assumptions from prior stages have changed.
