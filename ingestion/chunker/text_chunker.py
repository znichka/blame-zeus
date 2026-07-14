import re
from dataclasses import dataclass, field
from typing import Callable

from loader.ref_ranges import format_range, nearest_ref, range_end

CHUNK_SIZE = 1500  # target chars when splitting an oversized paragraph (or the preamble)
OVERLAP_SENTENCES = 2  # carried between sub-chunks of the SAME paragraph only (DEV-034)

# `passage_ref_extractor`s need these markers left in `text` to compute offsets (see
# text_cleaner.py's DEV-029 fix), but once a chunk's `passage_ref` is resolved the raw
# marker is redundant noise in the stored/embedded content — strip it here, after ref
# resolution, not in text_cleaner. Matches every marker shape seen across the corpus:
# bare `[90]`, dotted `[1.1.1]`/`[E.1.1]`, trailing-letter `[E.6.15a]`/`[929a]`, and the
# `[[219]`-style doubled-bracket OCR glitch (`\[+`). Deliberately narrow (starts with an
# optional `E.` then digits) so it never touches genuine editorial brackets in the
# translations, e.g. `[Jason]`, `[Zeus speaking:]`, `[Being the first to obtain ...]`.
_EMBEDDED_MARKER = re.compile(r"\[+(?:E\.)?\d+(?:\.\d+)*[a-z]?\]\s*")


@dataclass
class Chunk:
    text: str
    source_id: str
    passage_ref: str  # the paragraph's corpus-native range ("3.38-3.75"), a point, or "Author, Work"
    author: str
    work: str
    start_offset: int
    # One entry per stored sentence: {"ref": "3.38" | None, "start": int, "end": int},
    # offsets into the stored (marker-stripped) `text`. Under paragraph-aligned chunking
    # every entry carries the paragraph's start marker; kept for alignment audits and as
    # forward-compatibility should finer-grained markers ever land.
    sentence_refs: list[dict] = field(default_factory=list)
    # Original-text offset just past the last buffered sentence. Not stored in the DB;
    # lets offline audits (scripts/overlap_report.py) re-derive whether this chunk's
    # range end came from the containment-exception fallback.
    end_offset: int = 0


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
    """One chunk per marker interval ("paragraph") — DEV-034.

    Chunk boundaries snap to the corpus's own marker boundaries, so `passage_ref` is
    always the paragraph's native citation range (start marker → next marker minus 1,
    via ref_ranges), never a mid-paragraph point or a union across paragraphs. A
    paragraph longer than CHUNK_SIZE * 1.2 is split into ~CHUNK_SIZE sentence windows
    with OVERLAP_SENTENCES carried between them — every sub-chunk shares the
    paragraph's ref (the corpus's precision floor). Overlap never crosses a paragraph
    boundary. Text before the first marker forms "Author, Work" fallback chunks.
    """
    refs = extractor(text)  # [(offset, ref_string), ...]
    chunks: list[Chunk] = []
    boundaries = sorted({0, len(text), *(offset for offset, _ in refs)})
    for seg_start, seg_end in zip(boundaries, boundaries[1:]):
        seg_sentences = [
            (seg_start + offset, s) for offset, s in split_sentences(text[seg_start:seg_end])
        ]
        if not seg_sentences:
            continue
        # seg_end - 1 is the segment's last content char: seg_end itself is the next
        # marker's own offset, which must count as "next", never as "inside".
        passage_ref = format_range(
            nearest_ref(refs, seg_start), range_end(refs, seg_end - 1)
        ) or f"{author}, {work}"
        seg_len = sum(len(s) for _, s in seg_sentences)
        windows = (
            [seg_sentences] if seg_len <= CHUNK_SIZE * 1.2 else _split_windows(seg_sentences)
        )
        for window in windows:
            # Strip markers per sentence *before* joining, accumulating offsets as we
            # go, so each sentence_refs entry's [start:end] slice of the stored text is
            # aligned by construction. Sentences that were only a marker vanish
            # entirely (no ref entry) rather than leaving an empty slice behind.
            stored_parts: list[str] = []
            sentence_refs: list[dict] = []
            pos = 0
            for sent_offset, sent in window:
                stripped = _EMBEDDED_MARKER.sub("", sent).strip()
                if not stripped:
                    continue
                if stored_parts:
                    pos += 1  # the joining space
                sentence_refs.append(
                    {"ref": nearest_ref(refs, sent_offset), "start": pos, "end": pos + len(stripped)}
                )
                stored_parts.append(stripped)
                pos += len(stripped)
            if not stored_parts:
                continue  # marker-only segment/window — nothing citable to store
            chunks.append(
                Chunk(
                    " ".join(stored_parts),
                    source_id,
                    passage_ref,
                    author,
                    work,
                    start_offset=window[0][0],
                    sentence_refs=sentence_refs,
                    end_offset=window[-1][0] + len(window[-1][1]),
                )
            )
    return chunks


def _split_windows(sentences: list[tuple[int, str]]) -> list[list[tuple[int, str]]]:
    """Split one oversized paragraph's sentences into ~CHUNK_SIZE windows, carrying
    OVERLAP_SENTENCES between consecutive windows (intra-paragraph only)."""
    windows = []
    i = 0
    while i < len(sentences):
        buf: list[tuple[int, str]] = []
        buf_len = 0
        while i < len(sentences):
            next_len = len(sentences[i][1])
            # Stop *before* adding a sentence that would push the window past
            # CHUNK_SIZE (unless buf is still empty, so a single oversized sentence
            # still gets added and progress is guaranteed).
            if buf and buf_len + next_len > CHUNK_SIZE:
                break
            buf.append(sentences[i])
            buf_len += next_len
            i += 1
        windows.append(buf)
        if i >= len(sentences):
            break
        # Roll back for overlap, but never by more than len(buf) - 1: rolling back the
        # full OVERLAP_SENTENCES when fewer sentences remain would return `i` to the
        # same position every time (no forward progress). Clamping guarantees at least
        # 1 new sentence per window.
        i -= min(OVERLAP_SENTENCES, len(buf) - 1)
    return windows
