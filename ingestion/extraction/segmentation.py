"""A4: passage segmentation for extraction — a thin wrapper over the Stage 2
`passage_ref_extractor` scan (`loader/source_registry.py`) and the Stage 3
`ref_ranges.py` helpers (DEV-033), not a reimplementation of either.

Operates on the same cleaned text the chunker uses (`text_cleaner.clean()` collapses
blank-line runs to a single `\\n`, so paragraph breaks don't survive cleaning — marker
offsets are the only structural signal left). A segment here groups consecutive
MARKER INTERVALS (the same atomic unit DEV-034's paragraph-aligned chunker treats as
one chunk) up to `SEGMENT_SIZE`, deliberately coarser than the RAG chunker's
one-interval-per-chunk granularity, so a full genealogical statement spanning several
markers isn't split mid-claim (TODO-stage4 A4 / DEV-033 amendment). This is a
legitimately wider grouping than `narrative_chunks.passage_ref` — not a precedent for
chunk-level range width there.
"""

from dataclasses import dataclass
from typing import Callable

from chunker.text_chunker import _EMBEDDED_MARKER
from loader.ref_ranges import format_range, nearest_ref, range_end

SEGMENT_SIZE = 3000  # coarser than the RAG chunker's CHUNK_SIZE (1500) by design


@dataclass
class Segment:
    text: str  # embedded markers stripped — the form shown to the LLM
    passage_ref: str  # honest range/point (ref_ranges notation), or "Author, Work" fallback
    start_offset: int  # into the original (unstripped) cleaned text


def segment(
    text: str,
    author: str,
    work: str,
    extractor: Callable[[str], list[tuple[int, str]]],
) -> list[Segment]:
    refs = extractor(text)
    boundaries = sorted({0, len(text), *(offset for offset, _ in refs)})
    interval_count = len(boundaries) - 1

    segments: list[Segment] = []
    i = 0
    while i < interval_count:
        start_idx = i
        # A preamble interval (content before any marker) never merges forward — it
        # would otherwise swallow the next marker's precise ref into its own "Author,
        # Work" fallback, same as the chunker keeping preamble chunks separate.
        is_preamble = nearest_ref(refs, boundaries[start_idx]) is None
        # Keep folding in the next marker interval while the group stays under
        # SEGMENT_SIZE (a single oversized interval still gets its own segment, since
        # the inner condition never fires on the first interval alone).
        while (
            not is_preamble
            and i + 1 < interval_count
            and boundaries[i + 2] - boundaries[start_idx] <= SEGMENT_SIZE
        ):
            i += 1
        group_start, group_end = boundaries[start_idx], boundaries[i + 1]

        raw = text[group_start:group_end]
        stripped = _EMBEDDED_MARKER.sub("", raw).strip()
        if stripped:
            passage_ref = format_range(
                nearest_ref(refs, group_start), range_end(refs, group_end - 1)
            ) or f"{author}, {work}"
            segments.append(Segment(stripped, passage_ref, group_start))
        i += 1
    return segments
