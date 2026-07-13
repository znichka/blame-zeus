from pathlib import Path

# load_dotenv() MUST precede `import config` — config.py reads env vars at import
# time, so importing it first would read values before .env is loaded (see
# docs/TODO-stage2.md H1).
from dotenv import load_dotenv

load_dotenv()

import psycopg2

import config
from chunker.text_chunker import chunk
from loader.source_registry import SOURCE_REGISTRY
from loader.text_cleaner import clean
from pipeline.embedding_pipeline import store_chunks, validate_source_ids

conn = psycopg2.connect(
    host=config.POSTGRES_HOST,
    port=config.POSTGRES_PORT,
    dbname=config.POSTGRES_DB,
    user=config.POSTGRES_USER,
    password=config.POSTGRES_PASSWORD,
)
validate_source_ids(conn, SOURCE_REGISTRY)  # fail fast if DB is not seeded
for source in SOURCE_REGISTRY:
    raw = Path(source.file_path).read_text(encoding="utf-8")
    cleaned = clean(raw)
    chunks = chunk(
        cleaned, source.source_id, source.author, source.work, source.passage_ref_extractor
    )
    store_chunks(conn, chunks)  # ON CONFLICT DO NOTHING skips existing rows
conn.close()
