ALTER TABLE variant_claims ADD COLUMN passage_ref TEXT;
ALTER TABLE relationships  ADD COLUMN passage_ref TEXT;

COMMENT ON COLUMN variant_claims.passage_ref IS
    'Passage-level provenance within the source work (same format as narrative_chunks.passage_ref, e.g. ''2.1.3'' for Apollodorus). Populated mechanically from the extraction segment, never by the LLM; nullable for hand-added rows without a precise ref.';
COMMENT ON COLUMN relationships.passage_ref IS
    'Passage-level provenance within the source work (same format as narrative_chunks.passage_ref). Populated mechanically from the extraction segment; nullable.';
