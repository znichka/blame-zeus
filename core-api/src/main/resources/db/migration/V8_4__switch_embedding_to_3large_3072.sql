-- ADR-013: switch corpus embeddings to text-embedding-3-large (native 3072 dims).
-- Vectors from different models are not comparable; the corpus must be re-embedded,
-- so existing rows are dropped rather than migrated.
TRUNCATE narrative_chunks;

DROP INDEX narrative_chunks_embedding_idx;

ALTER TABLE narrative_chunks
    ALTER COLUMN embedding TYPE vector(3072);

-- pgvector's plain-vector HNSW index caps at 2000 dims; index via halfvec (pgvector >= 0.7).
-- Retrieval queries must ORDER BY (embedding::halfvec(3072) <=> ...) to hit this index.
CREATE INDEX narrative_chunks_embedding_hnsw_idx ON narrative_chunks
    USING hnsw ((embedding::halfvec(3072)) halfvec_cosine_ops)
    WITH (m = 16, ef_construction = 64);

-- ADR-006 §2 (planned as V15__add_embedding_model_tracking, renumbered per DEV-028):
-- model provenance per row. NOT NULL with no default — the table is empty after the
-- TRUNCATE above, and every writer must stamp the model explicitly.
ALTER TABLE narrative_chunks
    ADD COLUMN embedding_model TEXT NOT NULL;

COMMENT ON COLUMN narrative_chunks.embedding_model IS
    'Embedding model that produced this row''s vector. Compared at core-api startup '
    'against app.llm.embedding-model to detect drift before it silently degrades search quality.';
