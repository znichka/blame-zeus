-- Additive follow-up to V14 (DEV-100), in the V9_2 style: V14 is hand-written and already
-- applied, so new aliases land in their own migration rather than editing it (the Flyway
-- checksum trap -- see ingestion/audit/README.md).
--
-- Both aliases come from audit check A7 (name_coverage.py, DEV-099), which flags confirmed
-- entities the corpus names often but no candidate relationship row references. Both were
-- duplicate entities rather than missing ones, so each is removed from
-- entities_candidates_confirmed_v1.json (regenerating V10) and recorded here instead --
-- the same merge shape as DEV-092's Sky/Heaven/Uranus -> Ouranos.
--
--   Argeiphontes -> Hermes    A standing Homeric epithet, not a separate god: the Odyssey
--                             reads "let us send forth Hermes, the messenger, Argeiphontes"
--                             and "the messenger Argeiphontes". The extraction's own
--                             variant_claims candidates independently agree -- two rows
--                             carry subject_name='Hermes', claim_type='epithet',
--                             claim_value='Argeiphontes' (homer-iliad 24.77-24.119,
--                             homer-odyssey 10.274-10.320). A1 could never catch this:
--                             fuzz.ratio('argeiphontes','hermes') is 33.3.
--
--   Diomed -> Diomedes        Brookes More's metrical contraction, used only in Ovid (10x,
--                             zero elsewhere). Book 13's debate over Achilles' arms assigns
--                             it the Iliad Diomedes' own deeds -- "his sleeping Rhesus, his
--                             unwarlike Dolon, Helenus taken, and Pallas gained by theft --
--                             all done by night and all with Diomed". A1 misses this one by
--                             a hair: fuzz.ratio('diomed','diomedes') is 85.7, just under
--                             its 88 threshold.
--
-- Mirrors ingestion/extraction/known_aliases.json, updated in the same change. UNIQUE(alias)
-- on V14's table prevents either name resolving to two entities; both canonical targets are
-- seeded by V10.

INSERT INTO entity_aliases (entity_id, alias)
SELECT e.id, v.alias
FROM (VALUES
    ('Argeiphontes', 'Hermes'),
    ('Diomed',       'Diomedes')
) AS v(alias, canonical)
JOIN entities e ON e.name = v.canonical;
