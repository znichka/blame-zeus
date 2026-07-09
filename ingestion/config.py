import os

# load_dotenv() is NOT called here — it must run in main.py before this module is
# imported, since top-level reads below execute at import time (see docs/TODO-stage2.md H1).

OPENAI_API_KEY = os.environ["OPENAI_API_KEY"]

POSTGRES_USER = os.environ["POSTGRES_USER"]
POSTGRES_PASSWORD = os.environ["POSTGRES_PASSWORD"]
POSTGRES_DB = os.environ["POSTGRES_DB"]

# Not in .env.example (Stage 1b) — ingestion runs from the host against the Dockerized
# Postgres via its published port, not from inside the compose network.
POSTGRES_HOST = os.environ.get("POSTGRES_HOST", "localhost")
POSTGRES_PORT = int(os.environ.get("POSTGRES_PORT", "5432"))
