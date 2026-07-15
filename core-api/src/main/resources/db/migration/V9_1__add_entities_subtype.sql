ALTER TABLE entities ADD COLUMN subtype TEXT;

COMMENT ON COLUMN entities.subtype IS
    'Fine-grained classification preserved from extraction (e.g. ''Nereid'', ''river god'') that does not fit the coarse entities.type CHECK enum. Free text, no CHECK constraint; nullable.';
