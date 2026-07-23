import os

# load_dotenv() is NOT called here — it must run in main.py before this module is
# imported, since top-level reads below execute at import time (see docs/TODO-stage2.md H1).

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

# Single source of truth for the embedding model name, shared with core-api via the
# EMBEDDING_MODEL env var (ADR-006). Value is locked to what the corpus was embedded with —
# changing it requires re-ingesting the full corpus.
EMBEDDING_MODEL = os.environ["EMBEDDING_MODEL"]

POSTGRES_USER = os.environ["POSTGRES_USER"]
POSTGRES_PASSWORD = os.environ["POSTGRES_PASSWORD"]
POSTGRES_DB = os.environ["POSTGRES_DB"]

# Read-only runtime user (Stage P2 Track G: ingestion/audit/cycle_check.py's --db reader
# connects as this user, never the superuser above, since it only reads). Optional --
# only audit's --db path needs it, so importing config shouldn't fail without it set.
POSTGRES_APP_USER = os.environ.get("POSTGRES_APP_USER")
POSTGRES_APP_PASSWORD = os.environ.get("POSTGRES_APP_PASSWORD")

# Not in .env.example (Stage 1b) — ingestion runs from the host against the Dockerized
# Postgres via its published port, not from inside the compose network.
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.environ.get("POSTGRES_PORT", "5432"))
