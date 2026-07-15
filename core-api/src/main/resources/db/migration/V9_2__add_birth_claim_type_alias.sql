-- DEV-042: 'birth' surfaced during B5 review as a distinct claim_type extraction used
-- for unusual-origin narratives (Aphrodite's sea-foam birth, Athena's birth from
-- Zeus's head, etc.) -- semantically a parentage/origin claim, but not covered by any
-- existing alias, so rows under it never grouped with 'parentage' rows about the same
-- subject. Per DEV-022's standing pattern: new surface variants discovered during
-- extraction are appended here, never hardcoded elsewhere.
INSERT INTO claim_type_aliases (alias, canonical) VALUES
    ('birth', 'parentage')
ON CONFLICT DO NOTHING;
