CREATE TABLE relationships (
    id        SERIAL PRIMARY KEY,
    from_id   INTEGER NOT NULL REFERENCES entities(id),
    relation  TEXT NOT NULL,
    to_id     INTEGER NOT NULL REFERENCES entities(id),
    source_id TEXT NOT NULL REFERENCES sources(id)
);

CREATE INDEX idx_relationships_from_id   ON relationships(from_id);
CREATE INDEX idx_relationships_to_id     ON relationships(to_id);
CREATE INDEX idx_relationships_source_id ON relationships(source_id);
