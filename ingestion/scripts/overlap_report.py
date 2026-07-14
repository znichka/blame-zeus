"""Offline chunk diagnostics (DEV-033). Dry run only — no DB, no embedding calls.

Per source, over clean()+chunk() of the real corpus files:
  - overlap between consecutive chunks (chars shared with the previous chunk / chunk
    length): mean, p50, p90, and the share of chunks more than 30% overlapped — under
    DEV-034's paragraph-aligned chunking this should be ~0 everywhere except between
    sub-chunks of split oversized paragraphs (regression signal if it climbs);
  - passage_ref shape counts (range / point / "Author, Work" fallback);
  - containment-exception count: chunks whose range END came from the last-marker-inside
    fallback (EOF or book/work boundary), i.e. rows where content may extend past the
    stated end by up to one marker interval.

Run from the ingestion/ directory or anywhere: python scripts/overlap_report.py
"""

import sys
from pathlib import Path
from statistics import mean

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from chunker.text_chunker import chunk
from loader.ref_ranges import nearest_ref, range_end_info
from loader.source_registry import SOURCE_REGISTRY
from loader.text_cleaner import clean


def shared_chars_with_previous(prev_text: str, cur) -> int:
    """Longest sentence-aligned prefix of `cur.text` that is a suffix of the previous
    chunk's text. Sentence boundaries come from sentence_refs, so this measures the
    actual carried-over overlap, not accidental substring matches."""
    best = 0
    for entry in cur.sentence_refs:
        if prev_text.endswith(cur.text[: entry["end"]]):
            best = entry["end"]
    return best


def percentile(sorted_values: list[float], p: float) -> float:
    if not sorted_values:
        return 0.0
    index = min(len(sorted_values) - 1, round(p * (len(sorted_values) - 1)))
    return sorted_values[index]


def main() -> None:
    ingestion_root = Path(__file__).resolve().parents[1]
    header = (
        f"{'source':<24} {'chunks':>6} {'mean':>6} {'p50':>6} {'p90':>6} "
        f"{'>30%':>6} {'range':>6} {'point':>6} {'fallbk':>6} {'exc':>4}"
    )
    print(header)
    print("-" * len(header))
    for source in SOURCE_REGISTRY:
        raw = (ingestion_root / source.file_path).read_text(encoding="utf-8")
        cleaned = clean(raw)
        refs = source.passage_ref_extractor(cleaned)
        chunks = chunk(cleaned, source.source_id, source.author, source.work,
                       source.passage_ref_extractor)

        ratios = [
            shared_chars_with_previous(prev.text, cur) / len(cur.text)
            for prev, cur in zip(chunks, chunks[1:])
            if cur.text
        ]
        ratios.sort()

        author_fallback = sum(1 for c in chunks if c.passage_ref == f"{source.author}, {source.work}")
        ranged = sum(1 for c in chunks if "-" in c.passage_ref and c.passage_ref not in
                     (f"{source.author}, {source.work}",))
        points = len(chunks) - ranged - author_fallback
        containment_exceptions = sum(
            1
            for c in chunks
            if nearest_ref(refs, c.start_offset) is not None
            and range_end_info(refs, c.end_offset)[1]
        )

        print(
            f"{source.source_id:<24} {len(chunks):>6} "
            f"{mean(ratios) if ratios else 0:>6.2f} "
            f"{percentile(ratios, 0.5):>6.2f} "
            f"{percentile(ratios, 0.9):>6.2f} "
            f"{(sum(1 for r in ratios if r > 0.30) / len(ratios) if ratios else 0):>6.1%} "
            f"{ranged:>6} {points:>6} {author_fallback:>6} {containment_exceptions:>4}"
        )
    print(
        "\nmean/p50/p90 = overlap ratio with previous chunk; >30% = share of chunks more "
        "than 30% overlapped;\nexc = containment-exception rows (range end understated at "
        "EOF/book-boundary fallback)."
    )


if __name__ == "__main__":
    main()
