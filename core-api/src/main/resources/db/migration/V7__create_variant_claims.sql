CREATE TABLE variant_claims (
    id                SERIAL PRIMARY KEY,
    subject_entity_id INTEGER NOT NULL REFERENCES entities(id),
    claim_type        TEXT NOT NULL,
    claim_value       TEXT NOT NULL,
    source_id         TEXT NOT NULL REFERENCES sources(id),
    trust_tier        SMALLINT NOT NULL DEFAULT 2
);

CREATE INDEX idx_variant_claims_subject_type ON variant_claims(subject_entity_id, claim_type);
