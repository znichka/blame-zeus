CREATE TABLE entities (
    id         SERIAL PRIMARY KEY,
    name       TEXT NOT NULL UNIQUE,
    type       TEXT NOT NULL,
    generation INTEGER,
    domain     TEXT,
    CONSTRAINT chk_entities_type CHECK (type IN ('primordial', 'titan', 'olympian', 'other_god', 'hero', 'mortal', 'monster', 'nymph'))
);

CREATE INDEX idx_entities_name_trgm ON entities USING gin(name gin_trgm_ops);
