# ADR-014: `passage_ref` Follows Standard Classical Citation Notation, Not Raw Scraped Markers

| Field        | Value       |
|--------------|-------------|
| **Date**     | 2026-07-13  |
| **Status**   | Accepted (applied 2026-07-13 — see Implementation Checklist; amended 2026-07-13 — range-valued refs, see Amendments below; corrected 2026-07-14 — `sentence_refs` precision claim, see Correction below) |

**Traceability:** `IMPLEMENTATION_PLAN.md §4` (Ingestion Job / passage-ref extractor table — amendment banner added) · `docs/DEVIATIONS.md` #DEV-011, #DEV-029 (the deviation that prompted this ADR) · `docs/TODO-stage3.md` Tracks B, C, D (superseded) · `CLAUDE.md` Data Model (`sources`, `narrative_chunks.passage_ref`, `variant_claims.passage_ref`)

---

## Context

Nothing in the project's docs — `CONCEPT.md`, `IMPLEMENTATION_PLAN.md`, `TECH_GUARDRAILS.md`, or any prior ADR — ever states what notation `passage_ref` should follow. `IMPLEMENTATION_PLAN.md §4`'s marker table only describes assumed regex shapes for scraping each source file; it carries no citation-standard rationale, and (per DEV-029) those assumed shapes didn't even match the real downloaded corpus. This left an open question once the real per-source extractors were built (DEV-029, Stage 3): should `passage_ref` echo whatever marker shape happens to sit in the scraped `.txt` file, or should it follow the notation classicists actually use to cite these six works?

This matters beyond cosmetics. `passage_ref` is user-facing: it appears in RAG citations and in surfaced conflicts (`ConflictSynthesizer`), and the product's stated differentiator is source attribution the reader can verify against a real edition. A ref like `"[194]"` (the bracket shape scraped from theoi.com) means nothing to a reader trying to cross-check a claim in a library copy of the *Iliad*; `"Il. 1.194"` does, because it's exactly how classicists, translators, and reference works (Perseus Digital Library, the Oxford Classical Dictionary, the TLG canon) cite it.

## Decision

**`passage_ref` values follow the standard modern classical citation convention for each work — the numbering scheme used by Perseus/the OCD/the TLG — not the raw bracket/line shape found in the scraped `.txt` corpus files.** The scraped markers are read as *input* to locate each ref's offset; the *emitted* `passage_ref` string is the citation form a reader would recognize from any scholarly edition:

| Work | `passage_ref` shape | Example | Standard citation it matches |
|---|---|---|---|
| Apollodorus, *Bibliotheca* | `book.chapter.section` (Epitome: `E.chapter.section`) | `1.1.1`, `E.1.1` | `Apollod. 1.1.1`, `Apollod. Epit. 1.1` |
| Hesiod, *Theogony* | line number alone (no book/chapter division) | `116` | `Theog. 116` |
| Homeric Hymns | `hymn.line`, hymn number in Arabic | `2.90` | `Hom. Hymn 2.90` / `h.Cer. 90` |
| Homer, *Iliad* / *Odyssey* | `book.line`, book number in Arabic | `1.194` | `Il. 1.194`, `Od. 9.105` |
| Ovid, *Metamorphoses* | `book.line`, book number in Arabic | `1.89` | `Met. 1.89` |

Two notational choices follow directly from what "standard" means for these specific works, not from arbitrary preference:

1. **Arabic, not Roman, numerals for book/hymn numbers.** Perseus and the TLG cite `Il. 1.194`, not `Il. I.194`; Roman numerals are a print-typesetting convention (and how Loeb prints running headers), not the citation index itself. The source corpus happens to already use Arabic `BOOK 1` headers for Iliad/Odyssey/Ovid — no conversion needed there — but the Homeric Hymns' source headers *are* Roman (`I. TO DIONYSUS`, `II. TO DEMETER`), matching the traditional Allen/Evelyn-White hymn ordering, so the extractor converts that numeral to Arabic before emitting the ref.
2. **No book/chapter division for the *Theogony*.** It is a single continuous poem; the standard citation is line number alone (`Theog. 116`), never a synthetic `1.116`.

## Rationale

1. **The citation only has value if a reader can act on it.** `passage_ref` exists so a claim can be checked against a real edition (`CONCEPT.md`'s whole premise). A notation only the ingestion pipeline understands defeats that; the standard scholarly form is the one an actual reader — or another scholar's citation — will recognize and can look up.
2. **"Widely used" has a concrete, checkable answer here**, unlike many style questions: classical citation notation is standardized across Perseus, the OCD, and the TLG specifically so that any two scholars' citations of the same passage match. There's no ambiguity to adjudicate.
3. **Decoupling emitted-ref-shape from scraped-marker-shape also insulates the schema from corpus-source churn.** If a future re-scrape (a different site, a different transcription) changes the raw bracket shape again, only the extractor's input-side regex needs to change — the citation contract stored in `narrative_chunks.passage_ref` / `variant_claims.passage_ref` and shown to users stays stable.
4. **Precedent:** DEV-011 already established that Apollodorus's own marker shape (`book.chapter.section`) coincides with its standard citation — this ADR generalizes that same alignment goal to the other five sources, where the raw marker shape (bare `[N]`) does *not* coincide with the standard citation and therefore needs a transform, not a pass-through.

## Consequences

**Positive**
- Every `passage_ref` in the system, across all six sources, is now a citation a classicist would recognize on sight — a meaningfully stronger version of the product's "attribution you can verify" promise than "attribution you can verify if you also know our scraping format."
- The extractor/citation-shape decoupling (Rationale #3) means the notation survives future corpus re-sourcing without a schema or synthesis-prompt change.
- Uniform `book.line` / `hymn.line` shape across Homer/Ovid/Hymns simplifies any future citation-formatting code in `RagAgent`/`ConflictSynthesizer` (one `"{book}.{line}"` pattern to render, not five bespoke shapes).

**Negative / trade-offs**
- The extractor now does slightly more work than a pure scan-and-return (a roman-to-arabic conversion for hymn headers); this is a handful of lines, not a material complexity cost.
- `passage_ref` values no longer let a developer `grep` the raw `.txt` corpus file for the literal ref string (e.g. searching the Iliad file for `"1.194"` won't find a `[194]`-shaped marker verbatim). Mitigated by `test_passage_ref_extractors.py`'s explicit offset assertions, which pin the mapping in tests rather than relying on visual grep.
- Depends on the corpus's `BOOK`/hymn headers being reliably present and well-formed for every book/hymn (verified for all 6 sources in DEV-029's full-corpus dry run — every book/hymn's ref range lands within that work's known real extent).

## Alternatives Considered

- **Emit the raw scraped marker shape verbatim** (e.g. `"[194]"`, or the plan's originally assumed `"ll. 116-138"`). Rejected: means nothing to a reader checking the citation against a real edition, and ties the schema's citation contract to one specific transcription's incidental formatting choices.
- **Store both the raw marker and the standard citation** (e.g. add a second column or JSONB field). Rejected for the PoC: no consumer needs the raw marker once the standard citation is derivable and tested; adds schema surface for no identified use case. Revisit only if a future feature (e.g. "show me the original scan") needs it.
- **Keep Roman numerals for book/hymn numbers to visually mirror the source `.txt` files.** Rejected: the source files' Iliad/Odyssey/Ovid headers are already Arabic, so this would have meant *introducing* Roman numerals where none exist in the source, purely to imitate Loeb print typesetting rather than actual citation practice — the opposite of "standard."

## Traceability

- `docs/DEVIATIONS.md` #DEV-011 (Apollodorus marker-shape precedent), #DEV-029 (the extractor/cleaner implementation this ADR documents the rationale for).
- `IMPLEMENTATION_PLAN.md §4` (passage-ref extractor table; amendment banner points here).
- `docs/TODO-stage3.md` Tracks B/C/D (superseded implementation plan; marked `[DEVIATED]`).
- `CLAUDE.md` Data Model section (`sources`, `narrative_chunks.passage_ref`, `variant_claims.passage_ref` — all consumers of this notation).

## Implementation Checklist

- [x] `ingestion/loader/source_registry.py`: `hesiod_theogony_refs`, `hesiod_homeric_hymns_refs`, `book_line_refs` (shared by Iliad/Odyssey/Ovid) emit the notation in the table above; `apollodorus_refs` unchanged (already compliant).
- [x] `ingestion/loader/text_cleaner.py`: footnote-marker and page-header regexes fixed so the underlying scraped markers survive cleaning (DEV-029) — a prerequisite for the extractors to see them at all.
- [x] `ingestion/tests/test_passage_ref_extractors.py`, `test_text_cleaner.py`: updated/extended; 33 tests passing (13 + 20; 46 across the full `ingestion/tests/` suite).
- [x] Verified against the real, full corpus files (dry run, no DB writes): ref counts and book/line extents land within each work's known real length for all 6 sources.
- [ ] `V9__seed_sources.sql` (Stage 4, not yet written): no schema impact — `passage_ref` is `TEXT`, notation-agnostic — but confirm no downstream code assumes the old bracket shape when Stage 4/5/6 are built.
- [ ] `RagAgent` / `ConflictSynthesizer` (Stage 6, not yet built): when citation-rendering prompts/DTOs are written, format against this table (e.g. prefix with `Il.`/`Met.`/`Theog.` for user-facing display) rather than re-deriving a notation independently. Display may also apply classical elision to ranges (`Il. 9.114–140`) but never "fix" the stored full-prefix form. Cite at the **chunk level** via `passage_ref` — `metadata.sentence_refs` carries no finer citation than that (see Correction below); its offsets are for locating/highlighting the quoted sentence within `content`, not for a more precise ref.

---

## Amendment (2026-07-13) — Chunk-level `passage_ref` is a containment range (DEV-033)

Manual verification after DEV-032 showed a chunk-level point ref is only a **lower bound**: a ~1500-char chunk spans 15–35 verse lines, so two sequential non-overlapping Iliad chunks both carried `9.114` while content deep in the second belongs to line ~141+. A ref that *looks* precise but means "somewhere at or after this marker" quietly breaks this ADR's promise. Resolution (full rationale and measurements in DEV-033):

1. **Notation.** A chunk's `passage_ref` is `"start-end"` (e.g. `"9.114-9.161"`), a **containment claim**: all chunk content lies within `[start, end]`. `start` = nearest marker at or before the chunk start (unchanged); `end` = (first marker after the chunk's end) **minus 1 line**. The ref collapses to a bare point when the chunk sits inside a single marker interval; the `"Author, Work"` fallback for chunks that start before any marker is unchanged. Ranges match classical span citation (`Il. 9.114–140`).
2. **Decrement rule.** The minus-1 applies only when the next marker's final dot-component is a plain integer and its book/hymn/chapter prefix matches the nearest marker at or before the chunk's end. A chunk straddling a book boundary *with markers of the new book inside it* therefore legitimately gets a cross-prefix range (`"1.595-2.15"`).
3. **Containment exception (accepted, documented, counted).** Where the decrement is undefined — next marker opens a new book/hymn with no same-prefix marker inside the chunk, end of file, or a non-decrementable shape (`E.6.15a`) — the end falls back to the last marker *inside* the chunk, which for a containment claim is the unsafe direction: content may extend past the stated end by up to one marker interval. Fabricating an end would be worse; `ingestion/scripts/overlap_report.py` counts these rows per ingest (currently 40/1/14/21/18/22 across the six sources). For Apollodorus the fallback end is in fact exact, not understated — its markers open prose *sections*, so content between markers belongs to the last-started section.
4. **Stored form vs. display.** The stored ref always repeats the full prefix on both ends (`"9.114-9.161"`) for parseability; classical elision (`Il. 9.114–161`) is Stage 6 display formatting only. Do not "normalize" the stored form.
5. **Sentence-level precision.** Each chunk's `metadata.sentence_refs` (JSONB) carries one `{"ref", "start", "end"}` entry per stored sentence, with char offsets into the stored `content` — the actual precision instrument for Stage 6's `RagAgent` when it quotes an excerpt; the chunk range is the fallback granularity.
6. **Precision ceiling = marker density.** Denser transcriptions (5-line markers) mechanically tighten both ranges and sentence refs with no code change. The shared helper `ingestion/loader/ref_ranges.py` owns `range_end`/`format_range`; Stage 4's extraction segmentation must reuse it so `relationships`/`variant_claims` provenance shares this exact notation.

---

## Amendment 2 (2026-07-13) — Paragraph-aligned chunking; refs are corpus-native (DEV-034)

Amendment 1 kept 1500-char sentence-window chunks and stamped honest containment unions over whatever a window spanned. User review found those unions both **too broad** (windows straddling paragraph boundaries → `9.114-9.161`) and **duplicated** (several windows inside one large paragraph → identical ranges). Superseding decision (full detail in DEV-034):

1. **Chunk boundaries snap to marker boundaries.** Every `[N]` marker in the corpus opens a prose paragraph covering lines N..(next marker − 1); a chunk is exactly one such paragraph, and its `passage_ref` is that paragraph's native range (`"3.38-3.57"`) — both endpoints exact by construction. Apollodorus (whose markers open *sections*) stores bare points (`1.1.4`), matching `Apollod. 1.1.4` citation practice. This is the narrowest citation the corpus can support; the planned denser-transcription swap is retired as unnecessary.
2. **Oversized paragraphs** (> `CHUNK_SIZE * 1.2`, ~160 corpus-wide) split into ~`CHUNK_SIZE` sentence windows with `OVERLAP_SENTENCES` carried between them; all sub-chunks cite the same paragraph range — the only remaining duplicate refs, at the corpus's precision floor.
3. **No overlap across paragraph boundaries** (cross-chunk redundancy fell from mean 23–37% to 1–3%).
4. Amendment 1's containment exception now surfaces as a **bare point** on book/hymn-final paragraphs and at EOF (start marker cited, end underivable). Points 4 and 6 of Amendment 1 (stored form vs. display; shared `ref_ranges.py`) stand unchanged; cross-prefix straddle ranges no longer occur in `narrative_chunks` but remain legal for Stage 4's multi-interval extraction segments. **Point 5 (sentence-level precision) is corrected, not carried forward as written — see the Correction below**, which this chunking model makes necessary: a chunk is now exactly one marker interval, so every sentence inside it resolves to the same marker `sentence_refs` was meant to distinguish between.

Also note: Amendment 1 point 1's "collapses to a point when the chunk sits inside a single marker interval" describes a narrower condition than "single marker interval" now suggests under this model — see the Correction below.

---

## Correction (2026-07-14) — `sentence_refs` carries no citation precision beyond the chunk's own `passage_ref`

Manual DB inspection (both authors, against the live `narrative_chunks` table post-DEV-034) found Amendment 1 point 5's "actual precision instrument" framing does not hold and was never corrected when Amendment 2 landed:

1. **Why it can't hold.** Under paragraph-aligned chunking (Amendment 2), a chunk is bounded by exactly one marker interval — there is no marker anywhere between a paragraph's start and its end for an individual sentence to resolve to differently. `nearest_ref()` therefore returns the *same* marker for every sentence in a chunk, always. Verified directly against the live DB: zero chunks anywhere in the corpus have more than one distinct `ref` value among their `sentence_refs` entries, and every non-null `sentence_refs[].ref` equals its own chunk's `passage_ref` start. This is a structural property of the corpus (markers exist only at paragraph boundaries), not a bug — it can't be fixed without inventing refs the source text doesn't contain, which the project's containment-honesty principle (Amendment 1 point 3) already rules out.
2. **What `sentence_refs` is actually for.** The `{"ref", "start", "end"}` entries remain useful for **locating a quoted sentence's char span within stored `content`** (e.g. for excerpt highlighting) — `start`/`end` are real, sentence-boundary-aligned offsets. The `ref` field is redundant with the chunk's `passage_ref` and should not be read as adding precision.
3. **Decision: keep the field as-is, no code change.** The offset-tracking behavior has independent value; only the *documentation's claim about what it provides* was wrong. Implementation Checklist item above updated accordingly; no change to `ingestion/chunker/text_chunker.py`, `ingestion/loader/ref_ranges.py`, or stored data.
4. **Clarifying Amendment 1 point 1**, which reads ambiguously once "single marker interval" became the universal per-chunk case (Amendment 2): the collapse-to-a-point condition is specifically *decremented end equals the start marker* — i.e., the paragraph's start and the next paragraph's marker are exactly one line apart. It is **not** "any chunk that doesn't cross a paragraph boundary" — under Amendment 2 that describes nearly every chunk, yet most poetic-source chunks still render as multi-line ranges (e.g. Iliad: 1,167 of 1,194 marked chunks are ranges, not points — spans of ~10–30 lines are typical). Points collapse only for Apollodorus's section-level markers (adjacent sections, one interval apart by definition) and for book/hymn-final or EOF paragraphs hitting the containment-exception fallback.
5. **Amendment 1's exception counts (`40/1/14/21/18/22`) are superseded** by Amendment 2's re-measurement under paragraph-aligned chunking: `50/1/33/25/24/15` (Apollodorus/Theogony/Hymns/Iliad/Odyssey/Ovid), from `ingestion/scripts/overlap_report.py`'s `exc` column. Not a contradiction — different chunking model, re-measured — but Amendment 2 never pointed to the update; noted here.

No DB or code change accompanies this correction — see `docs/DEVIATIONS.md` #DEV-035.
