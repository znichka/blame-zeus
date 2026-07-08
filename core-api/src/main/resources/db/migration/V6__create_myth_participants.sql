CREATE TABLE myth_participants (
    myth_id   INTEGER NOT NULL REFERENCES myths(id),
    entity_id INTEGER NOT NULL REFERENCES entities(id),
    role      TEXT,
    PRIMARY KEY (myth_id, entity_id)
);
