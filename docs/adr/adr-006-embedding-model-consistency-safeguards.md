# ADR-006: Embedding Model Consistency & Drift Prevention Safeguards

| Field        | Value       |
|--------------|-------------|
| **Date**     | 2026-07-08  |
| **Status**   | Accepted (partially applied 2026-07-10 — see Implementation Checklist) |


**Traceability:** IMPLEMENTATION_PLAN.md §4 (Ingestion Job / `embedding_pipeline.py`), §5 (`LangChain4jConfig.kt`, `SchemaIntrospector`), §7 (Evaluation), §8 (Testing Strategy) · Supersedes nothing · Related to ADR-004 (seed data extraction strategy, applying the same "trust but verify" philosophy here to embeddings instead of claims)

---

## Context

The embedding model used at ingestion time (`ingestion/pipeline/embedding_pipeline.py`) and the embedding model used at query time (`core-api/.../config/LangChain4jConfig.kt`) must produce **vectors from the same model in the same configuration**. Otherwise similarity search silently degrades. Unlike a schema mismatch, this failure mode throws no exception: the system keeps returning results, just meaningless ones (see the "curse of dimensionality" and "silent failure" discussion that prompted this review).

A review of the current implementation plan found that **the two sides are consistent today**, but only by convention, not by design:

| Issue | Where it lives currently | Risk |
|---|---|---|
| Model name is a hardcoded string literal in **two separate codebases** (Python + Kotlin), with no shared config | `embedding_pipeline.py`: `model="text-embedding-3-small"` / `LangChain4jConfig.kt`: `.modelName("text-embedding-3-small")` | A future change to one without the other causes silent drift |
| No embedding model version is recorded per chunk | `store_chunks()`'s `metadata` JSONB payload has no `embedding_model` field | Impossible to retroactively audit which rows came from which model, or safely migrate incrementally later |
| `vector(1536)` column constraint is the *only* safety net | `V8__create_narrative_chunks.sql` | Passes for any model that happens to emit 1536 dimensions (e.g., `text-embedding-3-large` truncated via the `dimensions` param) even though the vector space is entirely different: a dimension match is not a model match |
| No test verifies the Python `openai` SDK path and the Kotlin LangChain4j `OpenAiEmbeddingModel` path produce equivalent vectors for the same input | §8 Testing Strategy has no such test | An unverified assumption underpins the entire RAG pipeline's correctness |
| No explicit confirmation that the LangChain4j `PgVectorEmbeddingStore`'s query distance metric matches the `vector_cosine_ops` HNSW index built in `V8` | `LangChain4jConfig.kt` `contentRetriever()` bean | Possible silent fallback to sequential scan, and/or `minScore=0.65` computed under the wrong metric |

The chat model is treated as explicitly swappable and config-driven (`LLM_CHAT_MODEL` env var). The embedding model is treated as "intentionally fixed," but "fixed by convention" and "fixed by design" are not the same thing, and the plan currently only documents the intent via code comments, not enforcement.

---

## Decision

We will treat embedding-model consistency as a first-class operational invariant enforced by config, data, and tests, not by comments alone.

### 1. Single source of truth for the model name

Add `EMBEDDING_MODEL` as a shared environment variable, consumed by both sides:

**`.env.example`:**
```bash
EMBEDDING_MODEL=text-embedding-3-small
```

**`ingestion/config.py`:**
```python
EMBEDDING_MODEL = os.environ["EMBEDDING_MODEL"]
```

**`ingestion/pipeline/embedding_pipeline.py`:**
```python
def embed_batch(texts: list[str]) -> list[list[float]]:
    response = client.embeddings.create(model=config.EMBEDDING_MODEL, input=texts)
    return [item.embedding for item in response.data]
```

**`core-api/src/main/resources/application.yml`:**
```yaml
app:
  llm:
    embedding-api-key: ${OPENAI_API_KEY}
    embedding-model: ${EMBEDDING_MODEL:text-embedding-3-small}
```

**`LangChain4jConfig.kt`:**
```kotlin
@Value("\${app.llm.embedding-model}") private lateinit var embeddingModelName: String

@Bean fun embeddingModel(): EmbeddingModel =
    OpenAiEmbeddingModel.builder()
        .apiKey(embeddingApiKey)
        .modelName(embeddingModelName)
        .build()
```

Both `docker-compose.yml` and `docker-compose.full.yml` pass `EMBEDDING_MODEL` through from the same `.env` file to both the ingestion invocation and the `core-api` container, so there is exactly one place to change it.

### 2. Record the model version with every stored vector

Add a dedicated column rather than burying this in the `metadata` JSONB blob: it needs to be cheaply queryable for consistency checks (decision rationale in "Alternatives Considered" below).

**New migration `V15__add_embedding_model_tracking.sql`:**
```sql
ALTER TABLE narrative_chunks
  ADD COLUMN embedding_model TEXT NOT NULL DEFAULT 'text-embedding-3-small';

COMMENT ON COLUMN narrative_chunks.embedding_model IS
  'Embedding model that produced this row''s vector. Compared at core-api startup '
  'against app.llm.embedding-model to detect drift before it silently degrades search quality.';
```

**`store_chunks()` insert statement** gains `embedding_model` as an explicit column (not just JSONB metadata):
```python
cur.execute(
    """INSERT INTO narrative_chunks
       (content, embedding, source_id, passage_ref, metadata, embedding_model)
       VALUES (%s, %s, %s, %s, %s, %s)
       ON CONFLICT (source_id, passage_ref, content_hash) DO NOTHING""",
    (chunk.text, np.array(embedding), chunk.source_id, chunk.passage_ref,
     json.dumps({...}), config.EMBEDDING_MODEL)
)
```

### 3. Fail loudly at startup on mismatch, rather than degrade silently

New component, `EmbeddingConsistencyChecker`, runs once on `ApplicationReadyEvent`:

```kotlin
@Component
class EmbeddingConsistencyChecker(
    private val jdbcTemplate: JdbcTemplate,
    @Value("\${app.llm.embedding-model}") private val configuredModel: String
) {
    private val log = LoggerFactory.getLogger(javaClass)

    @EventListener(ApplicationReadyEvent::class)
    fun checkOnStartup() {
        val distinctModels = jdbcTemplate.queryForList(
            "SELECT DISTINCT embedding_model FROM narrative_chunks", String::class.java
        )
        when {
            distinctModels.isEmpty() -> log.info("No embeddings ingested yet — skipping consistency check.")
            distinctModels.size > 1 -> log.error(
                "EMBEDDING DRIFT DETECTED: narrative_chunks contains vectors from multiple models: {}. " +
                "RAG results are unreliable until the corpus is fully re-embedded with one model.", distinctModels
            )
            distinctModels.single() != configuredModel -> log.error(
                "EMBEDDING MISMATCH: configured model is '{}' but stored vectors were produced by '{}'. " +
                "Query embeddings and stored embeddings are NOT comparable. Re-ingest before serving RAG traffic.",
                configuredModel, distinctModels.single()
            )
            else -> log.info("Embedding model consistency check passed: '{}'", configuredModel)
        }
    }
}
```

This is deliberately **log-and-continue, not fail-fast-and-crash**, for a Phase-1 PoC. The SQL and CONFLICT routes still function correctly even if RAG is degraded. A future phase could escalate this to a hard startup failure or a `/health` indicator.

### 4. Verify cross-library equivalence with a golden-vector fixture test

Add `EmbeddingConsistencyTest` to `core-api/src/test/kotlin/.../integration/`:

```kotlin
@Test
fun `embeddingModel produces vectors equivalent to the ingestion pipeline`() {
    val canaryText = "Aphrodite was born from sea foam."
    val actual = embeddingModel.embed(canaryText).content().vector()
    val golden = loadGoldenVectorFixture("canary-aphrodite.json")  // precomputed once via the Python pipeline

    val cosineSimilarity = cosineSimilarity(actual, golden)
    assertThat(cosineSimilarity).isGreaterThan(0.9999)
}
```

The fixture (`canary-aphrodite.json`) is generated **once**, offline, by running the exact same string through `ingestion/pipeline/embedding_pipeline.py` and committing the resulting vector as a test resource. This is a golden-file test, not a live network call in CI: it costs nothing to run and catches any accidental divergence between the `openai` Python SDK path and the LangChain4j Java path (differing default parameters, encoding format, etc.).

### 5. Confirm the distance metric matches the HNSW index

Add to §10 (Verification Steps) an explicit check:

```sql
EXPLAIN ANALYZE
SELECT id FROM narrative_chunks
ORDER BY embedding <=> '[...]'::vector
LIMIT 5;
```

Confirm the plan shows `Index Scan using narrative_chunks_embedding_idx` (or equivalent), not `Seq Scan`. If LangChain4j's `PgVectorEmbeddingStore` does not expose an explicit cosine-distance configuration matching `vector_cosine_ops`, this is escalated to a follow-up spike rather than left as an unverified assumption.

---

## Consequences

### Positive
- Embedding drift becomes **detectable at startup**, not discovered weeks later via degraded search quality.
- A future embedding model upgrade (e.g., a new OpenAI model) has a clear, auditable migration path: check `embedding_model` distribution, re-embed, verify via the same startup checker.
- The golden-vector test removes a previously untested assumption underpinning the entire RAG pipeline.
- Cost is minimal: one new column, one new env var, one new small component, one new test.

### Negative / Trade-offs
- One additional Flyway migration (`V15`) and one additional startup query on every boot (negligible: `SELECT DISTINCT` over a bounded corpus).
- The golden-vector fixture must be regenerated if the model is *intentionally* changed. That's a manual step, but a cheap and obvious one (failure mode is "test fails until fixture is updated," which is the correct failure direction).
- `EmbeddingConsistencyChecker` only logs errors rather than blocking startup, a deliberate PoC-appropriate choice, but it means a developer must still notice the log line. Acceptable for Phase 1; revisit for production hardening.

---

## Alternatives Considered

**A. Do nothing; rely on the existing code comments.**
Rejected: this is exactly the "silent failure" pattern that makes embedding drift dangerous. A comment cannot fail a build or a startup check.

**B. Store `embedding_model` only in the existing `metadata` JSONB column, not as a dedicated column.**
Rejected: consistency checks need to run `SELECT DISTINCT` cheaply and often (every startup). A dedicated column is directly indexable and matches the project's existing convention of promoting high-stakes fields to real columns (cf. `trust_tier` on `variant_claims`, which is also PoC-critical metadata that was given a first-class column rather than left in JSON).

**C. Enforce consistency via a hard startup failure (throw, refuse to start) rather than log-and-continue.**
Deferred, not rejected outright. Appropriate for a production system, but too strict for a Phase-1 PoC where SQL/CONFLICT routes should remain usable even if RAG embeddings are temporarily inconsistent during iteration. Revisit if/when this moves past PoC.

**D. Adopt a vector database with native embedding-version namespacing (e.g., Pinecone namespaces, Qdrant collections) instead of pgvector.**
Rejected: out of scope. The stack choice (Postgres + pgvector) is already fixed by REQUIREMENTS.md and SCOPE.md; this ADR addresses consistency *within* that existing choice rather than revisiting the vector store decision itself.

---

## Implementation Checklist

> **Partially applied 2026-07-10** (with ADR-008, under the *edit-existing-files-only* scope — see
> `DEVIATIONS.md` DEV-015). The §1 single-source-of-truth `EMBEDDING_MODEL` wiring is done across the
> existing files; all items that require a **new file** (the `V15` migration, `EmbeddingConsistencyChecker`,
> the golden-vector fixture/test) or an **unbuilt component** (`LangChain4jConfig.kt`) remain deferred
> to their build stages. Status of each item marked below.

- [x] ~~**(Deferred — new file)** `V15__add_embedding_model_tracking.sql`~~ — **landed 2026-07-13 as part of `V8_4__switch_embedding_to_3large_3072.sql`** (renumbered into the V8_x series per DEV-028 to avoid the V9–V14 in-order hazard; bundled with the ADR-013 embedding upgrade). Column is `NOT NULL` with no default — the same migration truncates the table, so no legacy rows needed the `'text-embedding-3-small'` default this ADR specified.
- [x] `.env.example`: add `EMBEDDING_MODEL`
- [x] `ingestion/config.py`: read `EMBEDDING_MODEL`
- [x] `embedding_pipeline.py`: use `config.EMBEDDING_MODEL` instead of literal string — **done**;
      *add `embedding_model` to insert statement* — **done 2026-07-13 with V8_4 (DEV-028/ADR-013)**
- [x] `application.yml`: add `app.llm.embedding-model` *(staged; consumer bean deferred with `LangChain4jConfig`)*
- [ ] **(Deferred — `LangChain4jConfig.kt` not yet built)** inject `embedding-model` property instead of hardcoded literal
- [ ] **(Deferred — new file)** `EmbeddingConsistencyChecker.kt` + startup log verification
- [ ] **(Deferred — new file)** `canary-aphrodite.json` golden fixture + `EmbeddingConsistencyTest.kt`
- [ ] **(Deferred — needs ingested data)** §10 Verification Steps: add `EXPLAIN ANALYZE` index-usage check
- [ ] **(Deferred)** IMPLEMENTATION_PLAN.md §3/§4/§5: cross-reference this ADR where the hardcoded model literals currently appear
