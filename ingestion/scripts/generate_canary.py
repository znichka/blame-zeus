"""Offline, one-time generation of the Stage 6 embedding-consistency canary fixture (F2).

Embeds a fixed query string with the live EMBEDDING_MODEL and writes the vector to
core-api/src/test/resources/canary-aphrodite.json. EmbeddingConsistencyTest pins the
embedding model's output against this file so a silent model/dimension swap is caught.

Run from the ingestion/ directory: python scripts/generate_canary.py
Requires a live OPENAI_API_KEY (loaded from .env at the repo root).
"""

import json
import sys
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
load_dotenv(REPO_ROOT / ".env")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import config  # noqa: E402  (must import after load_dotenv)
from pipeline.embedding_pipeline import embed_batch  # noqa: E402

CANARY_QUERY = "Who were Aphrodite's parents?"
OUTPUT_PATH = REPO_ROOT / "core-api" / "src" / "test" / "resources" / "canary-aphrodite.json"


def main() -> None:
    [vector] = embed_batch([CANARY_QUERY])
    payload = {
        "query": CANARY_QUERY,
        "embeddingModel": config.EMBEDDING_MODEL,
        "dimensions": len(vector),
        "vector": vector,
    }
    OUTPUT_PATH.write_text(json.dumps(payload))
    print(f"Wrote {OUTPUT_PATH} ({len(vector)} dims, model={config.EMBEDDING_MODEL})")


if __name__ == "__main__":
    main()
