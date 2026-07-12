CREATE TABLE claim_type_aliases (
    alias     TEXT PRIMARY KEY,
    canonical TEXT NOT NULL
);

COMMENT ON TABLE claim_type_aliases IS
    'Normalization map for variant_claims.claim_type: normalize(x) = canonical for the row where alias = lower(trim(x)), identity when no row matches (canonicals need no self-row). Single source of truth shared by the offline Python conflict detector and the runtime Kotlin ConflictLookup — never duplicate this map in code or JSON.';

-- Canonical namespace per ADR-007 §1 / DEV-020: parentage, marriage, death.
-- Relation-type mappings (parent_of/married_to/killed_by) and free-text surface
-- forms collapse to the same canonicals so a disagreement split between a typed
-- relationship and prose still groups under one key.
INSERT INTO claim_type_aliases (alias, canonical) VALUES
    ('parent_of',       'parentage'),
    ('parents',         'parentage'),
    ('married_to',      'marriage'),
    ('killed_by',       'death'),
    ('killed by',       'death'),
    ('slain by',        'death'),
    ('slaying',         'death'),
    ('death_manner',    'death'),
    ('manner_of_death', 'death'),
    ('how he died',     'death');
