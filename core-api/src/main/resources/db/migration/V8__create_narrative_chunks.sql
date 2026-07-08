CREATE TABLE narrative_chunks (
    id           SERIAL PRIMARY KEY,
    content      TEXT NOT NULL,
    content_hash TEXT GENERATED ALWAYS AS (md5(content)) STORED,
    embedding    vector(1536) NOT NULL,
    source_id    TEXT NOT NULL REFERENCES sources(id),
    passage_ref  TEXT,
    metadata     JSONB,
    CONSTRAINT uq_narrative_chunks UNIQUE (source_id, passage_ref, content_hash)
);

CREATE INDEX ON narrative_chunks USING hnsw (embedding vector_cosine_ops) WITH (m = 16, ef_construction = 64);
