import json
import os

from openai import OpenAI
from pgvector.psycopg2 import register_vector
from tenacity import retry, stop_after_attempt, wait_exponential

from chunker.text_chunker import OVERLAP_SENTENCES, Chunk
from loader.source_registry import SourceConfig

BATCH_SIZE = 20  # 100 chunks x 1500 chars ~= 37,500 tokens; batching avoids OpenAI's per-request token limit

client = OpenAI(api_key=os.environ["OPENAI_API_KEY"])


@retry(wait=wait_exponential(multiplier=1, min=2, max=60), stop=stop_after_attempt(5), reraise=True)
def embed_batch(texts: list[str]) -> list[list[float]]:
    response = client.embeddings.create(model="text-embedding-3-small", input=texts)
    return [item.embedding for item in response.data]


def store_chunks(conn, chunks: list[Chunk]) -> None:
    register_vector(conn)
    with conn.cursor() as cur:
        for batch_start in range(0, len(chunks), BATCH_SIZE):
            batch = chunks[batch_start : batch_start + BATCH_SIZE]
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
