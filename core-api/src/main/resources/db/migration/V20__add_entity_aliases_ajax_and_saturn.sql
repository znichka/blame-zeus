-- GAP-004 + GAP-006 entity-merge pass (docs/DATA-GAPS.md), DEV-121. Additive follow-up to
-- V14/V14_1/V19 in the same style -- a fresh top-level version, never an edit to an applied
-- migration (the Flyway checksum trap, ingestion/audit/README.md).
--
-- Two documented gaps, one merge pass, because both are the same shape: a figure split across
-- several entities that `entity_aliases` should have collapsed.
--
--   GAP-006 -- `Ajax` was fragmented across FIFTEEN entities for what are really two people.
--     Eight surface forms for Ajax the Greater (Ajax, Ajax the Great, Great Ajax, Ajax son of
--     Telamon, Ajax (Telamon's son), Aias (son of Telamon), Aias (Telamonian), Telamonian
--     Aias/Telamonian Ajax) and six for the Lesser (Ajax the Lesser, Ajax the Locrian, Ajax
--     (Oilean), Ajax son of Oileus, Aias (son of Oileus), Aias the less). Co-reference was proved
--     by their own candidate edges, not assumed: `Telamon parent_of` six of them and
--     `Oileus`/`Oileus parent_of` four. Canonical names follow this file's own precedent
--     (DEV-078/079/080/081/082): the bare name stays with the more central, more-referenced
--     figure -- `Ajax` = the Telamonian, who holds 49 of the 54 bare-name candidate rows -- and
--     the namesake takes a `Name (descriptor)` form, `Ajax (son of Oileus)`, matching
--     `Cecrops (son of Erechtheus)` / `Pandion (son of Cecrops)` / `Ilus (son of Dardanus)`.
--     (`Aias` -> `Ajax` already exists in V14 and is unchanged.)
--
--   GAP-004 -- `Saturn` existed as a separate `other_god` entity rather than an alias of the
--     `titan` `Cronus`, even though the parallel `Jove`/`Jupiter` -> Zeus and `Juno` -> Hera
--     aliases in V14 already do exactly this for the same translator (Brookes More's Ovid). The
--     inconsistency, not the missing row, is what made it a gap: DEV-119's A6 triage had to waive
--     Ovid's true `Zeus <- Saturn` and `Hera <- Saturn` claims as spurious second parents.
--
-- The Homeric `Oileus`/`Oileus` (diaeresis) spelling pair is merged in the same pass -- Murray's
-- Iliad uses the diaeresis, Frazer's Apollodorus does not -- canonical `Oileus`, the one already
-- confirmed. A1 could never have reached any of these: `fuzz.ratio` cannot span
-- `Great Ajax` <-> `Telamonian Aias`, and it only ever compares *confirmed* entity names, so the
-- unconfirmed `Oileus` spelling was outside its comparison set entirely.
--
-- Mirrors ingestion/extraction/known_aliases.json, updated in the same change. UNIQUE(alias) on
-- V14's table prevents any of these resolving to two entities. Both canonical targets are seeded
-- by V10: `Ajax` and `Oileus` predate this migration; `Ajax (son of Oileus)` is added by it.

INSERT INTO entity_aliases (entity_id, alias)
SELECT e.id, v.alias
FROM (VALUES
    -- GAP-006: Ajax the Greater, son of Telamon
    ('Ajax the Great',      'Ajax'),
    ('Great Ajax',          'Ajax'),
    ('Ajax son of Telamon', 'Ajax'),
    ('Ajax (Telamon''s son)', 'Ajax'),
    ('Aias (son of Telamon)', 'Ajax'),
    ('Aias (Telamonian)',   'Ajax'),
    ('Telamonian Aias',     'Ajax'),
    ('Telamonian Ajax',     'Ajax'),
    -- GAP-006: Ajax the Lesser, the Locrian, son of Oileus
    ('Ajax the Lesser',     'Ajax (son of Oileus)'),
    ('Ajax the Locrian',    'Ajax (son of Oileus)'),
    ('Ajax (Oilean)',       'Ajax (son of Oileus)'),
    ('Ajax son of Oileus',  'Ajax (son of Oileus)'),
    ('Aias (son of Oïleus)', 'Ajax (son of Oileus)'),
    ('Aias the less',       'Ajax (son of Oileus)'),
    -- GAP-006: the father's own translation-spelling duplicate
    ('Oïleus',              'Oileus'),
    -- GAP-004: Ovid's Roman theonym, alongside V14's Jove/Jupiter/Juno
    ('Saturn',              'Cronus')
) AS v(alias, canonical)
JOIN entities e ON e.name = v.canonical
ON CONFLICT (alias) DO NOTHING;
