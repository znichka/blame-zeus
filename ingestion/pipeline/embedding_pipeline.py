import hashlib
import json
import os

from openai import OpenAI
from pgvector.psycopg2 import register_vector
from tenacity import retry, stop_after_attempt, wait_exponential

import config
from chunker.text_chunker import OVERLAP_SENTENCES, Chunk
from loader.source_registry import SourceConfig

BATCH_SIZE = 20  # 100 chunks x 1500 chars ~= 37,500 tokens; batching avoids OpenAI's per-request token limit

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


@retry(wait=wait_exponential(multiplier=1, min=2, max=60), stop=stop_after_attempt(5), reraise=True)
def embed_batch(texts: list[str]) -> list[list[float]]:
    response = client.embeddings.create(model=config.EMBEDDING_MODEL, input=texts)
    return [item.embedding for item in response.data]


def content_hash(text: str) -> str:
    """Matches narrative_chunks.content_hash (Postgres md5() over the UTF-8 bytes)."""
    return hashlib.md5(text.encode("utf-8")).hexdigest()


def existing_chunk_keys(conn, source_ids: set[str]) -> set[tuple]:
    with conn.cursor() as cur:
        cur.execute(
            "SELECT source_id, passage_ref, content_hash FROM narrative_chunks WHERE source_id = ANY(%s)",
            (sorted(source_ids),),
        )
        return set(cur.fetchall())


def store_chunks(conn, chunks: list[Chunk]) -> None:
    register_vector(conn)
    # Skip already-stored chunks BEFORE embedding: ON CONFLICT DO NOTHING dedupes the
    # INSERT, but by then the OpenAI call is already paid for — a re-run must not
    # re-embed the whole corpus.
    existing = existing_chunk_keys(conn, {c.source_id for c in chunks})
    pending = [c for c in chunks if (c.source_id, c.passage_ref, content_hash(c.text)) not in existing]
    skipped = len(chunks) - len(pending)
    if skipped:
        print(f"Skipping {skipped} of {len(chunks)} chunks already embedded")
    with conn.cursor() as cur:
        for batch_start in range(0, len(pending), BATCH_SIZE):
            batch = pending[batch_start : batch_start + BATCH_SIZE]
            embeddings = embed_batch([c.text for c in batch])
            for c, embedding in zip(batch, embeddings):
                cur.execute(
                    """INSERT INTO narrative_chunks
                       (content, embedding, source_id, passage_ref, metadata)
                       VALUES (%s, %s, %s, %s, %s)
                       ON CONFLICT (source_id, passage_ref, content_hash) DO NOTHING""",
                    (
                        c.text,
                        embedding,
                        c.source_id,
                        c.passage_ref,
                        json.dumps(
                            {
                                "source_id": c.source_id,
                                "author": c.author,
                                "work": c.work,
                                "passage_ref": c.passage_ref,
                                "chunk_size": len(c.text),
                                "overlap_sentences": OVERLAP_SENTENCES,
                            }
                        ),
                    ),
                )
            # Commit per batch: a crash mid-run then loses at most one batch of embeddings
            conn.commit()


def validate_source_ids(conn, registry: list[SourceConfig]) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT id FROM sources")
        existing_ids = {row[0] for row in cur.fetchall()}
    missing = [s for s in registry if s.source_id not in existing_ids]
    if missing:
        raise RuntimeError(
            f"Source IDs not found in DB: {[s.source_id for s in missing]}. "
            f"Run core-api first to apply Flyway migrations and seed sources."
        )


def clear_source_chunks(conn, source_id: str) -> None:
    with conn.cursor() as cur:
        cur.execute("DELETE FROM narrative_chunks WHERE source_id = %s", (source_id,))
    conn.commit()
    print(f"Cleared existing chunks for source_id={source_id}")
