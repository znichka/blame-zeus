# ADR-014: `passage_ref` Follows Standard Classical Citation Notation, Not Raw Scraped Markers

| Field        | Value       |
|--------------|-------------|
| **Date**     | 2026-07-13  |
| **Status**   | Accepted (applied 2026-07-13 — see Implementation Checklist) |

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
- [ ] `RagAgent` / `ConflictSynthesizer` (Stage 6, not yet built): when citation-rendering prompts/DTOs are written, format against this table (e.g. prefix with `Il.`/`Met.`/`Theog.` for user-facing display) rather than re-deriving a notation independently.
