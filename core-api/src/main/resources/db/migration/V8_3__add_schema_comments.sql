-- Schema self-description for the text-to-SQL prompt. SchemaIntrospector emits these
-- comments (plus CHECK clauses, FKs, and live value vocabularies) so prompt rules like
-- "join sources for relationships but not for entity attributes" are derivable from the
-- schema instead of hand-listed. Keep comments about query semantics, not implementation.

COMMENT ON TABLE entities IS
    'Curated classification of mythological figures. type/generation/domain carry NO source attribution — never join sources for them and never fabricate a citation.';
COMMENT ON COLUMN entities.generation IS
    'Divine generation number (1 = primordial); NULL for mortals and heroes.';

COMMENT ON TABLE relationships IS
    'Typed edges between entities, each attributed to a source. Exactly one canonical edge per contested relationship (spine-source preferred); competing versions live in variant_claims, not here.';
COMMENT ON COLUMN relationships.relation IS
    'Relation vocabulary is enumerated live in the schema description (e.g. parent_of, married_to, killed_by) — use those exact strings, never synonyms like spouse_of.';

COMMENT ON TABLE sources IS
    'Ancient-source registry; id is a stable human-readable slug (e.g. apollodorus-bibliotheca). Join for attribution whenever a table carries a source_id FK.';
COMMENT ON COLUMN sources.role IS
    'Corpus tier: spine = fully indexed backbone, primary/selective = partial, stretch = optional.';
COMMENT ON COLUMN sources.year_published IS
    'Publication year of the public-domain translation, used in citations.';

COMMENT ON TABLE myths IS
    'Structural/organizational container only — no source_id FK. Never treat as authoritative for factual claims; narrative content lives in narrative_chunks, contested claims in variant_claims.';

COMMENT ON TABLE variant_claims IS
    'One row per attributed version of a claim; multiple rows per (subject, claim_type) when sources disagree. claim_type is stored as the normalized canonical value (see claim_type_aliases).';
COMMENT ON COLUMN variant_claims.trust_tier IS
    '1 = verified hand-curated, 2 = reviewed, 3 = provisional; runtime seed rows are trust_tier = 1.';

COMMENT ON TABLE narrative_chunks IS
    'RAG vector store of corpus text; queried by embedding similarity, not by text-to-SQL.';
