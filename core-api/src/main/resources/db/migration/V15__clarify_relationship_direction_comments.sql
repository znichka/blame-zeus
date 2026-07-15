-- DEV-047: relationships.relation's comment (V8_3) documents the vocabulary but never states
-- which end is the subject. Text-to-SQL queries for e.g. "children of Cronus" guessed the wrong
-- direction (treating Cronus as to_id under a child_of relation) because the actual seeded data
-- is predominantly parent_of edges (from_id = parent, to_id = child). Document the from/to
-- convention directly on the columns so SchemaIntrospector surfaces it to TextToSqlAgent.

COMMENT ON COLUMN relationships.from_id IS
    'The subject of relation: for "parent_of" this is the parent; for "married_to"/"killed_by"/"overthrew" this is the acting/first-named entity. Read as "from_id <relation> to_id" (e.g. Cronus parent_of Zeus means Cronus is the parent).';
COMMENT ON COLUMN relationships.to_id IS
    'The object of relation: for "parent_of" this is the child. Read as "from_id <relation> to_id".';
