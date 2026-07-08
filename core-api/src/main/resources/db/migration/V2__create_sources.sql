CREATE TABLE sources (
    id          TEXT PRIMARY KEY,
    author      TEXT NOT NULL,
    work        TEXT NOT NULL,
    passage_ref TEXT,
    translation TEXT,
    stance      TEXT NOT NULL,
    year_published INTEGER NOT NULL,
    role        TEXT NOT NULL,
    CONSTRAINT chk_sources_stance CHECK (stance IN ('poetic-myth', 'mythographic-handbook', 'cosmological', 'hymnic')),
    CONSTRAINT chk_sources_role   CHECK (role   IN ('spine', 'primary', 'selective', 'stretch'))
);
