# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

**blame-zeus** is a Greek Mythology Lore Assistant PoC. Its defining feature is **source attribution and conflict awareness**: rather than giving a single confident answer about a myth, it surfaces disagreements between ancient sources and attributes each version to the text it came from.

Key docs:
- `docs/CONCEPT.md` — full product concept and design rationale
- `docs/IMPLEMENTATION_PLAN.md` — architecture, module layout, data model, handler logic, evaluation, implementation sequence
- `docs/TECH_GUARDRAILS.md` — hard constraints on stack, LLM usage, SQL safety, testing, and what NOT to add

## Tech Stack

- **Language:** Kotlin 1.9.x + JVM 21 (`core-api`, `telegram-bot`); Python 3.12+ (`ingestion`)
- **Framework:** Spring Boot 3.2.x (Jakarta namespace, not `javax.*`)
- **Build:** Gradle Kotlin DSL; shared convention plugin in `buildSrc/`
- **LLM framework:** LangChain4j (JVM services only) — all LLM calls in `core-api` go through `@AiService` interfaces; no direct OpenAI/Anthropic Java SDK in JVM code. The `ingestion` Python job uses the OpenAI Python SDK directly for embedding only — this is intentional and the only authorized exception.
- **LLM provider:** OpenAI for **embedding** (fixed — must match `text-embedding-3-small` used during ingestion; not swappable without re-ingesting the full corpus). **Chat model is provider-agnostic** — all `@AiService` interfaces and handlers are provider-neutral; the only provider-specific code is the beans in `LangChain4jConfig.kt` (Phase 1 default: `OpenAiChatModel`). Swap those beans and add the new provider's LangChain4j starter to change the chat provider. Two separate API key env vars: `OPENAI_API_KEY` for ingestion and embedding, `LLM_API_KEY` for the chat model (both point to the same key in Phase 1). Chat model name injected via `LLM_CHAT_MODEL` env var — no default in `application.yml`, must always be set explicitly.
- **Storage:** Postgres 16 + pgvector — relational tables and `narrative_chunks` vector store in one DB
- **Deployment:** Docker Compose for Phase 1 (DB-only: `docker-compose.yml`; full stack: `docker-compose.full.yml`)

## Service Layout

| Unit | Type | Phase | Responsibility |
|---|---|---|---|
| **core-api** | Spring Boot service | Phase 1 | Q&A brain: route → SQL/RAG → synthesize → cite. REST API + Thymeleaf web UI + Swagger UI. |
| **telegram-bot** | Spring Boot service (thin adapter) | Phase 2 | Telegram consumer. Calls core-api REST. No mythology logic. |
| **ingestion** | Offline Python job | Phase 1 | One-time data prep: load .txt files → clean → chunk → embed → populate DB. Runs and exits; not deployed. Not part of Gradle build. |

Both runtime services share the same Postgres + pgvector instance. `springdoc-openapi` exposes Swagger UI at `/swagger-ui.html`.

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
│       │   ├── routing/        (QueryRouter, RouteDecision)
│       │   ├── ai/             (TextToSqlAgent, RagAgent, ConflictSynthesizer, EntityExtractor)
│       │   ├── handler/        (SqlQueryHandler, RagQueryHandler, ConflictQueryHandler, MixedQueryHandler)
│       │   ├── safety/         (SqlSafetyValidator)
│       │   └── service/        (QueryService — central orchestrator)
│       └── resources/
│           ├── application.yml
│           └── db/migration/   (Flyway V1–V14 + afterMigrate callback)
├── telegram-bot/               (Phase 2)
├── ingestion/                  (Python — excluded from Gradle build)
│   ├── corpus/                 (.txt files — not committed to git)
│   ├── loader/                 (source_registry.py, text_cleaner.py)
│   ├── chunker/                (text_chunker.py)
│   ├── pipeline/               (embedding_pipeline.py)
│   └── main.py
└── evaluation/
    └── gold-questions.json
```

## Query Routing

Four question types, each handled by a dedicated handler:

| Question type | Handler | Example |
|---|---|---|
| Fact-based | `RagQueryHandler` — RAG over `narrative_chunks` | "Why did Athena turn Arachne into a spider?" |
| Data | `SqlQueryHandler` — LLM text-to-SQL over entity/relationship tables | "Which Olympians are children of Cronus?" |
| Mixed | `MixedQueryHandler` — SQL filter → inject results → RAG narration | "Which heroes had a divine parent and died at Troy?" |
| Conflict | `ConflictQueryHandler` — query `variant_claims` → `ConflictSynthesizer` | "Who were Aphrodite's parents?" |

`QueryRouter` classifies each question at runtime (temperature 0.0). `QueryService` is the only class that knows about all four handlers.

## Data Model

**SQL tables (Flyway V1–V14):**
```
entities(id, name, type, generation, domain)
  -- type ∈ {primordial, titan, olympian, other_god, hero, mortal, monster, nymph}

relationships(id, from_id→entities, relation, to_id→entities, source_id TEXT→sources)

myths(id, title, location, summary)
myth_participants(myth_id, entity_id, role)

sources(id TEXT PRIMARY KEY, author, work, passage_ref, translation, stance, year_published INT, role TEXT)
  -- id is a human-readable slug e.g. 'apollodorus-bibliotheca'
  -- stance ∈ {poetic-myth, mythographic-handbook, cosmological, hymnic}
  -- role ∈ {spine, primary, selective, stretch}

variant_claims(id, subject_entity_id→entities, claim_type, claim_value, source_id TEXT→sources, trust_tier SMALLINT)
  -- multiple rows per question when sources conflict; Phase 1 seed uses trust_tier=1

narrative_chunks(id, content, content_hash GENERATED AS md5(content), embedding vector(1536), source_id TEXT→sources, passage_ref, metadata JSONB)
  -- UNIQUE(source_id, passage_ref, content_hash); HNSW index on embedding

entity_aliases(id, entity_id→entities, alias TEXT UNIQUE)
  -- cross-cultural aliases: Venus→Aphrodite, Hercules→Heracles, Odysseus→Ulysses
```

**`sources.id` is TEXT (slug), not SERIAL** — stable across DB resets; Python `SourceConfig.source_id: str` must match exactly.

## AI Services (LangChain4j `@AiService`)

Every LLM role is an interface — no inline `ChatLanguageModel.generate()` calls in business logic:

| Interface | Temperature | Role |
|---|---|---|
| `QueryRouter` | 0.0 | Classifies question → `RouteDecision` enum |
| `TextToSqlAgent` | 0.0 | Generates SQL from schema prompt + question |
| `RagAgent` | 0.3 | Retrieves narrative chunks, returns `RagResponse{answer, citations}` |
| `ConflictSynthesizer` | 0.3 | Formats all attributed versions without picking a winner |
| `EntityExtractor` | 0.0 | Extracts entity name from question for DB lookup |

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
- **Hand-curated `variant_claims`** — no automated extraction

## Corpus & Data Sources

Handbook sources (Apollodorus, Hesiod *Theogony*, Hyginus) → primarily SQL + RAG.
Narrative sources (Homer *Iliad*/*Odyssey*, Homeric Hymns, Ovid) → primarily RAG, key relationships also in SQL.

Structured tables: ~60–100 entities (Olympians, Titans, major heroes) hand-curated. Depth of `variant_claims` matters more than breadth.

## Evaluation

17 gold questions across five categories (FACT, DATA, MIXED, CONFLICT, REFUSAL) in `evaluation/gold-questions.json`; scored at 3 pts each. Target ≥75% overall. See `docs/IMPLEMENTATION_PLAN.md §7` for full schema and scoring rules.
