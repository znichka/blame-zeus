-- Hand-curated (ADR-004: sources is unaffected by the extraction pivot). These 6 rows
-- reproduce, verbatim, what Stage 3 Track E (DEV-030) already hand-inserted into the
-- running dev DB ahead of this migration — id/author/work/translation/stance/
-- year_published/role must match exactly, or ON CONFLICT DO NOTHING silently no-ops
-- against different values. Corrections vs. the original IMPLEMENTATION_PLAN.md §3
-- placeholders: Homeric Hymns author is Anonymous, not Hesiod (DEV-018); Iliad/Odyssey
-- years were swapped in the plan (DEV-029); Ovid's real translator is Brookes More,
-- 1922, not the plan's 'PD' placeholder (DEV-029). Slugs match SourceConfig.source_id
-- in ingestion/loader/source_registry.py.
INSERT INTO sources (id, author, work, translation, stance, year_published, role) VALUES
    ('apollodorus-bibliotheca', 'Apollodorus', 'Bibliotheca', 'Frazer', 'mythographic-handbook', 1921, 'spine'),
    ('hesiod-theogony', 'Hesiod', 'Theogony', 'Evelyn-White', 'cosmological', 1914, 'spine'),
    ('hesiod-homeric-hymns', 'Anonymous ("Homeric")', 'Homeric Hymns', 'Evelyn-White', 'hymnic', 1914, 'primary'),
    ('homer-iliad', 'Homer', 'Iliad', 'Murray', 'poetic-myth', 1924, 'spine'),
    ('homer-odyssey', 'Homer', 'Odyssey', 'Murray', 'poetic-myth', 1919, 'primary'),
    ('ovid-metamorphoses', 'Ovid', 'Metamorphoses', 'Brookes More', 'poetic-myth', 1922, 'selective')
ON CONFLICT (id) DO NOTHING;
