"""Shared passage-ref range helpers (DEV-033).

Used by the chunker now and by Stage 4's A4 extraction segmentation later, so both
stamp the same range notation ("9.114-9.140") onto narrative_chunks / variant_claims.

A chunk-level `passage_ref` is a CONTAINMENT claim: all chunk content lies within
[start, end] where end = (first marker after the chunk's end) minus one line. When
that decrement is undefined (no next marker at end of file, next marker's prefix
differs with no same-prefix marker inside the span, non-integer final component),
we fall back to the last marker *inside* the span — which understates the end:
content may extend past it by up to one marker interval. Fabricating an end would
be worse; the exception is documented (ADR-014 amendment) and counted per-ingest
by scripts/overlap_report.py.
"""

import re

_INT_COMPONENT = re.compile(r"^\d+$")


def nearest_ref(refs: list[tuple[int, str]], pos: int) -> str | None:
    """Last marker at or before `pos`; None if `pos` precedes every marker."""
    result = None
    for offset, ref in refs:
        if offset <= pos:
            result = ref
        else:
            break
    return result


def range_end_info(refs: list[tuple[int, str]], end_offset: int) -> tuple[str | None, bool]:
    """End of the containment range for a span ending at `end_offset`.

    Returns (end_ref, used_fallback). `used_fallback=True` marks the containment
    exception: the returned end is the last marker inside the span, so content may
    extend past it (see module docstring).

    Boundary asymmetry is deliberate: the next-marker scan uses strict `>` while
    nearest_ref uses `<=`, so a marker exactly at end_offset counts as inside the
    span *and* is skipped as "next" — this only ever widens the end (containment-
    safe) and is practically unreachable given separator whitespace.
    """
    inside = nearest_ref(refs, end_offset)
    next_ref = None
    for offset, ref in refs:
        if offset > end_offset:
            next_ref = ref
            break
    if next_ref is None:  # end of file — no marker after the span
        return inside, True
    prefix, _, last = next_ref.rpartition(".")
    inside_prefix = inside.rpartition(".")[0] if inside is not None else None
    if inside is not None and _INT_COMPONENT.match(last) and prefix == inside_prefix:
        decremented = f"{prefix}.{int(last) - 1}" if prefix else str(int(last) - 1)
        return decremented, False
    # Cross-context boundary (next marker opens a new book/hymn with no same-prefix
    # marker inside the span) or non-decrementable shape (e.g. "E.6.15a").
    return inside, True


def range_end(refs: list[tuple[int, str]], end_offset: int) -> str | None:
    return range_end_info(refs, end_offset)[0]


def _sort_key(ref: str) -> tuple:
    # Numeric components compare numerically, others lexically; the (0|1) tag keeps
    # mixed tuples comparable ("E.6.15a" never raises against "1.1.4").
    return tuple(
        (0, int(part)) if _INT_COMPONENT.match(part) else (1, part)
        for part in ref.split(".")
    )


def format_range(start: str | None, end: str | None) -> str | None:
    """Range string for a chunk, or None when the caller should keep its own
    "Author, Work" fallback (span starts before any marker)."""
    if start is None:
        return None
    if end is None or end == start:
        return start
    if _sort_key(end) <= _sort_key(start):  # single-marker interval collapsed by the decrement
        return start
    return f"{start}-{end}"
