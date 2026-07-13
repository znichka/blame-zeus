# ADR-013: Embedding Model Upgrade — text-embedding-3-large (native 3072 dims)

| Field        | Value       |
|--------------|-------------|
| **Date**     | 2026-07-13  |
| **Status**   | Accepted (applied 2026-07-13 — see Implementation Checklist) |

**Traceability:** IMPLEMENTATION_PLAN.md §3 (Data Model / `narrative_chunks`), §4 (Ingestion Job / `embedding_pipeline.py`), §5 (`LangChain4jConfig.kt`, Stage 6 retriever) · **Supersedes the embedding-model portion of ADR-003 and ADR-008 §3** (chat-model decisions untouched) · Implements the deferred `V15__add_embedding_model_tracking` from ADR-006 §2 (renumbered `V8_4`, see DEV-028) · Related to ADR-002 (pgvector), DEV-025 (custom `ContentRetriever`)

---

## Context

ADR-003 chose `text-embedding-3-small` (1536 dims) and ADR-008 §3 reaffirmed it, while explicitly naming the escalation path: *"`text-embedding-3-large` is the low-friction quality upgrade (same vendor, 3072-dim, `vector(3072)` schema change)"*, to be taken **before** the corpus grows — a model swap always requires re-embedding the entire corpus, so the cost of switching only rises over time.

At the end of Stage 2 the corpus is at its smallest it will ever be: exactly 260 chunks (~100k tokens, one source), one migration away from schema freedom, and no Kotlin consumer of the embedding model exists yet (`LangChain4jConfig.kt` is a Stage 6 deliverable). The decision was made to escalate now.

One hard constraint shapes the design: **pgvector's HNSW index over the plain `vector` type supports at most 2000 dimensions.** `text-embedding-3-large` natively emits 3072. The `V8` migration's `USING hnsw (embedding vector_cosine_ops)` index cannot be rebuilt as-is over `vector(3072)`. The local DB runs pgvector **0.8.4**, which supports `halfvec` (half-precision) indexing up to 4000 dims (available since pgvector 0.7).

## Decision

### 1. Switch `EMBEDDING_MODEL` to `text-embedding-3-large`, native 3072 dimensions

No `dimensions=` truncation parameter. `embedding_pipeline.py` passes no `dimensions=` argument, so the env-var flip alone produces native 3072-dim vectors. The ADR-006 single-source-of-truth wiring (`EMBEDDING_MODEL` env var → `ingestion/config.py` + `application.yml`) means the model name changes in exactly one place per environment; only the *defaults* embedded in `application.yml`, `application-test.yml`, and `docker-compose.full.yml` needed updating alongside `.env`/`.env.example`.

### 2. Migration `V8_4__switch_embedding_to_3large_3072.sql`

```sql
TRUNCATE narrative_chunks;                                  -- old vectors are not comparable; re-embed
DROP INDEX narrative_chunks_embedding_idx;
ALTER TABLE narrative_chunks ALTER COLUMN embedding TYPE vector(3072);
CREATE INDEX narrative_chunks_embedding_hnsw_idx ON narrative_chunks
    USING hnsw ((embedding::halfvec(3072)) halfvec_cosine_ops)
    WITH (m = 16, ef_construction = 64);
ALTER TABLE narrative_chunks ADD COLUMN embedding_model TEXT NOT NULL;  -- ADR-006 §2, ex-V15
```

- **`TRUNCATE` is intentional and load-bearing:** vectors from different models occupy different spaces, and `store_chunks()`'s skip-before-embed dedup keys on `content_hash`, which a model swap does not change — without the truncate, a re-run would skip every chunk and re-embed nothing (DEV-024).
- **halfvec expression index:** the column stays full-precision `vector(3072)` (lossless storage); only the *index* is half-precision. This is the standard pgvector pattern for >2000-dim vectors.
- **ADR-006's deferred `V15` lands here** as the `embedding_model` column, renumbered into the `V8_x` amendment series because the planned `V9`–`V14` (Stage 3/4 seeds) are still unwritten and a `V15` applied now would break Flyway's default in-order validation later — the exact hazard `TODO.md`'s Stage 3 item flagged and pre-authorized resolving by renumbering (logged as DEV-028). ADR-006's spec had `DEFAULT 'text-embedding-3-small'` to cover then-existing rows; post-`TRUNCATE` the table is empty, so the column is `NOT NULL` with **no default** — strictly better, every writer must stamp the model explicitly.

### 3. Retrieval queries MUST cast to `halfvec` to use the index

An expression index only matches queries using the same expression. Stage 6's custom `ContentRetriever` (DEV-025) must order by:

```sql
ORDER BY embedding::halfvec(3072) <=> ($1::vector(3072))::halfvec(3072)
```

A plain `ORDER BY embedding <=> $1` still returns correct results but **silently sequential-scans** — exactly the failure mode ADR-006 §5's `EXPLAIN ANALYZE` verification step exists to catch; that check now applies to the cast form.

## Consequences

### Positive
- Meaningfully better retrieval quality (MTEB ~64.6 vs ~62.3) at the moment re-embedding is cheapest it will ever be (~$0.01 for the current corpus).
- The `embedding_model` column + re-embed together mean drift tracking is populated correctly from row one — no backfill migration ever needed.
- Storage stays lossless (`vector(3072)`); only the ANN index is half-precision, whose recall impact is negligible at PoC corpus scale.

### Negative / Trade-offs
- Embedding cost rises $0.02 → $0.13 per 1M tokens (irrelevant at PoC scale) and per-row vector storage doubles (12 KB vs 6 KB; ~3 MB total today).
- Stage 6's retrieval SQL carries a non-obvious cast requirement (§3 above) — encoded in the migration comment, `TODO.md` Stage 6, and DEV-028 so it cannot be missed.
- The future `canary-aphrodite.json` golden-vector fixture (ADR-006 §4, Stage 6) must be generated with `-large`.
- Half-precision index adds a subtle recall/precision trade-off vs a plain-vector HNSW; acceptable and standard practice for 3072-dim vectors.

## Alternatives Considered

**A. Truncate to 1536 via the OpenAI `dimensions` parameter (Matryoshka).**
Rejected. Keeps the `V8` schema and plain HNSW index untouched and captures most of `-large`'s quality gain, but permanently institutionalizes the exact trap ADR-006 warns about: *"a dimension match is not a model match."* Every future reader of `vector(1536)` would have to know the vectors are truncated `-large`, not `-small` — an invisible config invariant.

**B. Native 3072 with no ANN index (exact scan).**
Rejected. At 260 rows a sequential scan is effectively free, but it deviates from the plan/guardrails ("HNSW index on embedding") with no offsetting benefit, and silently defers the >2000-dim problem to whenever the corpus grows.

**C. Stay on `text-embedding-3-small`.**
Rejected by the user's product decision; ADR-008 §3 already framed `-large` as the designated upgrade and "before more sources are ingested" as the right timing.

## Implementation Checklist

- [x] `V8_4__switch_embedding_to_3large_3072.sql` (truncate + `vector(3072)` + halfvec HNSW + `embedding_model` column)
- [x] `embedding_pipeline.py`: `store_chunks()` INSERT stamps `embedding_model = config.EMBEDDING_MODEL` (closes ADR-006 checklist item)
- [x] `EMBEDDING_MODEL=text-embedding-3-large` in `.env`, `.env.example`; defaults updated in `application.yml`, `application-test.yml`, `docker-compose.full.yml`; test env in `test_embedding_pipeline.py`
- [x] Corpus re-embedded (Apollodorus, 260 chunks, all `embedding_model='text-embedding-3-large'`, `vector_dims=3072`); halfvec index scan confirmed via `EXPLAIN` (with `enable_seqscan=off` — at 260 rows the planner legitimately prefers a seq scan on cost); idempotent re-run confirmed (`Skipping 260 of 260`)
- [ ] **(Deferred — Stage 6)** custom `ContentRetriever` uses the `halfvec(3072)` cast in ORDER BY; `EXPLAIN` confirms `narrative_chunks_embedding_hnsw_idx` usage
- [ ] **(Deferred — Stage 6)** `canary-aphrodite.json` golden fixture generated with `-large`
