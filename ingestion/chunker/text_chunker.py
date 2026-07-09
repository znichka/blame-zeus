import re
from dataclasses import dataclass
from typing import Callable

CHUNK_SIZE = 1500  # target chars
OVERLAP_SENTENCES = 2  # sentences carried into next chunk's start


@dataclass
class Chunk:
    text: str
    source_id: str
    passage_ref: str
    author: str
    work: str
    start_offset: int


def split_sentences(text: str) -> list[tuple[int, str]]:
    results, pos = [], 0
    for m in re.finditer(r"(?<=[.!?])\s+", text):
        sent = text[pos : m.start() + 1].strip()
        if sent:
            results.append((pos, sent))
        pos = m.end()
    if pos < len(text):
        results.append((pos, text[pos:].strip()))
    return results


def chunk(
    text: str,
    source_id: str,
    author: str,
    work: str,
    extractor: Callable[[str], list[tuple[int, str]]],
) -> list[Chunk]:
    refs = extractor(text)  # [(offset, ref_string), ...]
    sentences = split_sentences(text)
    chunks = []
    i = 0
    while i < len(sentences):
        buf: list[tuple[int, str]] = []
        buf_len = 0
        start_offset = sentences[i][0]
        while i < len(sentences):
            next_len = len(sentences[i][1])
            # Stop *before* adding a sentence that would push the chunk past CHUNK_SIZE
            # (unless buf is still empty, so a single oversized sentence still gets
            # added and progress is guaranteed). The plan's literal "sum < CHUNK_SIZE"
            # check runs before adding too, but always admits one more full sentence
            # after crossing the threshold — on the real corpus this let a chunk
            # overshoot CHUNK_SIZE * 1.2 by absorbing a long trailing sentence.
            if buf and buf_len + next_len > CHUNK_SIZE:
                break
            buf.append(sentences[i])
            buf_len += next_len
            i += 1
        chunk_text = " ".join(s for _, s in buf)
        passage_ref = _nearest_ref(refs, start_offset) or f"{author}, {work}"
        chunks.append(
            Chunk(chunk_text, source_id, passage_ref, author, work, start_offset=start_offset)
        )
        if i >= len(sentences):
            break  # last chunk consumed the remaining sentences; nothing left to overlap into
        # Roll back for overlap, but never by more than len(buf) - 1: rolling back the full
        # OVERLAP_SENTENCES when the tail of the document has <= OVERLAP_SENTENCES sentences
        # left returns `i` to the same position every time (infinite loop, no forward
        # progress) since the inner loop above exits due to exhausting `sentences`, not
        # because CHUNK_SIZE was reached. Clamping guarantees at least 1 new sentence per
        # outer iteration.
        i -= min(OVERLAP_SENTENCES, len(buf) - 1)
    return chunks


def _nearest_ref(refs: list[tuple[int, str]], pos: int) -> str | None:
    result = None
    for offset, ref in refs:
        if offset <= pos:
            result = ref
        else:
            break
    return result
