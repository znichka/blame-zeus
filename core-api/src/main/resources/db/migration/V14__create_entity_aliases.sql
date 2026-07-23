-- Hand-curated (C6). Cross-cultural / cross-spelling alias lookup for entity resolution:
-- ConflictLookup resolves a queried name exact -> alias -> trigram, so the Roman names
-- (Venus, Jupiter, ...) and Greek spelling variants (Kronos, Athene, ...) a user might
-- type all reach the canonical entity. Alias set mirrors ingestion/extraction/known_aliases.json
-- (the same list A3's extraction-time resolver uses); each canonical target below exists in
-- V10__seed_entities.sql. UNIQUE(alias) prevents a name resolving to two entities.

CREATE TABLE entity_aliases (
    id        SERIAL PRIMARY KEY,
    entity_id INTEGER NOT NULL REFERENCES entities(id),
    alias     TEXT NOT NULL,
    UNIQUE (alias)
);

INSERT INTO entity_aliases (entity_id, alias)
SELECT e.id, v.alias
FROM (VALUES
    -- Roman -> Greek
    ('Jupiter',  'Zeus'),
    ('Jove',     'Zeus'),
    ('Juno',     'Hera'),
    ('Neptune',  'Poseidon'),
    ('Pluto',    'Hades'),
    ('Dis',      'Hades'),
    ('Minerva',  'Athena'),
    ('Mars',     'Ares'),
    ('Venus',    'Aphrodite'),
    ('Cupid',    'Eros'),
    ('Vulcan',   'Hephaestus'),
    ('Mercury',  'Hermes'),
    ('Diana',    'Artemis'),
    ('Ceres',    'Demeter'),
    ('Vesta',    'Hestia'),
    ('Bacchus',  'Dionysus'),
    ('Hercules', 'Heracles'),
    ('Ulysses',  'Odysseus'),
    ('Aurora',   'Eos'),
    -- Greek spelling variants (trigram fallback + already-merged duplicates per DEV-043)
    ('Herakles', 'Heracles'),
    ('Kronos',   'Cronus'),
    ('Cronos',   'Cronus'),
    ('Ouranos',  'Uranus'),
    ('Phoebus',  'Apollo'),
    ('Aias',     'Ajax'),
    ('Athene',   'Athena'),
    ('Ocean',    'Oceanus'),
    -- J1 fuzzy-duplicate merges (Stage P3 Track J1, DEV-084)
    ('Ilithyia', 'Eileithyia'),
    ('Alcmene',  'Alcmena'),
    ('Atropus',  'Atropos'),
    ('Euneos',   'Euneus'),
    ('Cebrenus', 'Cebren'),
    ('Perimela', 'Perimele'),
    ('Lampetia', 'Lampetie'),
    -- J-lead follow-up (Coeranos/Coeranus untangling, DEV-087)
    ('Coeranos', 'Coeranus (Lycian warrior)')
) AS v(alias, entity_name)
JOIN entities e ON e.name = v.entity_name
ON CONFLICT (alias) DO NOTHING;
