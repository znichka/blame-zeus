# blame-zeus: Implementation Plan

## 1. Executive Summary

blame-zeus is a Greek mythology lore assistant PoC whose defining feature is source attribution and conflict detection — surfacing disagreements between ancient texts rather than giving a single confident answer. A user asks a natural-language mythology question; the system routes it through SQL, RAG, or a conflict-detection pipeline; and every claim in the answer cites the ancient work it came from.

**Traceability:** CONCEPT.md §4, §5, §10 · SCOPE.md AI requirements · REQIREMENTS.md stack requirements.

**Goals:**
- Working query pipeline covering all four question types (fact, data, mixed, conflict)
- Every answer carries source citations traceable to ancient texts
- Conflict questions return all attributed versions, not one flattened answer
- REST API with Swagger UI and a Thymeleaf web UI for smoke-testing
- Evaluation score ≥75% on 15–20 gold questions

**Non-goals (Phase 1):**
- Cloud deployment (Docker Compose only)
- Authentication or user accounts
- Telegram bot (planned Phase 2; module placeholder only)
- Caching layer, message queues, Spring Cloud
- Fully-automatic seed data with no human review — `variant_claims` always
  requires developer sign-off before `trust_tier=1` (see `docs/adr/adr-004-seed-data-extraction-strategy.md`);
  `entities`/`relationships` are LLM-extracted with a lighter spot-check, not
  hand-typed from scratch
- Ingesting translator/editorial footnotes as a distinct, RAG-citable source —
  footnote markers are stripped as noise during ingestion; footnote content is
  consulted manually only when hand-curating `variant_claims` (§3, V12; see
  `CONCEPT.md §8, §15` for the full rationale and the deferred design)

---

## 2. Architecture

```
[Ingestion Job — offline, Python script]
        ↓  load → clean → chunk → embed
[PostgreSQL 16 + pgvector]
        ↑  SQL queries + vector search
[core-api — Spring Boot 3.2.x]  ←→  [LangChain4j ChatLanguageModel — provider-configurable]
   ├── REST /api/v1/query
   ├── Swagger UI  /swagger-ui.html
   └── Thymeleaf   /

[telegram-bot — Spring Boot 3.2.x, Phase 2]
   └── thin adapter → core-api REST
```

### Module Layout

```
blame-zeus/
├── settings.gradle.kts
├── build.gradle.kts                  (root — versions/plugins only, no code)
├── gradle.properties
├── docker-compose.yml                (postgres+pgvector only)
├── docker-compose.full.yml           (postgres + core-api + telegram-bot)
├── .env.example
│
├── buildSrc/
│   └── src/main/kotlin/
│       └── blame-zeus.kotlin-conventions.gradle.kts
│
├── ingestion/                        (Python — NOT part of Gradle build; explicitly excluded from settings.gradle.kts via comment to prevent IDE/Gradle scanning of .venv artifacts)
│   ├── pyproject.toml
│   ├── requirements.txt
│   ├── main.py
│   ├── config.py
│   ├── loader/
│   │   ├── source_registry.py
│   │   └── text_cleaner.py
│   ├── chunker/
│   │   └── text_chunker.py
│   └── pipeline/
│       └── embedding_pipeline.py
│
├── core-api/
│   ├── build.gradle.kts
│   └── src/main/
│       ├── kotlin/com/blamezeus/coreapi/
│       └── resources/
│           ├── application.yml
│           └── db/migration/
│
└── telegram-bot/
    ├── build.gradle.kts
    └── src/main/kotlin/com/blamezeus/telegrambot/
```

> ⚠️ Deviations occurred building Track D (Stage 4 JPA entities/repositories, D1-D6 complete). See
> `DEVIATIONS.md` #DEV-037: `blame-zeus.kotlin-conventions.gradle.kts` now applies `kotlin("plugin.allopen")`/
> `kotlin("plugin.noarg")` targeting `jakarta.persistence.Entity`/`Embeddable` (completing wiring
> `kotlin-allopen` was added for back in Stage 1 but never applied). New packages:
> `domain/entity/` (`Source`, `EntityRecord`, `Relationship`, `Myth`, `MythParticipant`, `VariantClaim`,
> `NarrativeChunk`) and `repository/` (matching `JpaRepository` interfaces), both under
> `com.blamezeus.coreapi`. D7 (`EntityAlias`) is deliberately not yet present — it's blocked on
> Track C6/`V14` existing, since `ddl-auto: validate` fails the whole module's Spring context if an
> `@Entity` maps to a table that doesn't exist yet.

### Key Dependencies

| Module | Key additions |
|---|---|
| `core-api` | `spring-boot-starter-web`, `spring-boot-starter-data-jpa`, `spring-boot-starter-thymeleaf`, `flyway-core`, `postgresql`, `langchain4j-spring-boot-starter:1.0.x`, `langchain4j-open-ai-spring-boot-starter:1.0.x` *(required permanently for the embedding model — always OpenAI `text-embedding-3-small`, fixed. Also used as the Phase 1 chat provider default; the chat provider is swappable — add the new provider's LangChain4j starter and update the routing/synthesis beans in `LangChain4jConfig.kt` to change it. Do NOT remove this starter when swapping the chat provider — the embedding bean still requires it.)*, `langchain4j-pgvector:1.0.x`, `springdoc-openapi-starter-webmvc-ui:2.5.x` |
| `core-api` (test) | `spring-boot-starter-test`, `com.ninja-squad:springmockk:4.0.2`, `org.testcontainers:junit-jupiter:1.19.x`, `org.testcontainers:postgresql:1.19.x` |
| `ingestion` (Python) | `openai>=1.0`, `psycopg2-binary`, `pgvector`, `tenacity>=8.2`, `python-dotenv` |
| `ingestion` (Python test) | `pytest>=8.0` |
| `telegram-bot` | `spring-boot-starter-web`, `telegrambots-spring-boot-starter:6.9.x` |

---

## 3. Data Model & Flyway Migrations

> ⚠️ Deviations occurred in this section. See DEVIATIONS.md for details — notably DEV-028/ADR-013:
> `narrative_chunks.embedding` is `vector(3072)` (`text-embedding-3-large`) since `V8_4`, the HNSW index
> is a halfvec expression index (retrieval must cast `embedding::halfvec(3072)`), and the table carries an
> `embedding_model` provenance column (ADR-006's planned `V15`, renumbered).

> ⚠️ Amended by ADR-007 — see `docs/adr/adr-007-conflict-detection-and-surfacing.md` and `DEVIATIONS.md` DEV-014.
> `variant_claims.claim_type` is open free-text (no CHECK) by design; V7 already reflects this. Rows in `V12`
> are written with the **normalized canonical** `claim_type` (surface variants collapsed at promotion), so the
> runtime `WHERE subject_entity_id = X AND claim_type = Y` lookup matches by exact equality and both rows of a
> conflict share one value — the `normalize()` map is applied at promotion, not re-applied at query time.
> Contested relationships keep **one canonical edge** in `V11` (default: `sources.role='spine'`) with the
> contradiction recorded in `V12` — competing edges are not stored in the runtime graph.
>
> ⚠️ Also see `DEVIATIONS.md` DEV-018: the V9 row's Homeric Hymns `author` is corrected from `Hesiod` to
> `Anonymous` (slug `hesiod-homeric-hymns` retained). The original `author='Hesiod'` text below is kept
> unamended per the deviation protocol.
>
> ⚠️ Amended by DEV-021/DEV-022 (2026-07-12): `V8_1__add_claim_provenance.sql` adds nullable `passage_ref`
> to `relationships` and `variant_claims` (passage-level provenance, populated mechanically from the
> extraction segment — V11/V12 rows carry it); `V8_2__create_claim_type_aliases.sql` creates and seeds the
> `claim_type_aliases(alias, canonical)` table, replacing the planned `claim_type_aliases.json` as the
> single shared `normalize()` source of truth (readable by both Python extraction and Kotlin
> `ConflictLookup`); `V8_3__add_schema_comments.sql` adds `COMMENT ON` text consumed by `SchemaIntrospector`
> (DEV-023). The V4/V7 rows below are kept unamended per the deviation protocol.

All migrations in `core-api/src/main/resources/db/migration/`. The ingestion job connects to the same DB but does NOT run Flyway — core-api startup runs it.

| Migration | Content |
|---|---|
| `V1__enable_pgvector.sql` | `CREATE EXTENSION IF NOT EXISTS vector; CREATE EXTENSION IF NOT EXISTS pg_trgm;` |
| `V2__create_sources.sql` | `sources(id TEXT PRIMARY KEY, author, work, passage_ref, translation, stance, year_published INTEGER NOT NULL, role TEXT NOT NULL)` — `id` is a human-readable slug (e.g. `'apollodorus-bibliotheca'`, `'hesiod-theogony'`) rather than a SERIAL integer; this makes the Python `SourceConfig.source_id: str` stable across DB resets. `stance CHECK IN ('poetic-myth','mythographic-handbook','cosmological','hymnic')`, `role CHECK IN ('spine','primary','selective','stretch')`. `year_published` is the translator's publication year (e.g. 1921 for Frazer), used to construct full citations like "Hesiod, *Theogony* (Evelyn-White, 1914)". `role` drives ingestion priority: `spine` sources are fully indexed; `stretch` sources are optional. |
| `V3__create_entities.sql` | `entities(id, name UNIQUE, type, generation, domain)` — `type CHECK IN (primordial,titan,olympian,other_god,hero,mortal,monster,nymph)` + `CREATE INDEX idx_entities_name_trgm ON entities USING gin(name gin_trgm_ops);` for fuzzy name matching in `ConflictQueryHandler` step 3 |
| `V4__create_relationships.sql` | `relationships(id, from_id→entities, relation, to_id→entities, source_id TEXT NOT NULL REFERENCES sources(id))` + indexes |
| `V5__create_myths.sql` | `myths(id, title, location, summary)` — structural/organizational container only; no `source_id` FK. Factual myth content lives in `narrative_chunks` (RAG) and `variant_claims` (conflicts). Do not treat this table as authoritative for any factual claim. |
| `V6__create_myth_participants.sql` | `myth_participants(myth_id, entity_id, role)` PK composite |
| `V7__create_variant_claims.sql` | `variant_claims(id, subject_entity_id→entities, claim_type, claim_value, source_id TEXT REFERENCES sources(id), trust_tier SMALLINT NOT NULL DEFAULT 2)` — `trust_tier`: 1=verified hand-curated, 2=reviewed, 3=provisional. All Phase 1 seed rows use `trust_tier=1`. Composite index: `CREATE INDEX idx_variant_claims_subject_type ON variant_claims(subject_entity_id, claim_type)` — covers the primary query pattern `WHERE subject_entity_id = X AND claim_type = Y` and also serves subject-only lookups via the leftmost prefix. The single-column `(claim_type)` index is omitted; if claim-type-only queries appear later, add it then. |
| `V8__create_narrative_chunks.sql` | `narrative_chunks(id, content TEXT NOT NULL, content_hash TEXT GENERATED ALWAYS AS (md5(content)) STORED, embedding vector(1536) NOT NULL, source_id TEXT NOT NULL REFERENCES sources(id), passage_ref TEXT, metadata JSONB)` + `UNIQUE (source_id, passage_ref, content_hash)` (mid-run crash recovery: same chunking params + same content → safe re-run. Re-ingesting after changing chunk size or overlap requires `clear_source_chunks()` first — see §4 — otherwise old chunks accumulate alongside new ones) + HNSW index `(embedding vector_cosine_ops) WITH (m=16, ef_construction=64)` |
| `V9__seed_sources.sql` | **Hand-curated (unaffected by ADR-004).** 6 public-domain sources with explicit text `id` slugs, `year_published`, and `role`: `('apollodorus-bibliotheca', 'Apollodorus', 'Bibliotheca', 'Frazer', 1921, 'spine')`, `('hesiod-theogony', 'Hesiod', 'Theogony', 'Evelyn-White', 1914, 'spine')`, `('hesiod-homeric-hymns', 'Hesiod', 'Homeric Hymns', 'Evelyn-White', 1914, 'primary')`, `('homer-iliad', 'Homer', 'Iliad', 'Murray', 1919, 'spine')`, `('homer-odyssey', 'Homer', 'Odyssey', 'Murray', 1924, 'primary')`, `('ovid-metamorphoses', 'Ovid', 'Metamorphoses', 'PD', null, 'selective')`. All with `ON CONFLICT DO NOTHING`. The slug IDs must exactly match `SourceConfig.source_id` values in `source_registry.py`. |
| `V10__seed_entities.sql` | **LLM-extracted, spot-checked (see §4 Extraction Pipeline / `docs/adr/adr-004-seed-data-extraction-strategy.md`).** ~60–100 entities: 7 primordials, 12 titans, 13 olympians, 9 heroes, ~10 monsters/key mortals. Extraction candidates come from `ingestion/extraction/output/entities_candidates.json`; developer spot-checks names/types before merging into this migration. |
| `V11__seed_relationships.sql` | **LLM-extracted, spot-checked.** Key parent_of, married_to, killed_by rows with source attribution. Candidates from `ingestion/extraction/output/relationships_candidates.json`. |
| `V12__seed_variant_claims.sql` | **Most critical. LLM-extracted candidates, but every row requires explicit developer review before it enters this file** — see ADR-004. Candidates are staged at `trust_tier=3` in `ingestion/extraction/output/variant_claims_candidates.json` (both LLM-flagged in-text disagreements and the supplementary cross-source conflict scan in `conflict_detector.py`); only rows a developer has reviewed and promoted to `trust_tier=1` are inserted here. Minimum coverage is a hard floor regardless of what extraction surfaces — hand-add if missed: Aphrodite parentage (Hesiod vs Homer), Io parentage (Inachus vs Piren per Apollodorus), Achilles death variants |
| `V13__seed_myths.sql` | **Hand-curated (unaffected by ADR-004)** — editorial myth groupings aren't a mechanical extraction target. Key myths with `myth_participants` |
| `V14__create_entity_aliases.sql` | **Hand-curated (unaffected by ADR-004).** `entity_aliases(id, entity_id INTEGER NOT NULL REFERENCES entities(id), alias TEXT NOT NULL, UNIQUE(alias))` — cross-cultural and variant name aliases, e.g. Venus → Aphrodite, Hercules → Heracles, Odysseus → Ulysses. Seed ~20 well-known aliases (reuse `ingestion/extraction/known_aliases.json` as a source list — it's also used at extraction time for entity resolution). Used by `ConflictQueryHandler` to resolve query names before falling back to partial match. |
| `afterMigrate__grant_app_user.sql` | `GRANT SELECT ON ALL TABLES IN SCHEMA public TO zeus_app;` — Flyway callback (not a versioned migration). Runs after every migration set, including no-op runs. Ensures `zeus_app` always has SELECT on any tables added by future migrations, compensating for the fact that `ALTER DEFAULT PRIVILEGES` in `01_readonly_user.sql` only covers tables created in that user's future sessions. |

**`V12` sample:**
```sql
INSERT INTO variant_claims (subject_entity_id, claim_type, claim_value, source_id, trust_tier) VALUES
  ((SELECT id FROM entities WHERE name='Aphrodite'), 'parentage',
   'Born from sea foam around the severed genitals of Ouranos',
   (SELECT id FROM sources WHERE author='Hesiod' AND work='Theogony'), 1),
  ((SELECT id FROM entities WHERE name='Aphrodite'), 'parentage',
   'Daughter of Zeus and Dione',
   (SELECT id FROM sources WHERE author='Homer' AND work='Iliad'), 1)
ON CONFLICT DO NOTHING;
```

---

## 4. Ingestion Job

> ⚠️ Deviations occurred in this section. See DEVIATIONS.md for details — notably DEV-028/ADR-013:
> embedding model is `text-embedding-3-large` (corpus re-embedded), and `store_chunks()` stamps
> `embedding_model` on every row.

> ⚠️ Amended by ADR-007 — see `docs/adr/adr-007-conflict-detection-and-surfacing.md` and `DEVIATIONS.md` DEV-014.
> Conflict detection is generalized: the extractor stores **all** attributed claims (not only `is_contested`),
> and `conflict_detector.py` becomes a single GROUP-BY pass over *all* candidate claims keyed on
> `(subject, normalize(claim_type))` `HAVING count(DISTINCT source_id) >= 2` — not a relationships-only scan.
> A new `ingestion/extraction/claim_type_aliases.json` + `normalize()` helper collapses surface variants.

**Language:** Python 3.12+. Standalone script — not part of the Gradle build.  
**Entry point:** `ingestion/main.py`

### Setup

```
ingestion/
├── pyproject.toml          (or requirements.txt)
├── config.py               (reads env vars via python-dotenv)
├── corpus/                 (local .txt files — NOT committed to git if large)
│   ├── apollodorus_bibliotheca_frazer1921.txt
│   ├── hesiod_theogony_evelynwhite1914.txt
│   ├── hesiod_homeric_hymns_evelynwhite1914.txt
│   ├── homer_iliad_murray1919.txt
│   ├── homer_odyssey_murray1924.txt
│   └── ovid_metamorphoses_pd.txt
├── loader/
│   ├── source_registry.py  (file path + source_id per source)
│   └── text_cleaner.py     (strip footnotes, normalize whitespace)
├── chunker/
│   └── text_chunker.py     (sliding window: size=1500 chars, overlap=200)
├── pipeline/
│   └── embedding_pipeline.py  (OpenAI embeddings + psycopg2 + pgvector)
└── main.py
```

**`requirements.txt`:**
```
openai>=1.0
psycopg2-binary
pgvector
tenacity>=8.2
python-dotenv
```

### Key Implementation Notes

**`source_registry.py`** — list of `SourceConfig` dataclasses:

```python
@dataclass
class SourceConfig:
    source_id: str  # text slug matching sources.id in DB, e.g. 'apollodorus-bibliotheca'
    author: str
    work: str
    file_path: str  # relative to ingestion/, e.g. corpus/apollodorus_bibliotheca_frazer1921.txt
    passage_ref_extractor: Callable[[str], list[tuple[int, str]]]
    # Returns list of (char_offset, ref_string) pairs, sorted ascending by offset.
    # The chunker uses these to assign the most-recently-seen ref to each chunk.
```

`source_id` must match the seeded `sources` table FK. Source .txt files are prepared once per source and stored locally in `corpus/` before running ingestion — origin differs by source, since not every translation has a ready-made plaintext edition:

- **Apollodorus (Frazer, 1921)** is not on Project Gutenberg or sacred-texts.com — it's still in copyright renewal limbo there despite being public domain. Source: the Theoi Classical Texts Library (`theoi.com/Text/Apollodorus{1,2,3}.html` + `ApollodorusE.html` for the Epitome). Developer manually copies the text from these four pages (in order) into `apollodorus_bibliotheca_frazer1921.txt`; the Theoi layout presents Frazer's translation as one paragraph per canonical section, each prefixed with its bracketed `[book.chapter.section]` reference — see the extractor row below. Preserve these bracketed markers when preparing the file.
- **Hesiod, Homer, Homeric Hymns** (Evelyn-White / Murray) — sourced from Project Gutenberg / sacred-texts.com plaintext exports as originally planned.

**`text_cleaner.py`** — `re.sub(r'\[\d+\]', '', text)` to strip footnote markers, collapse multi-whitespace, normalize smart quotes. Also strips page headers and running titles common in Gutenberg plaintext files (e.g., lines matching `^[A-Z\s]+$` at the top of pages). This regex only matches brackets containing pure digits, so it does not touch the `[book.chapter.section]` passage markers (which contain dots) — no ordering dependency between footnote-stripping and passage-ref extraction.

**Footnote content is intentionally discarded here, not archived.** This strip-and-drop behavior is a deliberate scope decision, not an oversight: footnote text (Frazer's especially) is never fetched, chunked, or embedded, and there is no `sources` row for translator commentary. It is left for a human to read directly off the source site when hand-curating `V12__seed_variant_claims.sql`. See `CONCEPT.md §8, §15` for the full rationale and the deferred design.

**Passage reference extraction — per-source strategy:**

> ⚠️ Deviations occurred in this stage. See DEVIATIONS.md #DEV-029 — the marker table below does not match the real corpus files (bare `[N]` line markers instead of `[ll. N-M]` ranges, Arabic not Roman `BOOK` headers, no literal "HYMN" word in hymn headers), and the shipped extractors emit standard citation form (`"1.194"`, `"2.90"`, `"116"`) rather than the raw scraped shape shown here. The citation-notation choice itself is now a formal decision — see **ADR-014**.
>
> ⚠️ Also amended by DEV-033 + DEV-034 (see DEVIATIONS.md and ADR-014 Amendments 1–2): the chunker no longer cuts 1500-char windows through the text — **chunk boundaries snap to marker boundaries** (one chunk per corpus paragraph; oversized paragraphs split into sub-chunks sharing the paragraph's ref), and a chunk's `passage_ref` is the paragraph's corpus-native range (`"3.38-3.57"`, end = next-marker-minus-1 via `loader/ref_ranges.py`) with per-sentence refs stored in `metadata.sentence_refs`.

Each `SourceConfig` carries a `passage_ref_extractor` that pre-scans the cleaned text and returns `list[tuple[int, str]]` — (character offset, human-readable ref). The chunker does a single pre-scan pass, then for each chunk looks up the last ref with offset ≤ chunk start.

| Source | Marker pattern in .txt | Extractor regex | Example ref |
|---|---|---|---|
| Apollodorus *Bibliotheca* | Bracketed section numbers at paragraph start (Theoi format): `[1.1.1]`, `[1.2.3]` | `r'(?m)^\s*\[?(\d+\.\s*\d+\.\s*\d+)\]?'` | `1.1.1` |
| Hesiod *Theogony* / *Works and Days* | Line citations in brackets: `[ll. 116-138]` | `r'\[ll?\.\s*(\d+(?:[–\-]\d+)?)\]'` | `ll. 116-138` |
| Homeric Hymns | Hymn header + lines: `HYMN I. TO DIONYSUS` … `[ll. 1-21]` | Book: `r'HYMN\s+([IVXLCDM]+)\.\s+TO\s+(\w+)'`; lines same as Hesiod | `Hymn I (To Dionysus) ll. 1-21` |
| Homer *Iliad* / *Odyssey* | Book header `BOOK I` then line refs `[l. 1]` or `[ll. 1-7]` | Book: `r'^BOOK\s+([IVXLCDM]+)'` (multiline); lines: `r'\[ll?\.\s*(\d+(?:[–\-]\d+)?)\]'` | `Book I ll. 1-7` |
| Ovid *Metamorphoses* | Book header `BOOK I` then story title on its own line in ALL CAPS | Book: `r'^BOOK\s+([IVXLCDM]+)'`; story: `r'^([A-Z][A-Z\s]{4,})\s*$'` (multiline, after book marker) | `Book I: The Creation` |

Extractor helper pattern (same shape for all sources):

```python
def apollodorus_refs(text: str) -> list[tuple[int, str]]:
    return [(m.start(), m.group(1))
            for m in re.finditer(r'(?m)^\s*\[?(\d+\.\s*\d+\.\s*\d+)\]?', text)]

def homer_refs(text: str) -> list[tuple[int, str]]:
    results = []
    current_book = ""
    for m in re.finditer(
            r'(?m)^BOOK\s+([IVXLCDM]+)|\[ll?\.\s*(\d+(?:[–\-]\d+)?)\]', text):
        if m.group(1):
            current_book = f"Book {m.group(1)}"
        elif m.group(2) and current_book:
            results.append((m.start(), f"{current_book} ll. {m.group(2)}"))
    return results
```

If no marker precedes a chunk (text before the first marker), use `f"{author}, {work}"` as fallback.

**`text_chunker.py`** — two-phase structural approach: split into sentences first, then accumulate to target size with a rolling sentence-count overlap. This eliminates offset drift from dynamic boundary snapping and produces deterministic chunk boundaries.

```python
CHUNK_SIZE = 1500        # target chars
OVERLAP_SENTENCES = 2    # sentences carried into next chunk's start

def split_sentences(text: str) -> list[tuple[int, str]]:
    # Returns [(char_offset, sentence_text), ...]
    results, pos = [], 0
    for m in re.finditer(r'(?<=[.!?])\s+', text):
        sent = text[pos:m.start() + 1].strip()
        if sent:
            results.append((pos, sent))
        pos = m.end()
    if pos < len(text):
        results.append((pos, text[pos:].strip()))
    return results

def chunk(text: str, source_id: int, author: str, work: str,
          extractor: Callable[[str], list[tuple[int, str]]]) -> list[Chunk]:
    refs = extractor(text)          # [(offset, ref_string), ...]
    sentences = split_sentences(text)
    chunks = []
    i = 0
    while i < len(sentences):
        buf: list[tuple[int, str]] = []
        start_offset = sentences[i][0]
        while i < len(sentences) and sum(len(s) for _, s in buf) < CHUNK_SIZE:
            buf.append(sentences[i])
            i += 1
        chunk_text = " ".join(s for _, s in buf)
        passage_ref = _nearest_ref(refs, start_offset) or f"{author}, {work}"
        chunks.append(Chunk(chunk_text, source_id, passage_ref, author, work,
                            start_offset=start_offset))
        i -= OVERLAP_SENTENCES      # roll back for overlap
        if i < 0:
            break
    return chunks

def _nearest_ref(refs: list[tuple[int, str]], pos: int) -> str | None:
    # Last ref with offset <= pos (binary search or linear scan)
    result = None
    for offset, ref in refs:
        if offset <= pos:
            result = ref
        else:
            break
    return result
```

`Chunk` dataclass gains `start_offset: int` — the character position of the first sentence in the chunk within the cleaned text. `_nearest_ref` uses `start_offset` rather than a sliding `i` cursor, so passage refs align precisely with the actual chunk content regardless of sentence lengths.

> ⚠️ Amended by DEV-024 (see `DEVIATIONS.md`; follows DEV-013): `store_chunks` now pre-computes
> `md5(content)` in Python and skips chunks whose `(source_id, passage_ref, content_hash)` already
> exists **before** calling the embeddings API (re-runs cost zero OpenAI calls), and commits per
> 20-chunk batch instead of once at the end (a crash loses at most one batch). `ON CONFLICT DO
> NOTHING` remains as the backstop. The snippet below is kept unamended per the deviation protocol.

**`embedding_pipeline.py`**:
```python
import json
import numpy as np
import psycopg2
from pgvector.psycopg2 import register_vector
from openai import OpenAI

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])

@retry(wait=wait_exponential(multiplier=1, min=2, max=60),
       stop=stop_after_attempt(5),
       reraise=True)
def embed_batch(texts: list[str]) -> list[list[float]]:
    response = client.embeddings.create(model="text-embedding-3-small", input=texts)
    return [item.embedding for item in response.data]

def store_chunks(conn, chunks: list[Chunk]) -> None:
    register_vector(conn)
    texts = [c.text for c in chunks]
    embeddings = embed_batch(texts)
    with conn.cursor() as cur:
        for chunk, embedding in zip(chunks, embeddings):
            cur.execute(
                """INSERT INTO narrative_chunks
                   (content, embedding, source_id, passage_ref, metadata)
                   VALUES (%s, %s, %s, %s, %s)
                   ON CONFLICT (source_id, passage_ref, content_hash) DO NOTHING""",
                (chunk.text, np.array(embedding), chunk.source_id,
                 chunk.passage_ref,
                 json.dumps({
                     "source_id": chunk.source_id,
                     "author": chunk.author,
                     "work": chunk.work,
                     "passage_ref": chunk.passage_ref,
                     "chunk_size": len(chunk.text),
                     "overlap_sentences": OVERLAP_SENTENCES
                 }))
            )
    conn.commit()
```

Batch size: 20 chunks per `embed_batch` call. 100 chunks × 1500 chars ≈ 37,500 tokens and risks hitting OpenAI's per-request token limit. `embed_batch` is decorated with `@retry` (tenacity: exponential backoff, 2–60s, 5 attempts, reraise on exhaustion). The import block at the top of `embedding_pipeline.py` must include `from tenacity import retry, stop_after_attempt, wait_exponential`.

**Pre-ingestion helpers (add to `embedding_pipeline.py` or a new `db_utils.py`):**

```python
def validate_source_ids(conn, registry: list[SourceConfig]) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM sources")
        existing_ids = {row[0] for row in cur.fetchall()}
    missing = [s for s in registry if s.source_id not in existing_ids]
    if missing:
        raise RuntimeError(
            f"Source IDs not found in DB: {[s.source_id for s in missing]}. "
            f"Run core-api first to apply Flyway migrations and seed sources."
        )

def clear_source_chunks(conn, source_id: int) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM narrative_chunks WHERE source_id = %s", (source_id,))
    conn.commit()
    print(f"Cleared existing chunks for source_id={source_id}")
```

`validate_source_ids` surfaces FK violations immediately rather than after hundreds of failed inserts. `clear_source_chunks` is a manual utility — call it before re-ingesting only when chunk size or overlap has changed. The `content_hash` constraint won't catch old chunks that differ only in boundaries; `ON CONFLICT DO NOTHING` handles normal re-runs without pre-deletion.

**`main.py`** — `load_dotenv()` must be called before any `from config import ...` statement. Python evaluates top-level module imports at parse time, so importing from `config` before calling `load_dotenv()` would read env vars from the environment before the `.env` file is loaded:
```python
from dotenv import load_dotenv
load_dotenv()                   # MUST precede all config imports

from loader.source_registry import SOURCE_REGISTRY
from pipeline.embedding_pipeline import store_chunks, validate_source_ids
from chunker.text_chunker import chunk
from loader.text_cleaner import clean
import psycopg2
import config

conn = psycopg2.connect(...)
validate_source_ids(conn, SOURCE_REGISTRY)  # fail fast if DB is not seeded
for source in SOURCE_REGISTRY:
    raw = Path(source.file_path).read_text(encoding="utf-8")
    cleaned = clean(raw)
    chunks = chunk(cleaned, source.source_id, source.author, source.work,
                   source.passage_ref_extractor)
    store_chunks(conn, chunks)  # ON CONFLICT DO NOTHING skips existing rows
conn.close()
```

**Run:**
```bash
cd ingestion
pip install -r requirements.txt   # or: uv sync
OPENAI_API_KEY=... POSTGRES_HOST=localhost python main.py
```

Place .txt files in `ingestion/corpus/` before running. Start with Apollodorus (smallest, most structured) and verify rows in `narrative_chunks` before ingesting all sources.

### Extraction Pipeline (Seed Data Generation)

> ⚠️ Amended by ADR-007 — `conflict_detector.py` runs one GROUP-BY over *all* candidate claims (relationship
> candidates mapped in: `parent_of → parentage`, `married_to → marriage`, `killed_by → death`); the extractor
> hints (not restricts) `claim_type` and stores every attributed claim. The relation→claim_type targets are
> the same canonicals as `claim_type_aliases.json`, so a death disagreement split between a `killed_by` edge and
> free-text prose groups under one `death` key (not `slaying` vs `death_manner`). See `DEVIATIONS.md` DEV-014, DEV-020.
>
> ⚠️ Deviations occurred building this pipeline (Track A, complete). See `DEVIATIONS.md` #DEV-036: the
> passage-segmentation helper groups consecutive marker intervals up to a size cap (`SEGMENT_SIZE`), not
> blank-line paragraphs — `text_cleaner.clean()` collapses blank-line runs before segmentation ever sees the
> text, so no blank-line signal survives to group on. Also, `ExtractedRelationship`/`ExtractedVariantClaim`
> carry a `source_id` field alongside `passage_ref` (both `SkipJsonSchema`-hidden from the LLM, stamped
> mechanically post-parse), extending DEV-021's `passage_ref`-only precedent to cover source attribution too.

See `docs/adr/adr-004-seed-data-extraction-strategy.md` for the full decision
record. Runs **after** corpus ingestion (needs real cleaned text to extract
from), **offline**, and writes reviewable candidate files — it never inserts
into the database directly. Entities and relationships get a developer
spot-check before merging; `variant_claims` candidates require explicit
per-row approval (`trust_tier=3` → `trust_tier=1`) before they enter `V12`.

```
ingestion/
├── extraction/
│   ├── schema.py             # Pydantic models mirroring V10–V12:
│   │                         #   ExtractedEntity, ExtractedRelationship (+ is_contested), ExtractedVariantClaim
│   ├── known_aliases.json    # Roman/cross-cultural equivalents; also a reference list for hand-curated V14
│   ├── entity_resolver.py    # in-memory dedup: exact name → known_aliases → rapidfuzz fuzzy match
│   ├── claim_extractor.py    # instructor + OpenAI chat completions, per-source extraction hints, tenacity retry
│   ├── conflict_detector.py  # supplementary pass: same subject+claim_type, different source_id → extra variant_claims candidates
│   └── run_extraction.py     # entry point → writes extraction/output/*.json
└── extraction/output/
    ├── entities_candidates.json
    ├── relationships_candidates.json
    └── variant_claims_candidates.json   # every row trust_tier=3 until reviewed
```

**`schema.py`** — Pydantic models scoped exactly to this project's schema (not the broader entity/claim/conflict/place/event schema considered and rejected in ADR-004):

```python
class ExtractedEntity(BaseModel):
    name: str
    type: str            # must match entities.type CHECK values
    generation: int | None = None
    domain: str | None = None

class ExtractedRelationship(BaseModel):
    from_name: str
    relation: str         # parent_of, married_to, killed_by
    to_name: str
    is_contested: bool = False   # set true when the source text itself signals disagreement

class ExtractedVariantClaim(BaseModel):
    subject_name: str
    claim_type: str
    claim_value: str
```

> ⚠️ Amended by ADR-008 — the extraction model is now **Claude Opus 4.8** (`claude-opus-4-8`) via
> `instructor.from_anthropic(Anthropic(...))`, not `gpt-4o` via `instructor.from_openai(OpenAI(...))`.
> The env var is `EXTRACTION_MODEL=claude-opus-4-8` and the client reads `ANTHROPIC_API_KEY`; add the
> `anthropic` package to `requirements.txt`. The `instructor` pattern is otherwise unchanged (it now
> layers on an Anthropic client, not the `openai` one). See `DEVIATIONS.md` DEV-015.

**`claim_extractor.py`** — uses `instructor` (Pydantic-validated structured output with automatic retry on schema-invalid responses, layered on the same `openai` client instance — not a separate LLM framework) instead of hand-parsing JSON:

```python
import instructor
from openai import OpenAI
from tenacity import retry, stop_after_attempt, wait_exponential

client = instructor.from_openai(OpenAI(api_key=os.environ["OPENAI_API_KEY"]))

SOURCE_HINTS = {
    "apollodorus-bibliotheca": "Flag phrases like 'others say' or 'some say' as is_contested=true — "
                               "this is a systematic handbook that names variant accounts inline.",
    "hesiod-theogony": "Focus on divine-generation sequences; primordials (Chaos, Gaia, Tartarus) are entities too.",
}

@retry(wait=wait_exponential(multiplier=1, min=2, max=60), stop=stop_after_attempt(3), reraise=True)
def extract(segment: PassageSegment) -> ExtractedFacts:
    return client.chat.completions.create(
        model=EXTRACTION_MODEL,   # e.g. "gpt-4o" — distinct from EMBEDDING_MODEL
        response_model=ExtractedFacts,
        messages=[
            {"role": "system", "content": "Extract only what is explicitly stated. Do not infer or invent."},
            {"role": "user", "content": f"Source: {segment.author}, {segment.passage_ref}\n"
                                        f"{SOURCE_HINTS.get(segment.source_id, '')}\n\n{segment.text}"},
        ],
    )
```

Extraction runs on **passage-ref-aligned segments**, not the 1500-char RAG
chunks — reuse the same `passage_ref_extractor` scan from the section above,
but group whole sections between consecutive ref boundaries so a full
genealogical statement isn't split mid-claim across windows.

**`entity_resolver.py`** — dedupes candidate names across chunks/sources *before* they're written to the candidate files, so the same entity mentioned in Apollodorus and Hesiod doesn't produce two rows:

```python
from rapidfuzz import fuzz
import json

known_aliases = json.loads(Path("extraction/known_aliases.json").read_text())

def resolve(name: str, seen_names: list[str]) -> str:
    if name in seen_names:
        return name
    for canonical, aliases in known_aliases.items():
        if name in aliases:
            return canonical
    best = max(seen_names, key=lambda n: fuzz.ratio(name, n), default=None)
    if best and fuzz.ratio(name, best) >= 88:
        return best   # log this — a fuzzy merge is worth a second look during spot-check
    return name
```

This is corpus-time, in-memory resolution to keep candidate files clean — a
different concern from `ConflictQueryHandler`'s runtime `pg_trgm` fuzzy match
(§5), which resolves a *user's* typed entity name against the *already-seeded*
`entities` table at query time. Both use fuzzy matching; neither replaces the
other.

**`conflict_detector.py`** — supplements the LLM's explicit `is_contested`
flag with a mechanical pass over extracted relationship candidates: same
`subject_name` + `relation` (e.g. `parent_of`), different `source_id` → an
additional `variant_claims` candidate, since two sources disagreeing on a
parent is itself a conflict even if neither source's text uses "some say"
phrasing.

**New `requirements.txt` additions:** `instructor>=1.3.0`, `rapidfuzz>=3.0.0` — both ingestion-only.

**Review workflow (`ingestion/notebooks/`):**
1. `01_test_extraction.ipynb` — tune the extraction prompt against Apollodorus (the spine source) on 5–10 segments before running the full corpus. If quality is good there, the rest follows — Apollodorus is the most systematic and structurally predictable of the six sources.
2. `02_verify_conflicts.ipynb` — load `variant_claims_candidates.json`, review each row against its `passage_ref` in the source text, promote approved rows (edit `trust_tier` to `1`) into `V12__seed_variant_claims.sql` by hand. Cross-check that the three minimum-coverage conflicts (Aphrodite, Io, Achilles) are present; hand-add any that extraction missed.

`entities_candidates.json` and `relationships_candidates.json` get a lighter pass — skim for obviously wrong types or duplicate names, then merge into `V10`/`V11` directly.

---

## 5. Core-API

> ⚠️ Deviations occurred in this section. See DEVIATIONS.md for details — notably DEV-028/ADR-013 (with
> DEV-025): the Stage 6 retriever's cosine query must cast to the halfvec expression index —
> `ORDER BY embedding::halfvec(3072) <=> (?::vector(3072))::halfvec(3072)` — and the embedding model is
> `text-embedding-3-large`; the `PgVectorEmbeddingStore` snippet below (`.dimension(1536)`) predates both.

> ⚠️ Amended by ADR-007 — see `docs/adr/adr-007-conflict-detection-and-surfacing.md` and `DEVIATIONS.md` DEV-014.
> `RouteDecision` is `SQL | RAG | MIXED` (no `CONFLICT`); `QueryRouter` never emits a conflict route.
> `ConflictQueryHandler` is **deleted** — its entity resolution + `variant_claims` fetch move into a shared
> `ConflictLookup`. A new `ConflictProbe` (`@AiService`, temp 0.0 → `{subject, claimType}`; may fold into
> `EntityExtractor`) drives a router-independent enrichment step in `QueryService`: after any answer,
> `ConflictProbe` → `ConflictLookup` (claim-type-filtered fetch) → `ConflictSynthesizer`, writing only
> `conflicts[]` (never `answer`), wrapped so it never breaks the primary answer. `RagAgent`'s system message
> gains a conflict-aware disagreement backstop instruction. The `QueryRouter`, `ConflictQueryHandler`, and
> `QueryService` snippets below predate this and are retained for context only.

### Package Structure

```
core-api/src/main/kotlin/com/blamezeus/coreapi/
├── CoreApiApplication.kt
├── config/
│   ├── LangChain4jConfig.kt          (all LangChain4j bean wiring)
│   ├── SchemaIntrospector.kt         (queries information_schema at startup, builds SQL prompt fragment)
│   └── OpenApiConfig.kt              (Springdoc customization)
├── controller/
│   ├── QueryController.kt            (POST /api/v1/query, GET /api/v1/*)
│   └── WebController.kt              (GET /, POST /web/query — Thymeleaf)
├── domain/
│   ├── entity/                       (JPA @Entity classes)
│   └── dto/                          (QueryRequest, QueryResponse, Citation, ConflictEntry, RagResponse)
├── repository/                       (Spring Data JPA interfaces)
├── routing/
│   ├── QueryRouter.kt                (@AiService interface → RouteDecision)
│   └── RouteDecision.kt              (enum: SQL, RAG, MIXED, CONFLICT)
├── ai/
│   ├── TextToSqlAgent.kt             (@AiService — returns SQL string)
│   ├── RagAgent.kt                   (@AiService — wired with ContentRetriever)
│   ├── ConflictSynthesizer.kt        (@AiService — presents all versions without picking winner)
│   └── EntityExtractor.kt            (@AiService — extracts entity name from question)
├── handler/
│   ├── SqlQueryHandler.kt
│   ├── RagQueryHandler.kt
│   ├── ConflictQueryHandler.kt
│   └── MixedQueryHandler.kt
├── safety/SqlSafetyValidator.kt
└── service/QueryService.kt           (routes question to correct handler)
```

### AI Services

**`QueryRouter`** — system message classifies question into SQL/RAG/MIXED/CONFLICT. Returns `RouteDecision` enum directly. Temperature 0.0.

**`TextToSqlAgent`** — system message uses a `{{schema}}` placeholder populated at call time from `SchemaIntrospector.buildSchemaPrompt()`. Returns raw SQL string. Rules enforced in prompt: SELECT only, use ILIKE for names, use WITH RECURSIVE for lineage, JOIN sources for attribution when querying relationship data (`relationships.source_id → sources`) or claims (`variant_claims.source_id → sources`); for direct entity attribute queries (`entities.type`, `entities.generation`, `entities.domain`) no source attribution is available — these are curated classifications without source FKs, do not fabricate a join. Temperature 0.0. Interface:
```kotlin
interface TextToSqlAgent {
    fun generateSql(@V("schema") schema: String, @V("question") question: String): String
}
```
`SchemaIntrospector` queries `information_schema.columns` for the application tables on first call and caches the result — the schema string is built once at startup, not per-request:

> ⚠️ Amended by DEV-023 (see `DEVIATIONS.md`): the implemented class does **not** use the hardcoded
> `listOf(...)` below — tables are auto-enumerated from `information_schema` (minus
> `flyway_schema_history`), so new migrations self-register in the prompt; and each table additionally
> emits column types, foreign keys, CHECK clauses, `COMMENT ON` text (`V8_3`), and live `SELECT DISTINCT`
> value vocabularies for `relationships.relation` / `variant_claims.claim_type`. ADR-009's "register the
> table in SchemaIntrospector" action item is thereby a no-op. The snippet below is kept unamended per
> the deviation protocol.

```kotlin
@Component
class SchemaIntrospector(private val jdbcTemplate: JdbcTemplate) {
    private val schemaPrompt: String by lazy { buildSchemaPrompt() }

    fun get(): String = schemaPrompt

    private fun buildSchemaPrompt(): String {
        val tables = listOf("entities", "relationships", "myths", "myth_participants",
                            "sources", "variant_claims", "narrative_chunks")
        return tables.joinToString("\n") { table ->
            val cols = jdbcTemplate.queryForList(
                "SELECT column_name FROM information_schema.columns " +
                "WHERE table_name = ? ORDER BY ordinal_position", table)
                .map { it["column_name"] }
            "$table(${cols.joinToString(", ")})"
        }
    }
}
```

**`RagAgent`** — wired with `ContentRetriever` (maxResults=5, minScore=0.65). Returns structured `RagResponse` rather than free text, so citations are never parsed from prose. Temperature 0.3:
```kotlin
data class RagResponse(
    val answer: String,
    val citations: List<Citation>
)

@AiService
interface RagAgent {
    @SystemMessage("""
        You are a Greek mythology scholar. Answer using ONLY the provided context.
        Return your answer as JSON matching this exact structure:
        {"answer": "your answer text", "citations": [{"author": "...", "work": "...", "passageRef": "..."}]}
        Cite every factual claim. If the context does not support an answer,
        set answer to a sentence explaining this and citations to [].
    """)
    fun answer(@UserMessage question: String): RagResponse
}
```
LangChain4j `@AiService` resolves `RagResponse` via JSON mode: the `@SystemMessage` instructs the model to return JSON matching the schema, and LangChain4j deserializes it automatically. Without `@SystemMessage` specifying the JSON structure, deserialization of `RagResponse` fails at runtime. `minScore=0.65` is the starting value; tune against gold questions after corpus ingestion (see §7).

**`ConflictSynthesizer`** — receives pre-built conflict summary string; formats each version as `"According to [Author], [Work]: [claim]."` with no winner chosen. Temperature 0.3.

**`EntityExtractor`** — returns entity name for DB lookup. Used by `ConflictQueryHandler` and `MixedQueryHandler`. Temperature 0.0.

### `LangChain4jConfig` Key Beans

> ⚠️ Amended by ADR-008 — the chat beans use **`AnthropicChatModel`** (Claude Haiku 4.5,
> `claude-haiku-4-5-20251001`), not `OpenAiChatModel`; add `langchain4j-anthropic-spring-boot-starter`
> and keep `langchain4j-open-ai-spring-boot-starter` (the embedding bean still needs it). `LLM_API_KEY`
> now holds an Anthropic key. Per-role temps (0.0 / 0.3) and the fixed OpenAI embedding bean are
> unchanged. See `DEVIATIONS.md` DEV-015. (Embedding model name is also now injected via
> `app.llm.embedding-model` per ADR-006 rather than hardcoded — that bean edit is deferred.)
>
> ⚠️ Amended by DEV-025 (see `DEVIATIONS.md`): the `embeddingStore`/`contentRetriever` beans below are
> **dropped**. Verified against the pinned `langchain4j-pgvector:1.0.0-beta5` jar: `PgVectorEmbeddingStore`
> hardcodes its own `embedding_id UUID PRIMARY KEY, embedding, text, metadata` schema in its CREATE/INSERT/
> SELECT statements with no column mapping, so `createTable(false)` over `narrative_chunks(id, content, …)`
> fails at retrieval (`column "text" does not exist`). Stage 6 implements a small custom `ContentRetriever`
> over `JdbcTemplate` instead (embed query → `ORDER BY embedding <=> ? LIMIT 5`, minScore filter, returning
> `source_id`/`passage_ref` for citations). The snippet below is kept unamended per the deviation protocol.

```kotlin
// Chat model — provider-configurable. OpenAiChatModel is the Phase 1 default; all @AiService interfaces
// and handlers are provider-neutral. To swap the chat provider: replace OpenAiChatModel with another
// LangChain4j ChatLanguageModel (e.g. AnthropicChatModel, VertexAiGeminiChatModel), add that
// provider's LangChain4j starter dependency (keep langchain4j-open-ai-spring-boot-starter — the
// embedding model still requires it), and update LLM_CHAT_MODEL / LLM_API_KEY in application.yml.
@Value("\${app.llm.chat-api-key}") private lateinit var chatApiKey: String
@Value("\${app.llm.chat-model}") private lateinit var chatModelName: String

@Bean @Qualifier("routingModel") fun routingModel(): ChatLanguageModel =
    OpenAiChatModel.builder().apiKey(chatApiKey).modelName(chatModelName).temperature(0.0).build()

@Bean @Qualifier("synthesisModel") fun synthesisModel(): ChatLanguageModel =
    OpenAiChatModel.builder().apiKey(chatApiKey).modelName(chatModelName).temperature(0.3).build()

// Embedding model — intentionally fixed to OpenAI text-embedding-3-small. Must match the model
// used during ingestion. Uses a separate key (app.llm.embedding-api-key) so the chat provider
// can be swapped independently. Do not change this bean without re-ingesting the full corpus.
@Value("\${app.llm.embedding-api-key}") private lateinit var embeddingApiKey: String

@Bean fun embeddingModel(): EmbeddingModel =
    OpenAiEmbeddingModel.builder().apiKey(embeddingApiKey).modelName("text-embedding-3-small").build()

@Bean fun embeddingStore(): EmbeddingStore<TextSegment> =
    PgVectorEmbeddingStore.builder().table("narrative_chunks").dimension(1536).createTable(false).build()

@Bean fun contentRetriever(store, model): ContentRetriever =
    EmbeddingStoreContentRetriever.builder().maxResults(5).minScore(0.65).build()
// minScore=0.65 is the tuning starting point; adjust after running gold questions against the real corpus
```

### Handler Logic

**`SqlQueryHandler`:**

```kotlin
@Component
class SqlQueryHandler(
    private val textToSqlAgent: TextToSqlAgent,
    private val schemaIntrospector: SchemaIntrospector,
    private val validator: SqlSafetyValidator,
    private val jdbcTemplate: JdbcTemplate
)
```

`textToSqlAgent.generateSql(schemaIntrospector.get(), question)` → `validator.validate(sql)` → `jdbcTemplate.queryForList(sql)` → format rows + extract citations from result columns. `SchemaIntrospector` must be explicitly injected here; the LangChain4j `@AiService` wiring can obscure where the schema prompt actually comes from. The `statement_timeout = '3s'` set via Hikari `connection-init-sql` applies to every JDBC connection; no per-query timeout configuration is required.

**`RagQueryHandler`:** `ragAgent.answer(question)` — retriever auto-populates context; `RagResponse.citations` is already structured, no text parsing needed.

**`ConflictQueryHandler`:** `EntityExtractor.extract(question)` → case-insensitive entity lookup → `ConflictSynthesizer.synthesize(prompt)`. Two failure modes handled explicitly:

1. **Name resolution** — three-step lookup chain:
   1. `variantClaimRepository.findByEntityNameIgnoreCase(name)` — exact ILIKE match on `entities.name`
   2. `entityAliasRepository.findByAliasIgnoreCase(name)` → get `entity_id` → look up variant claims — covers cross-cultural aliases (Venus → Aphrodite, Hercules → Heracles)
   3. Trigram similarity fallback — `SELECT * FROM entities WHERE similarity(name, ?) > 0.3 ORDER BY similarity(name, ?) DESC LIMIT 1` — requires `pg_trgm` extension and `idx_entities_name_trgm` GIN index (both added in V1/V3). Handles Greek spelling variants ("Herakles" → "Heracles") that `ILIKE %name%` misses.
2. **No conflict data** — if `variantClaims` is empty after all three steps, return `QueryResponse` with `answer = "The curated sources contain no conflicting accounts for '${name}'."` and an empty `conflicts` list, not a silent empty response. This is a valid answer, not a bug.

**`MixedQueryHandler`:** `TextToSqlAgent.generateSql()` → execute → inject SQL results as context into `ragAgent.answer(augmentedQuestion)`.

### QueryService

Central orchestrator. Two nested try-catches: the outer catches router failures (degrades to RAG); the inner catches handler failures (returns a `serviceError` response rather than propagating an exception). If the LLM API is down, both the router and the RAG fallback will fail — the inner catch prevents an unhandled exception and gives the user a clear message:

```kotlin
fun handle(question: String): QueryResponse {
    val route = try {
        queryRouter.classify(question)
    } catch (e: Exception) {
        log.warn("Router failed for '{}', defaulting to RAG: {}", question, e.message)
        RouteDecision.RAG
    }
    return try {
        when (route) {
            RouteDecision.SQL      -> sqlQueryHandler.handle(question)
            RouteDecision.RAG      -> ragQueryHandler.handle(question)
            RouteDecision.MIXED    -> mixedQueryHandler.handle(question)
            RouteDecision.CONFLICT -> conflictQueryHandler.handle(question)
        }
    } catch (e: Exception) {
        log.error("Handler failed for route {} on '{}': {}", route, question, e.message)
        QueryResponse(
            answer = "The service is temporarily unavailable. Please try again later.",
            routeDecision = route,
            citations = emptyList(),
            conflicts = emptyList(),
            sqlGenerated = null,
            serviceError = true
        )
    }
}
```

RAG is the correct router default — it produces a cited answer rather than a SQL error. `serviceError = true` signals the Thymeleaf template to render an error banner instead of the normal answer block.

### REST API

| Method | Path | Returns |
|---|---|---|
| `POST` | `/api/v1/query` | `QueryResponse` |
| `GET` | `/api/v1/entities` | entity list |
| `GET` | `/api/v1/sources` | source list |
| `GET` | `/api/v1/conflicts/{entityName}` | variant claims for an entity |

**`QueryResponse` shape:**
```json
{
  "answer": "string",
  "routeDecision": "CONFLICT",
  "citations": [{"author":"Hesiod","work":"Theogony","passageRef":"188-200","stance":"cosmological"}],
  "conflicts": [{"claimValue":"Born from sea foam...","sourceAuthor":"Hesiod","sourceWork":"Theogony"}],
  "sqlGenerated": null,
  "serviceError": false
}
```
`serviceError: Boolean = false` is a Kotlin data class default. Thymeleaf template renders an error banner when `serviceError == true` instead of the normal answer/citations block.

Swagger UI auto-generated at `/swagger-ui.html` via `springdoc-openapi`.

### Thymeleaf Web UI

`WebController` serves `GET /` (empty form) and `POST /web/query` (calls `QueryService`, passes response to template).

`templates/index.html`:
- Text input + submit button
- Route badge: color-coded by `routeDecision` (SQL=blue, RAG=green, MIXED=purple, CONFLICT=orange)
- Answer text block with citations as numbered footnotes
- Conflicts section: one block per version, formatted as `Author, Work: claim`
- Collapsible SQL block when `sqlGenerated != null`
- Minimal Tailwind CSS via CDN (no build step)

### `application.yml`

```yaml
spring:
  datasource:
    url: jdbc:postgresql://${POSTGRES_HOST:localhost}:${POSTGRES_PORT:5432}/${POSTGRES_DB:blamezeus}
    username: ${POSTGRES_APP_USER:zeus_app}
    password: ${POSTGRES_APP_PASSWORD:app_password}
    hikari:
      connection-init-sql: "SET statement_timeout = '3s'"
  flyway:
    url: ${spring.datasource.url}
    user: ${POSTGRES_USER:zeus}
    password: ${POSTGRES_PASSWORD:olympus}
  jpa:
    hibernate:
      ddl-auto: validate

app:
  llm:
    chat-api-key: ${LLM_API_KEY}                # API key for the chat model provider; set to OPENAI_API_KEY when using OpenAI (Phase 1 default)
    embedding-api-key: ${OPENAI_API_KEY}         # always OpenAI — must match text-embedding-3-small used during ingestion
    chat-model: ${LLM_CHAT_MODEL}               # required — no default; provider-agnostic. Update LangChain4jConfig.kt beans when swapping the chat provider
```

`POSTGRES_APP_USER`/`POSTGRES_APP_PASSWORD` are the runtime credentials for the read-only `zeus_app` user. `POSTGRES_USER`/`POSTGRES_PASSWORD` are the superuser credentials used only by Flyway for schema migrations. The `statement_timeout` applies globally to all Hikari-managed connections, capping every LLM-generated SQL query at 3 seconds and preventing runaway recursive CTEs from exhausting the connection pool. Add both credential pairs to `.env.example`.

The `zeus_app` user is created by `docker-entrypoint-initdb.d/01_readonly_user.sql` (run automatically by the Postgres container on first startup):
```sql
CREATE USER zeus_app WITH PASSWORD 'app_password';
GRANT CONNECT ON DATABASE blamezeus TO zeus_app;
GRANT USAGE ON SCHEMA public TO zeus_app;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO zeus_app;
ALTER DEFAULT PRIVILEGES IN SCHEMA public GRANT SELECT ON TABLES TO zeus_app;
```

---

## 6. Consumer Layer — Telegram Bot (Phase 2)

Module `telegram-bot/` is a thin Spring Boot service. It knows nothing about mythology.

Key files:
- `BlamezeusBot extends TelegramLongPollingBot` — receives updates, calls `CoreApiClient`, sends formatted reply
- `CoreApiClient` — `RestClient` calling `POST /api/v1/query` on core-api
- `TelegramResponseFormatter` — converts `QueryResponse` to Telegram MarkdownV2 (escape `.`, `!`, `(`, `)`, `-`, `[`, `]`); splits messages >4096 chars at citation boundaries

`docker-compose.full.yml` adds `telegram-bot` with `depends_on: core-api: condition: service_healthy`. Requires `TELEGRAM_BOT_TOKEN` and `TELEGRAM_BOT_USERNAME` env vars.

---

## 7. Evaluation

> ⚠️ Amended by ADR-007 — see `docs/adr/adr-007-conflict-detection-and-surfacing.md` and `DEVIATIONS.md` DEV-014.
> Conflict questions (Q13–15) no longer expect a `CONFLICT` route: their `expected_route` re-points
> (parentage → SQL, death → RAG), and they are scored on `conflicts[]` having ≥2 distinct versions surfaced by
> enrichment, **not** on a route match. The `CONFLICT` value survives only as a gold-question *category* label,
> not as a `RouteDecision`. (Broader eval expansion is ADR-010, still Proposed — not applied here.)

### Gold Question JSON Schema

Each entry in `evaluation/gold-questions.json` has these fields:

```json
{
  "id": 1,
  "category": "FACT|DATA|MIXED|CONFLICT|REFUSAL",
  "question": "...",
  "expected_route": "RAG|SQL|MIXED|CONFLICT",
  "required_authors": ["Hesiod"],
  "required_keywords": ["spider", "weaving", "Arachne"],
  "forbidden_patterns": ["I don't know", "not in my corpus", "I cannot"]
}
```

`required_keywords` — all must appear (case-insensitive) in the answer text. These are defined per question and are the authoritative check, not a post-hoc keyword guess. `forbidden_patterns` — any match in the answer is an automatic fail (catches hallucinations and broken refusals). `required_authors` — at least one must appear in `citations[]`.

**REFUSAL questions** use a different schema: no `required_keywords`, no `required_authors`; instead a `refusal_criteria` block:

```json
{
  "id": 16,
  "category": "REFUSAL",
  "question": "What did Achilles look like physically?",
  "expected_route": "RAG",
  "refusal_criteria": {
    "must_not_assert_answer": true,
    "must_mention_source_limit": true,
    "must_not_fabricate_citation": true
  },
  "forbidden_patterns": ["his hair was", "he had", "described as"]
}
```

Pass criteria for REFUSAL:
- `must_not_assert_answer`: response does NOT make a positive claim about the fact asked (no fabricated description)
- `must_mention_source_limit`: response contains a phrase acknowledging the texts are silent (e.g. "the texts do not describe", "Homer does not give", "no surviving account")
- `must_not_fabricate_citation`: `citations[]` does not include a source that doesn't actually address the question — checked by asserting `citations` is empty or matches only known-relevant passages
- `forbidden_patterns`: catch common hallucination signatures for each specific question

### Gold Question Set

| # | Category | Question | Expected Route | `required_keywords` | `required_authors` |
|---|---|---|---|---|---|
| 1 | FACT | "Why did Athena turn Arachne into a spider?" | RAG | spider, weaving, Arachne | Ovid |
| 2 | FACT | "What was Prometheus punished for?" | RAG | fire, eagle, liver | Hesiod |
| 3 | FACT | "How did Odysseus escape Polyphemus?" | RAG | nobody, stake, eye | Homer |
| 4 | FACT | "What happened at the wedding of Peleus and Thetis?" | RAG | apple, Eris, discord | — |
| 5 | FACT | "Why did Demeter stop the crops from growing?" | RAG | Persephone, Hades, abduction | — |
| 6 | DATA | "Which Olympians are children of Cronus?" | SQL | Zeus, Hera, Poseidon, Demeter, Hestia, Hades | — |
| 7 | DATA | "Which heroes are children of Zeus?" | SQL | Heracles, Perseus | — |
| 8 | DATA | "List all monsters Perseus encountered." | SQL | Medusa, Gorgon, Cetus | — |
| 9 | DATA | "Trace Zeus's lineage back to Chaos." | SQL | Cronus, Ouranos, Chaos | — |
| 10 | DATA | "Which entities have 'olympian' type?" | SQL | *(count check: ≥12 rows)* | — |
| 11 | MIXED | "Which heroes had a divine parent and died at Troy?" | MIXED | Troy, divine | — |
| 12 | MIXED | "What is the divine lineage connecting Achilles to Zeus?" | MIXED | Peleus, Thetis, Zeus | — |
| 13 | CONFLICT | "Who were Aphrodite's parents?" | CONFLICT | Ouranos, Zeus, Dione | Hesiod, Homer |
| 14 | CONFLICT | "Who was Io's father?" | CONFLICT | Inachus, Piren | Apollodorus |
| 15 | CONFLICT | "How did Achilles die?" | CONFLICT | Paris, arrow, heel | — |
| 16 | REFUSAL | "What did Achilles look like physically?" | RAG | *(refusal_criteria)* | — |
| 17 | REFUSAL | "What were Zeus's exact words at the Trojan council?" | RAG | *(refusal_criteria)* | — |

**Notes on specific questions:**
- Q9 (lineage): `required_keywords` checks that all steps appear in the answer. `EvaluationRunner` also asserts `sqlGenerated != null` then checks it contains `WITH RECURSIVE` — the null guard must come first, since `sqlGenerated` is `null` for non-SQL routes and a missing null check will throw in the runner itself.
- Q10 (olympian count): no keyword list. Assert `sqlGenerated != null`, then execute the generated SQL against the test DB and assert `rowCount >= 12`. Do not keyword-search the prose — the LLM may format the list as a table or truncate it.
- Q13–15 (conflict): assert `conflicts[]` has ≥2 entries with distinct `claimValue`s. For Q13 and Q15, also assert each entry in `required_authors` appears in at least one conflict entry. Q14 (Io) has both variants attributed to Apollodorus — `required_authors` has only one entry, so the per-author assertion is skipped. The runner must guard: only apply the per-author check when `required_authors.size >= 2`; otherwise the ≥2 distinct claims check is sufficient.

### Evaluation Runner

`EvaluationRunner` (`fun main()` or JUnit integration test):
1. Load `gold-questions.json`
2. `POST /api/v1/query` for each question
3. Score per question (3 pts max):
   - **Route match** (1pt): `routeDecision` equals `expected_route`
   - **Author/conflict check** (1pt): for FACT/MIXED — at least one `required_authors` entry appears in `citations[]`; for CONFLICT — `conflicts[]` has ≥2 entries with distinct `claimValue`s; additionally, if `required_authors` has ≥2 entries, each listed author must appear in at least one conflict entry; for REFUSAL/DATA — automatic 1pt if route matches
   - **Content check** (1pt): for FACT/DATA/MIXED — all `required_keywords` match in `answer` using `re.search(r'\b' + re.escape(kw) + r'\b', answer, re.IGNORECASE)` (word-boundary regex; define keyword stems, e.g. `"gorgon"` matches "Gorgon"/"Gorgons"), none of `forbidden_patterns` match; for CONFLICT — all `required_keywords` present across `conflicts[].claimValue`; for REFUSAL — all three `refusal_criteria` pass and no `forbidden_patterns` match
4. Print scored table + total accuracy %

Target: ≥75% overall (≥13/17 questions at full score).

---

## 8. Testing Strategy

> ⚠️ Amended by ADR-007 — see `DEVIATIONS.md` DEV-014. `ConflictQueryHandlerTest` is replaced by
> `ConflictLookupTest` + a `QueryService` enrichment test (conflict-shaped question on a SQL/RAG route still
> populates `conflicts[]`; claim-type mismatch yields empty `conflicts[]`; enrichment failure leaves the
> primary answer intact). Add a `QueryRouterTest` asserting the router never emits `CONFLICT`.

### Approach

TDD throughout: write a failing test before implementing each unit. Cycle is Red → Green → Refactor. No handler, validator, or service is complete until its tests pass. The gold-question evaluation in §7 measures answer quality; these tests catch regressions.

### Test Directory Structure

```
core-api/src/test/kotlin/com/blamezeus/coreapi/
├── safety/
│   └── SqlSafetyValidatorTest.kt
├── handler/
│   ├── SqlQueryHandlerTest.kt
│   ├── RagQueryHandlerTest.kt
│   ├── ConflictQueryHandlerTest.kt
│   └── MixedQueryHandlerTest.kt
├── service/
│   └── QueryServiceTest.kt
└── integration/
    ├── FlywayMigrationTest.kt
    ├── SchemaIntrospectorTest.kt
    └── QueryControllerIntegrationTest.kt

ingestion/tests/
├── test_text_cleaner.py
├── test_text_chunker.py
└── test_passage_ref_extractors.py
```

### Test Spring Profile

`core-api/src/test/resources/application-test.yml`:
```yaml
spring:
  jpa:
    hibernate:
      ddl-auto: validate
  flyway:
    enabled: true
```

Integration tests use `@ActiveProfiles("test")` + `@Testcontainers`. Testcontainers provides PostgreSQL 16 with the `pgvector` extension; no manual DB setup required.

### Mocking `@AiService` Interfaces

`@AiService` interfaces have no concrete class. Use `mockk<T>()` in pure unit tests and `@MockkBean` (springmockk) in Spring-context tests:

```kotlin
// Pure unit test
val textToSqlAgent = mockk<TextToSqlAgent>()
every { textToSqlAgent.generateSql(any(), any()) } returns "SELECT * FROM entities"

// Spring slice / integration test
@MockkBean lateinit var textToSqlAgent: TextToSqlAgent
```

### TDD Cycle Per Implementation Phase

Write the listed failing test(s) **before** writing any production code for that phase.

| Phase | Write these tests first | What they verify |
|---|---|---|
| **1 — Foundation** | `FlywayMigrationTest`, `SchemaIntrospectorTest` | Each expected table exists after Flyway runs; critical tables have required columns; `SchemaIntrospector` prompt contains all application tables and key columns |
| **2 — Seed Data** | `SourceRepositoryTest`, `EntityRepositoryTest`, `VariantClaimRepositoryTest` | `findAll()` returns correct counts (6 sources, ≥60 entities); `findByEntityName("Aphrodite")` returns ≥2 conflict rows |
| **5 — SQL Pipeline** | `SqlSafetyValidatorTest`, `SqlQueryHandlerTest` | `SELECT`/`WITH` allowed; `DROP`, `DELETE`, `INSERT`, `UPDATE`, `;` blocked; handler calls validator before `JdbcTemplate` |
| **6 — RAG Pipeline** | `RagQueryHandlerTest` | Mocked `RagAgent` response is returned; citation parsing does not throw |
| **7 — Conflict Pipeline** | `ConflictQueryHandlerTest` | All fetched `variant_claims` rows are passed to `ConflictSynthesizer`; `QueryResponse.conflicts` is non-empty; unknown entity name returns graceful `answer` string not an exception |
| **8 — Mixed Pipeline** | `MixedQueryHandlerTest` | SQL result rows are injected into the augmented question string before the RAG call |
| **5–8 routing** | `QueryServiceTest` | Each `RouteDecision` value dispatches to exactly one handler and not the others; when both router and handler throw, `QueryResponse.serviceError == true` and `answer` is non-empty |
| **9 — Web Layer** | `QueryControllerIntegrationTest` | HTTP 200; response body contains `routeDecision`; CONFLICT query populates `conflicts` |

### `FlywayMigrationTest` — Column Verification

A table existing with the wrong schema passes a table-presence check but will silently break queries. Verify columns for the tables most likely to diverge from the migration:

```kotlin
private fun columns(table: String): List<String> =
    jdbcTemplate.queryForList(
        "SELECT column_name FROM information_schema.columns WHERE table_name = ?", table)
    .map { it["column_name"] as String }

@Test fun `variant_claims has required columns`() {
    assertThat(columns("variant_claims"))
        .contains("subject_entity_id", "claim_type", "claim_value", "source_id", "trust_tier")
}

@Test fun `narrative_chunks has content_hash and embedding`() {
    assertThat(columns("narrative_chunks"))
        .contains("content", "content_hash", "embedding", "source_id", "passage_ref")
}

@Test fun `sources has year_published and role`() {
    assertThat(columns("sources"))
        .contains("author", "work", "translation", "stance", "year_published", "role")
}
```

These tests catch the most common migration drift: adding a column to Flyway but forgetting to update `SchemaIntrospector`'s table list, or vice versa.

### `SchemaIntrospectorTest` — Prompt Correctness

`SchemaIntrospector` is in the critical path of every SQL query. A wrong prompt silently generates wrong SQL. Test it in the integration profile (Testcontainers + Flyway):

```kotlin
@Test fun `prompt contains all application tables`() {
    val prompt = schemaIntrospector.get()
    listOf("entities", "relationships", "sources", "variant_claims", "narrative_chunks")
        .forEach { table -> assertThat(prompt).contains(table) }
}

@Test fun `prompt contains known columns from critical tables`() {
    val prompt = schemaIntrospector.get()
    assertThat(prompt).contains("subject_entity_id")  // variant_claims
    assertThat(prompt).contains("trust_tier")          // variant_claims
    assertThat(prompt).contains("year_published")      // sources
    assertThat(prompt).contains("content_hash")        // narrative_chunks
}
```

If a migration adds or renames a column and `SchemaIntrospector` fails to pick it up, these tests catch it before you spend time debugging why the LLM generates wrong SQL.

### `SqlSafetyValidatorTest` — Key Cases

```kotlin
@Test fun `SELECT is allowed`() { validator.validate("SELECT id FROM entities") }
@Test fun `DROP is rejected`() { assertThrows<IllegalArgumentException> { validator.validate("DROP TABLE entities") } }
@Test fun `semicolon is rejected`() { assertThrows<IllegalArgumentException> { validator.validate("SELECT 1; DROP TABLE entities") } }
@Test fun `WITH CTE is allowed`() { validator.validate("WITH RECURSIVE t AS (SELECT ...) SELECT * FROM t") }
```

### Python Tests

`test_text_cleaner.py` — assert footnote markers (`[1]`, `[42]`) are stripped; smart quotes normalized; multi-whitespace collapsed.

`test_text_chunker.py` — assert no chunk exceeds `CHUNK_SIZE * 1.2` characters (bounding variable sentence-length growth); assert the last `OVERLAP_SENTENCES` sentences of chunk N appear verbatim at the start of chunk N+1; assert `passage_ref` on each chunk matches the nearest preceding marker in the input; assert running `chunk()` twice on the same text produces identical `(chunk_text, passage_ref)` tuples (determinism guarantees `ON CONFLICT DO NOTHING` catches re-runs with no duplicate DB keys).

`test_passage_ref_extractors.py` — one test per source extractor using inline fixtures with known markers. Each extractor must be tested against both clean and OCR-noise variants:
- `apollodorus_refs`: clean fixture `"[1.1.1]"` and `"[1.2.3]"` (Theoi bracketed format) → assert offsets and captured group match (bracket-free, e.g. `"1.1.1"`); unbracketed variant `"1.1.1"` → assert same ref still extracted (regex tolerates optional brackets); noise fixture `"[1. 1. 1]"` (extra spaces) → assert same ref is still extracted; must not match a bare footnote marker like `"[3]"` (single integer, no dots) — assert no entry emitted for that input
- `homer_refs`: clean fixture `"BOOK I"` then `[ll. 1-7]` → assert `"Book I ll. 1-7"`; noise variants `[l.1]` (no space) and `[ll.1 - 7]` (space before dash) → assert both parse; no-preceding-book fixture → assert no entry emitted (chunker uses fallback, not extractor)
- `ovid_refs`: `"BOOK I"` then ALL-CAPS story title → assert `"Book I: The Creation"`; consecutive markers with no text between → assert no empty-string chunks are produced by the chunker
- All extractors: fixture with text before the first marker → assert extractor returns `None` for that offset (chunker applies `f"{author}, {work}"` fallback — test the fallback in `test_text_chunker.py`, not here)

Run: `pytest ingestion/tests/`

---

## 9. Implementation Sequence

Build in phases to validate each layer before building on it. For each phase, write the tests listed in §8 **before** writing production code.

> ⚠️ Deviations occurred in Stage 1. See DEVIATIONS.md for details (DEV-001 through DEV-009).
>
> ⚠️ Amended by ADR-007 (DEV-014): "Phase 7 — Conflict Pipeline" becomes "Conflict Enrichment" — no
> `CONFLICT` route and no `ConflictQueryHandler`; build `ConflictProbe` + shared `ConflictLookup` + the
> `QueryService` enrichment step instead. The phase 7 verification row below still holds (Aphrodite question
> returns ≥2 attributed versions), but via enrichment on a SQL/RAG route, not a `CONFLICT` route.
>
> ⚠️ Deviations occurred in Stage 2. See DEVIATIONS.md for details (DEV-010 through DEV-013).
>
> ⚠️ **Stage order changed by ADR-004** (`docs/adr/adr-004-seed-data-extraction-strategy.md`): seed data
> generation now depends on ingested corpus text (the extraction pipeline reads it), so ingestion runs
> *before* seed data. Stage numbers below reflect execution order — Phase 2 is now Ingestion Setup, Phase 3
> is Full Corpus, Phase 4 is Seed Data (extraction-assisted). Phase 5 onward is unchanged.

| Phase | Steps | Done when |
|---|---|---|
| **1 — Foundation** | Gradle scaffold for JVM modules, Docker Compose, Flyway V1–V8 | `docker-compose up`, Flyway migrates, empty tables exist |
| **2 — Ingestion setup** | Python venv, `requirements.txt`, `config.py`, download corpus .txt files, file loader + cleaner for Apollodorus | `python main.py` runs without error, rows appear in `narrative_chunks` |
| **3 — Full Corpus** | Add Homer, Hesiod, Hymns, Ovid file paths to `source_registry.py` | All sources indexed |
| **4 — Seed Data** | Extraction pipeline (`ingestion/extraction/`) run against ingested corpus; entities/relationships spot-checked into V10/V11; `variant_claims` candidates reviewed and promoted into V12; V9/V13/V14 hand-curated as before; JPA entities + repos | `GET /api/v1/entities` returns ~60 entities |
| **5 — SQL Pipeline** | `QueryRouter` + `TextToSqlAgent` + `SqlSafetyValidator` + `SqlQueryHandler` | DATA gold questions answer correctly |
| **6 — RAG Pipeline** | `RagAgent` + `RagQueryHandler` | FACT gold questions cite sources |
| **7 — Conflict Pipeline** | `ConflictQueryHandler` + `ConflictSynthesizer` | Aphrodite question returns ≥2 attributed versions |
| **8 — Mixed Pipeline** | `MixedQueryHandler` | Multi-hop questions return SQL + narrative |
| **9 — Web UI** | Thymeleaf `index.html` + `WebController` | Manual smoke test all 17 gold questions in browser |
| **10 — Evaluation** | `EvaluationRunner`, run full gold set | ≥75% score |
| **11 — Telegram (opt.)** | `telegram-bot` module | Bot answers in chat |

---

## 10. Verification Steps

1. `docker-compose up` — Flyway migrates, `GET localhost:5432` health check passes
2. `GET localhost:8080/swagger-ui.html` — Swagger UI loads
3. `GET localhost:8080/api/v1/entities` — returns ≥50 entities
4. `POST /api/v1/query {"question":"Which Olympians are children of Cronus?"}` — `routeDecision: SQL`, answer contains Zeus/Hera/Poseidon, `sqlGenerated` populated
5. `POST /api/v1/query {"question":"Why did Athena turn Arachne into a spider?"}` — `routeDecision: RAG`, citations include Ovid
6. `POST /api/v1/query {"question":"Who were Aphrodite's parents?"}` — `routeDecision: CONFLICT`, `conflicts` has ≥2 entries from different authors
7. Open `http://localhost:8080/` — web UI renders, form submits, route badge + citations visible
8. `EvaluationRunner` prints ≥75% overall score

---

## 11. Critical Files

| File | Why it matters |
|---|---|
| `core-api/.../db/migration/V12__seed_variant_claims.sql` | Conflict detection quality lives here; richness of this data determines demo impact |
| `core-api/.../config/LangChain4jConfig.kt` | All AI bean wiring; misconfiguration cascades to every handler |
| `core-api/.../service/QueryService.kt` | Central orchestrator connecting routing to handlers |
| `ingestion/pipeline/embedding_pipeline.py` | Dimension mismatch here silently breaks all RAG queries |
| `core-api/.../config/SchemaIntrospector.kt` | Schema prompt is derived from live DB — if this class is wrong, every SQL query misfires |
| `core-api/.../ai/TextToSqlAgent.kt` | `{{schema}}` placeholder must be present in system message; `SchemaIntrospector.get()` keeps it in sync with Flyway automatically |
