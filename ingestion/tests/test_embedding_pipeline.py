import os
from unittest.mock import MagicMock, patch

# Module-level OpenAI client + config require env vars at import time.
os.environ.setdefault("OPENAI_API_KEY", "test-key")
os.environ.setdefault("EMBEDDING_MODEL", "text-embedding-3-small")
os.environ.setdefault("POSTGRES_USER", "test")
os.environ.setdefault("POSTGRES_PASSWORD", "test")
os.environ.setdefault("POSTGRES_DB", "test")

import pipeline.embedding_pipeline as ep
from chunker.text_chunker import Chunk


def make_chunk(text: str, ref: str = "1.1.1") -> Chunk:
    return Chunk(
        text=text,
        source_id="apollodorus-bibliotheca",
        passage_ref=ref,
        author="Apollodorus",
        work="Bibliotheca",
        start_offset=0,
    )


def make_conn(existing_rows):
    conn = MagicMock()
    cur = conn.cursor.return_value.__enter__.return_value
    cur.fetchall.return_value = existing_rows
    return conn, cur


def insert_calls(cur):
    return [c for c in cur.execute.call_args_list if "INSERT" in c.args[0]]


def test_content_hash_matches_postgres_md5():
    # SELECT md5('abc') in Postgres (UTF-8 database) returns this digest
    assert ep.content_hash("abc") == "900150983cd24fb0d6963f7d28e17f72"


def test_skips_already_embedded_chunks_before_embedding():
    stored = make_chunk("already stored text")
    new = make_chunk("brand new text", ref="1.1.2")
    conn, cur = make_conn(
        [(stored.source_id, stored.passage_ref, ep.content_hash(stored.text))]
    )

    with patch.object(ep, "register_vector"), patch.object(
        ep, "embed_batch", return_value=[[0.0] * 3]
    ) as embed:
        ep.store_chunks(conn, [stored, new])

    embed.assert_called_once_with([new.text])
    assert len(insert_calls(cur)) == 1
    assert insert_calls(cur)[0].args[1][0] == new.text


def test_no_embedding_call_when_everything_already_stored():
    chunk = make_chunk("already stored text")
    conn, cur = make_conn([(chunk.source_id, chunk.passage_ref, ep.content_hash(chunk.text))])

    with patch.object(ep, "register_vector"), patch.object(ep, "embed_batch") as embed:
        ep.store_chunks(conn, [chunk])

    embed.assert_not_called()
    assert insert_calls(cur) == []
    conn.commit.assert_not_called()


def test_commits_once_per_batch():
    chunks = [make_chunk(f"chunk number {i}", ref=f"1.1.{i}") for i in range(45)]
    conn, cur = make_conn([])

    with patch.object(ep, "register_vector"), patch.object(
        ep, "embed_batch", side_effect=lambda texts: [[0.0] * 3 for _ in texts]
    ) as embed:
        ep.store_chunks(conn, chunks)

    assert [len(c.args[0]) for c in embed.call_args_list] == [20, 20, 5]
    assert len(insert_calls(cur)) == 45
    assert conn.commit.call_count == 3
