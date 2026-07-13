# blame-zeus

A Greek mythology lore assistant that answers questions with **source attribution and conflict awareness**. Instead of giving one confident answer, it surfaces disagreements between ancient texts and attributes each version to the work it came from.

> "Who were Aphrodite's parents?"
> According to Hesiod (*Theogony*): born from sea foam around the severed genitals of Ouranos.
> According to Homer (*Iliad*): daughter of Zeus and Dione.

## Why

General-purpose LLMs answer mythology questions fluently but hallucinate details, present one version as *the* version, and give no way to ask "who said that?" This system grounds every answer in a curated corpus with per-claim source attribution.

## Four Question Types

| Type | Example | How |
|---|---|---|
| **Fact** | "Why did Athena turn Arachne into a spider?" | RAG over narrative text |
| **Data** | "Which Olympians are children of Cronus?" | LLM text-to-SQL over entity/relationship tables |
| **Mixed** | "Which heroes had a divine parent and died at Troy?" | SQL filter → RAG narration |
| **Conflict** | "Who were Aphrodite's parents?" | Query `variant_claims` table; return all attributed versions |

## Architecture

```
[ingestion — Python offline job]
        ↓  load .txt → clean → chunk → embed
[PostgreSQL 16 + pgvector]
        ↑  SQL queries + vector search
[core-api — Spring Boot 3.2 / Kotlin]  ←→  [OpenAI via LangChain4j]
   ├── POST /api/v1/query
   ├── Swagger UI  /swagger-ui.html
   └── Thymeleaf   /

[telegram-bot — Phase 2]
   └── thin adapter → core-api REST
```

**core-api** is the Q&A brain. It routes each question, runs SQL or RAG (or both), and returns a structured response with `citations[]` and `conflicts[]`. Every LLM role is a LangChain4j `@AiService` interface.

**ingestion** is a standalone Python 3.12+ script — not part of the Gradle build. It loads public-domain plaintext files, chunks them, embeds with `text-embedding-3-large`, and inserts into `narrative_chunks`.

## Data Model

```
entities            — ~60–100 hand-curated: Olympians, Titans, heroes, monsters
relationships       — parent_of, married_to, killed_by (with source attribution)
sources             — author, work, translation, stance, year_published
variant_claims      — multiple rows per contested claim, each citing a source
narrative_chunks    — embedded text segments (vector(3072)) for RAG
entity_aliases      — Venus→Aphrodite, Hercules→Heracles, etc.
myths / myth_participants
```

`variant_claims` is the core differentiator. Each row is one attributed version of a contested fact. When sources disagree, all versions are returned — none is picked as canonical.

## Corpus

Public-domain translations only:

| Source | Translation | Role |
|---|---|---|
| Apollodorus, *Bibliotheca* | Frazer, 1921 | spine |
| Hesiod, *Theogony* | Evelyn-White, 1914 | spine |
| Homer, *Iliad* | Murray, 1919 | spine |
| Homer, *Odyssey* | Murray, 1924 | primary |
| Homeric Hymns | Evelyn-White, 1914 | primary |
| Ovid, *Metamorphoses* | PD verse translation | selective |

Modern translations are excluded.

## Running Locally

**Prerequisites:** Docker, Java 21, Python 3.12+, an OpenAI API key.

**1. Start the database**
```bash
cp .env.example .env   # fill in OPENAI_API_KEY and passwords
docker-compose up -d   # PostgreSQL 16 + pgvector; Flyway runs on core-api startup
```

**2. Run ingestion** (one time)
```bash
cd ingestion
pip install -r requirements.txt
# Place corpus .txt files in ingestion/corpus/ (download from Project Gutenberg / sacred-texts.com)
python main.py
```

**3. Start core-api**
```bash
./gradlew :core-api:bootRun
```

Open `http://localhost:8080` for the web UI or `http://localhost:8080/swagger-ui.html` for the API.

**Full stack with Telegram bot (Phase 2):**
```bash
docker-compose -f docker-compose.full.yml up
```

## Tech Stack

- **core-api / telegram-bot:** Kotlin 1.9 + Spring Boot 3.2 + LangChain4j + Flyway + pgvector
- **ingestion:** Python 3.12 + openai + psycopg2 + pgvector
- **DB:** PostgreSQL 16 + pgvector extension
- **Build:** Gradle Kotlin DSL

## Evaluation

17 gold questions across five categories (FACT, DATA, MIXED, CONFLICT, REFUSAL). Target score: ≥75%. See `evaluation/gold-questions.json` and `docs/IMPLEMENTATION_PLAN.md §7`.

## Docs

- [`docs/CONCEPT.md`](docs/CONCEPT.md) — problem statement, design rationale, source stance model
- [`docs/IMPLEMENTATION_PLAN.md`](docs/IMPLEMENTATION_PLAN.md) — full architecture, handler logic, migration list, test strategy, implementation sequence
- [`docs/TECH_GUARDRAILS.md`](docs/TECH_GUARDRAILS.md) — hard constraints: what to use, what not to add, safety rules
