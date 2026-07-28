-- Stage P4 Track G1/G2 (DEV-107, docs/TODO-phase2-stage-p4.md): the extraction pipeline emits
-- seven distinct raw claim_type spellings for what turned out, on per-row review of real sample
-- content (subject/claim_value pairs across all seven), to be ONE underlying concept -- a notable
-- narrative fact about the subject that doesn't fit any other structured claim_type (parentage,
-- death, marriage, epithet, transformation, abduction, role, punishment, burial). The candidate
-- "claim about a figure vs. deed done by one" split this track set out to evaluate does not exist
-- in the data: every one of the seven surface forms freely mixes active deeds ("Seized and bound
-- the Cercopes"), passive events ("fled when Achilles came"), and asserted claims ("Claims credit
-- for Troy's impending fall") -- reviewed, not guessed, per ADR-019 Track D's discipline against
-- inventing a split the data doesn't support. Canonical is 'notable_claim', the plurality surface
-- form (268 of 648 rows) -- the same majority-frequency rule audit check A9
-- (ingestion/audit/claim_type_distribution.py) already applies to its own mechanical duplicate
-- proposals, applied here to the full family for consistency.
INSERT INTO claim_type_aliases (alias, canonical) VALUES
    ('notable',       'notable_claim'),
    ('notable_deed',  'notable_claim'),
    ('notable_act',   'notable_claim'),
    ('notable claim', 'notable_claim'),
    ('notable act',   'notable_claim'),
    ('notable_event', 'notable_claim')
ON CONFLICT DO NOTHING;
