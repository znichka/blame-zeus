-- Track F (ADR-019, docs/TODO-phase2-stage-p3.md): the relationships.relation
-- analogue of claim_type_aliases (V8_2/DEV-022) -- collapses synonym/inverse
-- surface variants of relationships.relation to a canonical relation + direction,
-- shrinking SchemaIntrospector's advertised vocabulary for text-to-SQL (DEV-041).
CREATE TABLE relation_aliases (
    alias     TEXT PRIMARY KEY,
    canonical TEXT NOT NULL,
    inverse   BOOLEAN NOT NULL DEFAULT FALSE
);

COMMENT ON TABLE relation_aliases IS
    'Normalization map for relationships.relation: normalize_relation(x) = (canonical, inverse) for the row where alias = lower(trim(x)), identity (x, false) when no row matches (canonicals and legit-long-tail labels need no self-row). inverse=true means the alias is the reversed edge of its canonical -- ingestion/seedgen/relationships_gen.py swaps from_id/to_id at generation time so every row lands on the canonical relation and the canonical direction (DEV-047: parent_of''s from_id is the parent). Single source of truth read by ingestion/extraction/relation_normalizer.py -- never duplicate this map in code or JSON.';

-- Initial rows from the Stage P3 audit's A4 relation-label taxonomy check
-- (ingestion/audit/relation_taxonomy.py, DEV-071) -- classified against the live
-- relationships_candidates_cleaned.json vocabulary and reviewed before promotion.
-- New surface variants discovered later are appended via follow-up migrations
-- (e.g. a V17_1-style addition), never hardcoded elsewhere (the DEV-022 rule).
INSERT INTO relation_aliases (alias, canonical, inverse) VALUES
    ('child_of',            'parent_of',  TRUE),
    ('son_of',              'parent_of',  TRUE),
    ('daughter_of',         'parent_of',  TRUE),
    ('father_of',           'parent_of',  FALSE),
    ('mother_of',           'parent_of',  FALSE),
    ('killed',              'killed_by',  TRUE),
    ('sister_of',           'sibling_of', FALSE),
    ('brother_of',          'sibling_of', FALSE),
    ('brother_relation_of', 'sibling_of', FALSE);
