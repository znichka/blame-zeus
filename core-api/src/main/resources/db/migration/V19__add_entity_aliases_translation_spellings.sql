-- Stage P4 Track H (GAP-002 long-tail triage, docs/TODO-phase2-stage-p4.md), DEV-108. Additive
-- follow-up to V14/V14_1 in the same style -- a fresh top-level version, not "V14_2": V15-V18 are
-- already applied, and a version numbered between V14_1 and V15 would sort *before* migrations
-- Flyway has already recorded, which it cannot accept.
--
-- All three aliases surfaced while triaging GAP-002's unknown-name long tail: each was initially a
-- candidate for a NEW entity (each had double-digit candidate-relationship reference counts), but
-- turned out to be a translation-spelling variant of an entity already confirmed:
--
--   Aesculapius -> Asclepius   Frazer's Apollodorus translation and Brookes More's Ovid both use
--                              the Latinized 'Aesculapius'; Evelyn-White's Homeric Hymns translation
--                              uses the Greek 'Asclepius', which was already confirmed. Same person
--                              (son of Apollo and Coronis, god of medicine) across both spellings.
--
--   Phorcus -> Phorcys         'Phorcys' (son of Pontus and Gaia, married to Ceto, father of the
--                              Phorcides/Gorgons/Graeae/Scylla per Apollodorus 1.2.1-1.2.7) was
--                              already confirmed; 'Phorcus' is the same figure under a translation
--                              spelling variant, appearing only in the candidate relationship rows.
--
--   Helios -> Helius           Caught only by re-running the full audit suite after this batch's
--                              first reseed: A1's transliteration pass fuzzy-matched the just-added
--                              'Helios' against the already-confirmed 'Helius' at 83.3 -- both are
--                              son of Hyperion, father of Circe/Aeetes, across the same source set
--                              (hesiod-theogony, homer-odyssey). 'Helios' was reverted from
--                              entities_candidates_confirmed_v1.json (it was never a real gap) and
--                              added here instead, keeping 'Helius' canonical since it was the one
--                              already confirmed before this batch touched anything.
--
-- None of the three was caught by A1 *before* being added: A1 only ever compares *confirmed*
-- entity names to each other, and none of these three was itself confirmed until this batch, so
-- none entered that comparison set until after the fact -- the same structural blind spot
-- DEV-098/DEV-099/DEV-100's A7 findings hit, but on the *translation-spelling* axis rather than
-- the *extraction-corruption* axis. Re-running the full audit suite after every batch, not just
-- the checks that seem relevant, is what caught 'Helios' here.
--
-- Mirrors ingestion/extraction/known_aliases.json, updated in the same change. UNIQUE(alias) on
-- V14's table prevents any of the three resolving to two entities; all three canonical targets
-- are already seeded (Asclepius/Phorcys/Helius predate this migration).

INSERT INTO entity_aliases (entity_id, alias)
SELECT e.id, v.alias
FROM (VALUES
    ('Aesculapius', 'Asclepius'),
    ('Phorcus',     'Phorcys'),
    ('Helios',      'Helius')
) AS v(alias, canonical)
JOIN entities e ON e.name = v.canonical
ON CONFLICT (alias) DO NOTHING;
