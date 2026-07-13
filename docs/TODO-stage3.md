# Stage 3 — Full Corpus: Detailed Checklist

**Done when:** All 6 sources indexed in `narrative_chunks`; row count per source is non-zero;
per-source `passage_ref`s are real structural refs (not all falling back to `f"{author}, {work}"`).

> ⚠️ Formerly Stage 4 — renumbered per ADR-004 (see `TODO.md` Stage 2 note).

Before starting, re-read `DEVIATIONS.md`. Directly relevant here:
- **DEV-011** — the Apollodorus extractor regex had to be widened after QA against the *real*
  corpus file (Epitome `E.x.y` markers). Expect the same for every Stage 3 extractor: the plan's
  regexes (`IMPLEMENTATION_PLAN.md §4`, marker table) are **hypotheses about file formats the
  plan's author never inspected** — treat them as starting points, verify against the actual
  downloaded text, and log a DEV entry per widened regex.
- **DEV-024** — `store_chunks()` skips already-embedded chunks *before* the OpenAI call. A full
  re-run after adding 5 sources will print `Skipping 260 of 260…` for Apollodorus and embed only
  the new sources. This is correct behavior, not a bug.
- **DEV-027** — precedent for hand-inserting `sources` rows ahead of Stage 4's `V9` (gotcha #1 below).
- **DEV-028 / ADR-013** — embeddings are `text-embedding-3-large` (3072-dim); every inserted row is
  stamped with `embedding_model` from `config.EMBEDDING_MODEL`. No pipeline change needed in this
  stage. Cost note: the full remaining corpus is roughly ~550–700k tokens ≈ **well under $0.15**
  at -large pricing; expect roughly **1,500–3,000 new chunks** across the 5 sources.

---

## ⚠️ Gotcha #1 (repeat of Stage 2's): `validate_source_ids` needs all 6 `sources` rows

`main.py` fails fast unless every `SOURCE_REGISTRY.source_id` exists in `sources`. `V9__seed_sources.sql`
is still Stage 4 work. Per the DEV-027 precedent, hand-insert the 5 missing rows before Track F
(values must match `TODO-stage4.md` C1 exactly, including the DEV-018 author correction for the Hymns,
so V9's later `ON CONFLICT DO NOTHING` is a no-op):

```sql
INSERT INTO sources (id, author, work, translation, stance, year_published, role) VALUES
  ('hesiod-theogony',     'Hesiod',                 'Theogony',      'Evelyn-White', 'cosmological', 1914, 'spine'),
  ('hesiod-homeric-hymns','Anonymous ("Homeric")',  'Homeric Hymns', 'Evelyn-White', 'hymnic',       1914, 'primary'),
  ('homer-iliad',         'Homer',                  'Iliad',         'Murray',       'poetic-myth',  1924, 'spine'),
  ('homer-odyssey',       'Homer',                  'Odyssey',       'Murray',       'poetic-myth',  1919, 'primary'),
  ('ovid-metamorphoses',  'Ovid',                   'Metamorphoses', 'Brookes More', 'poetic-myth',  1922, 'selective')
ON CONFLICT (id) DO NOTHING;
```

`[DEVIATED - see DEVIATIONS.md #DEV-030]` — this template originally had Murray's Iliad/Odyssey
years swapped (same bug as DEV-029's `V9` placeholder) and an unfilled Ovid `<TRANSLATOR>`/`<YEAR>`;
corrected here to match `TODO-stage4.md` C1 before executing the insert.

**Sub-gotcha (latent plan bug this stage surfaces):** the plan's V9 row for Ovid
(`IMPLEMENTATION_PLAN.md §3` L140, `TODO-stage4.md` C1) says `translation='PD', year_published=null` —
but `V2__create_sources.sql` declares `year_published INTEGER NOT NULL` (and `TECH_GUARDRAILS.md`
explicitly forbids source rows without it). The row as planned **cannot be inserted**. Resolve in
Track A5 by picking a concrete public-domain translation with a real year, then update
`TODO-stage4.md` C1 to match and log a DEV entry. Log the whole hand-insert as a DEV entry too
(one entry can cover both, per the DEV-027 pattern).

## ⚠️ Gotcha #2 (critical, blocks Homer + Ovid refs): `text_cleaner` deletes the markers `[DEVIATED - see DEVIATIONS.md #DEV-029]`

`main.py` runs `clean()` **before** the extractor sees the text, and `text_cleaner.py`'s
`_PAGE_HEADER_LINE = r"^[A-Z\s]+$"` drops **every all-caps line**. But the plan's own marker table
(`IMPLEMENTATION_PLAN.md §4`) relies on all-caps lines as structural markers:

| Victim | Marker the extractor needs | Matches `^[A-Z\s]+$`? |
|---|---|---|
| Homer *Iliad*/*Odyssey* | `BOOK I`, `BOOK II`, … | **yes — deleted** |
| Ovid *Metamorphoses* | `BOOK I` + ALL-CAPS story titles (`THE CREATION`) | **yes — deleted** |
| Homeric Hymns | `HYMN I. TO DIONYSUS` | no (contains `.`) — but a header like `TO DEMETER` alone would be |

Left unfixed, `homer_refs`/`ovid_refs` receive text with no `BOOK` lines, emit nothing (or line refs
with no book context), and **every Homer/Ovid chunk silently falls back to `"Homer, Iliad"`-style
refs** — precisely the passage-level-provenance failure this project exists to avoid. Track B fixes
this **before** the extractors are verified end-to-end. Log the `clean()` signature change as a DEV
entry (it deviates from the plan's one-size-fits-all cleaner).

---

## Parallelization Guide

> ⚠️ **Stale as originally written.** This graph described the *planned* dependency shape
> (B/C/D as separately-gated, per-source-track work). DEV-029 (2026-07-13) replaced B, C, and
> D's entire planned approach with one consolidated implementation — see the status table below
> for what's actually true now, not the diagram's original arrows.

```
Track A1–A5 (corpus acquisition)        ✅ done
Track B  (text_cleaner marker fix)      ✅ done — DEV-029, different mechanism than planned
Track C1–C4 (extractors)                ✅ done — DEV-029 + ADR-014, different functions/notation than planned
Track D  (registry wiring)              ✅ done — DEV-029
Track E  (hand-insert sources rows)     ✅ done — DEV-030
Track F  (full ingestion run)           ⬜ ready — every dependency (A–E) is now satisfied
Track G  (verify + DEV log)             ⬜ depends on F
```

- **A1–A5, B, C1–C4, E** were mutually independent as planned (still true of A/E in isolation).
- **D depends on** all of C (real function objects) and A (final file names on disk) — satisfied:
  DEV-029 built C's function objects (under different names/shapes than planned, see below) and
  wired all 6 `SOURCE_REGISTRY` entries against A's real files.
- **F depends on** A, B, C, D, E — **all five are now satisfied** (A–D via DEV-029, E via DEV-030
  this session). Track F is unblocked and has not been run yet.
- **G depends on** F.

**Why B/C/D show done despite most of their sub-items below being unchecked:** DEV-029 solved
the same problems (markers surviving `clean()`, per-source ref extraction, registry wiring) with
a smaller, different implementation than these tracks specify — no `preserve_line` mechanism, and
3 extractor functions instead of 4 differently-named/shaped ones. The checkboxes below are left
as literal history of the original plan; each item is individually annotated with what actually
happened instead of being silently checked off for work that was never built as written.

---

## Track A — Corpus acquisition & preparation (manual, developer; 5 independent sub-tracks)

_Directory:_ `ingestion/corpus/` (gitignored — line 36 of `.gitignore`; keep it that way).
File names below are fixed by `IMPLEMENTATION_PLAN.md §4` — Track D's `file_path`s must match exactly.
Common steps for every sub-track: save as UTF-8; **strip Project Gutenberg boilerplate**
(everything up to and including `*** START OF THE PROJECT GUTENBERG EBOOK … ***` and everything
from `*** END OF …` onward — the license block would otherwise be chunked and embedded); QA like
Stage 2 B3 (no HTML tags/entities, no duplicated seams); **record the actual marker format** in a
scratch note for the matching C sub-track (bracketed `[ll. 1-25]` vs parenthesized `(ll. 1-25)`,
`BOOK I` vs `BOOK THE FIRST`, en-dash vs hyphen in ranges — the plan's regexes assume brackets and
Roman numerals; Gutenberg's Evelyn-White export is known to use **parentheses**, so expect deviations).

- [x] **A1** *Hesiod, Theogony* (Evelyn-White 1914) → `corpus/hesiod_theogony_evelynwhite1914.txt`
  - Source: Project Gutenberg #348 (*Hesiod, the Homeric Hymns, and Homerica*) or sacred-texts.
    **The Gutenberg volume is one file containing Theogony + Works and Days + Hymns + fragments —
    cut out the Theogony section only** (this sub-track and A2 likely share one download).
  - QA: line-group citations present (`(ll. 116-138)`-style); record bracket/paren style for C1.
- [x] **A2** *Homeric Hymns* (Evelyn-White 1914) → `corpus/hesiod_homeric_hymns_evelynwhite1914.txt`
  - Cut the Hymns section from the same volume as A1. Keep every hymn header line (`I. TO DIONYSUS` /
    `HYMN I. TO DIONYSUS` — record which form) **and** the line-group citations.
  - QA: count hymn headers (should be 33ish); check multi-word dedicatees exist (`TO PYTHIAN APOLLO`,
    `TO EARTH THE MOTHER OF ALL`) — the plan's `TO\s+(\w+)` captures one word only; C2 must handle this.
- [x] **A3** *Homer, Iliad* (Murray 1919) → `corpus/homer_iliad_murray1919.txt`
  - Murray's (Loeb) prose translation is **not** on Project Gutenberg — like Apollodorus/Frazer it
    lives on theoi.com (`theoi.com/Text/HomerIliad1.html` …, 24 books across pages). Manual copy
    per the Stage 2 B-track method. If that proves impractical, escalate: switching translator
    (e.g. Butler) changes the `sources` row (`translation`, `year_published`) → update Gotcha #1's
    insert + `TODO-stage4.md` C1 + DEV entry.
  - QA: `BOOK` headers or per-page book context present; line refs present; record exact formats for C3.
    Largest file of the stage (~1 MB) — spot-check 3 random mid-file locations, not just the ends.
- [x] **A4** *Homer, Odyssey* (Murray 1924) → `corpus/homer_odyssey_murray1924.txt` — same method,
      same QA as A3.
- [x] **A5** *Ovid, Metamorphoses* (public-domain translation) → `corpus/ovid_metamorphoses_pd.txt`
  - **Decision required first** (feeds Track E and `TODO-stage4.md` C1): pick a concrete PD
    translation — candidates: Brookes More 1922 (theoi.com, verse), Garth/Dryden et al. 1717
    (Gutenberg #26073, has book + story-title structure closest to the plan's assumed format),
    Golding 1567 (archaic; avoid). Record `translation` + `year_published` for the `sources` row
    (**`null` year is impossible** — see Gotcha #1 sub-gotcha).
  - QA: verify the edition actually has per-book markers and per-story titles/headers matching what
    C4 will extract; record exact formats. If the chosen edition has no usable story titles, the
    fallback granularity is book-level refs (`Book I`) — acceptable for a `selective`-role source;
    note it in the DEV entry.

---

## Track B — `text_cleaner.py`: stop deleting structural markers (Gotcha #2 fix) `[DEVIATED - see DEVIATIONS.md #DEV-029]`

_Directory:_ `ingestion/loader/`. Independent; TDD (tests first, per `TECH_GUARDRAILS.md`).

- [ ] **B1** `[N/A - see DEVIATIONS.md #DEV-029]` A `preserve_line`-parameterized test suite was
      never written — DEV-029 fixed marker survival with two regex changes instead (see B2). The
      goal this item was chasing (structural markers survive `clean()`, existing behavior stays
      correct) is covered by `test_text_cleaner.py`'s `test_leaves_bare_digit_line_start_markers_unchanged`,
      `test_strips_footnote_ref_attached_to_preceding_word`, and
      `test_preserves_all_caps_section_titles_after_first_structural_marker`.
- [ ] **B2** `[N/A - see DEVIATIONS.md #DEV-029]` No `preserve_line` parameter was added — `clean()`'s
      signature is unchanged from Stage 2. DEV-029 fixed the actual root causes instead:
      `_FOOTNOTE_MARKER` gained a `(?<=\S)` lookbehind (only strips brackets glued to a preceding
      word, sparing line-initial `[N]` markers), and `_PAGE_HEADER_LINE` stripping was scoped to
      the metadata preamble before the first structural marker (so in-body ALL-CAPS section titles
      survive). Apollodorus's 260 stored chunks are confirmed unaffected (its dotted markers never
      matched either regex before or after).
- [ ] **B3** `[N/A - see DEVIATIONS.md #DEV-029]` No `preserve_line` field exists on `SourceConfig` —
      B2 made it unnecessary. D2/D3 (which depend on this item) are N/A for the same reason.
- [x] **B4** Logged — `docs/DEVIATIONS.md` #DEV-029 (content differs from what B4 anticipated: it
      documents the regex-fix approach above, not a `SourceConfig`/`main.py` signature change).

---

## Track C — Passage-ref extractors (4 independent sub-tracks; TDD) `[DEVIATED - see DEVIATIONS.md #DEV-029]`

_Directory:_ `ingestion/loader/source_registry.py` (co-located with `apollodorus_refs`).
All return `list[tuple[int, str]]` sorted ascending, same `Callable` shape as Stage 2. Write
fixture tests first in `test_passage_ref_extractors.py` from the plan's marker table; the final
item of each sub-track re-verifies against the real file from Track A and widens the regex if
needed (**each widening = DEV entry**, per DEV-011). Shared test cases for every extractor:
bare footnote `[3]` emits nothing; text before first marker → chunker fallback (tested in
chunker tests, not here); OCR-noise spacing variants; en-dash `–` and hyphen `-` in ranges.

> `[N/A - see DEVIATIONS.md #DEV-029, ADR-014]` **None of C1–C4 below were built as written.**
> The real corpus uses bare `[N]` line markers everywhere (no `[ll. N-M]` ranges, no en-dashes,
> no Ovid story titles to key off), which made this track's four range/title-parsing functions
> moot. DEV-029 built three functions instead — `hesiod_theogony_refs` (replaces C1, no book
> division), `hesiod_homeric_hymns_refs` (replaces C2, `"{hymn}.{line}"`), `book_line_refs`
> (replaces C3 **and** C4 — shared by Iliad/Odyssey/Ovid, `"{book}.{line}"`, no story-title
> granularity for Ovid) — emitting the standard classical citation notation ADR-014 formalizes,
> not the `"ll. 116-138"` / `"Hymn I (To Dionysus) ll. 1-21"` / `"Book I: The Creation"` shapes
> below. Tests live in `test_passage_ref_extractors.py`'s DEV-029 section; verification against
> all 6 real corpus files is recorded in DEV-029's dry-run ref counts (Apollodorus 386, Theogony
> 85, Hymns 166, Iliad 1138, Odyssey 882, Ovid 669 — all within each work's known real extent).
> Sub-items below are left unchecked as a record of the original plan, not pending work.

- [ ] **C1** `hesiod_refs` — line citations `[ll. 116-138]` (plan regex
      `r'\[ll?\.\s*(\d+(?:[–\-]\d+)?)\]'`) → ref `"ll. 116-138"`.
  - [ ] C1a tests: bracketed range, single line `[l. 1]`, en-dash range, `(ll. 1-25)`
        **parenthesized variant expected from Gutenberg** — decide bracket-or-paren after A1's QA
        and encode whichever the real file uses (widen to accept both if harmless).
  - [ ] C1b implement; C1c verify against real A1 file: ref count > 0, ascending, no duplicates.
- [ ] **C2** `hymn_refs` — stateful like the plan's `homer_refs` sketch: hymn header sets context
      (`HYMN I. TO DIONYSUS` or `I. TO DIONYSUS`), line citations emit
      `"Hymn I (To Dionysus) ll. 1-21"`.
  - [ ] C2a tests: header+lines composition; **multi-word dedicatee** (`TO PYTHIAN APOLLO` — the
        plan's `TO\s+(\w+)` is too narrow, use `TO\s+([A-Z][A-Z\s]+?)\s*$`-style capture and
        title-case it); second hymn header resets context; line ref before any header → no emission.
  - [ ] C2b implement; C2c verify against real A2 file: every hymn header found (count matches A2's
        QA count), refs ascending.
- [ ] **C3** `homer_refs` — the plan gives a full reference implementation
      (`IMPLEMENTATION_PLAN.md §4`): `BOOK ([IVXLCDM]+)` sets context, `[ll?. N(-M)?]` emits
      `"Book I ll. 1-7"`. Shared by Iliad and Odyssey (one function, two registry entries).
  - [ ] C3a tests: book header + line refs; book rollover (`BOOK II` resets); line ref before any
        `BOOK` → no emission; Roman numerals through `XXIV`.
  - [ ] C3b implement (adapt marker forms to A3/A4's recorded reality — Theoi's Murray pages may
        carry per-page headers instead of inline `BOOK` lines; if so the prep step in A3/A4 must
        insert `BOOK N` separator lines manually and note it in the DEV entry).
  - [ ] C3c verify against both real files: >0 refs per book for all 24 books of each poem
        (a missing book ⇒ a seam error in A3/A4's page concatenation — this check catches it).
- [ ] **C4** `ovid_refs` — stateful: `BOOK ([IVXLCDM]+)` (or the edition's actual book-header form)
      sets context; ALL-CAPS story-title line (plan: `r'^([A-Z][A-Z\s]{4,})\s*$'`) emits
      `"Book I: The Creation"` (title-cased).
  - [ ] C4a tests: book + story composition; story before any book → no emission; a `BOOK I` line
        itself must **not** also match the story-title regex (it does match `[A-Z\s]{4,}` — exclude
        lines starting with `BOOK`); title-casing.
  - [ ] C4b implement per A5's recorded format; C4c verify against real file: stories per book > 0
        for all 15 books, refs ascending. If A5 chose book-level-only granularity, C4 reduces to the
        book half — reflect that in the tests, not just the code.

---

## Track D — `source_registry.py` wiring `[DEVIATED - see DEVIATIONS.md #DEV-029]`

_Depends on:_ C (real function objects), A (file names exist on disk), ~~B3 (`preserve_line` field)~~
`[N/A - see DEVIATIONS.md #DEV-029]` — no `preserve_line` field exists (B3 was never built; D
doesn't need it).

- [x] **D1** Done, via DEV-029's extractors instead of Track C's planned ones: all 6
      `SOURCE_REGISTRY` entries present in `ingestion/loader/source_registry.py`, slugs/authors/works
      matching `TODO-stage4.md` C1 (incl. DEV-018's `Anonymous ("Homeric")`), `file_path`s matching
      the real files on disk, extractors = `apollodorus_refs` / `hesiod_theogony_refs` /
      `hesiod_homeric_hymns_refs` / `book_line_refs` (shared by both Homer entries and Ovid).
- [ ] **D2** `[N/A - see DEVIATIONS.md #DEV-029]` No `preserve_line` mechanism exists — moot.
- [ ] **D3** `[N/A - see DEVIATIONS.md #DEV-029]` `main.py` has no `preserve_line` pass-through to add.
- [x] **D4** Ran the sanity pass (2026-07-13): `clean()` → `extractor()` on all 6 real files —
      `apollodorus-bibliotheca: (386, '1.1.1', 'E.7.40')`, `hesiod-theogony: (85, '1', '1021')`,
      `hesiod-homeric-hymns: (166, '1.1', '33.1')`, `homer-iliad: (1138, '1.1', '24.788')`,
      `homer-odyssey: (882, '1.1', '24.545')`, `ovid-metamorphoses: (669, '1.1', '15.871')`. Every
      source has the extractor its file format needs, no cross-wiring, all ranges sane.

---

## Track E — `sources` rows hand-insert `[DEVIATED - see DEVIATIONS.md #DEV-030]`

_Depends on:_ running Postgres container; A5's translator/year decision. Independent of B/C/D.

- [x] **E1** Apply Gotcha #1's `INSERT` via `docker exec blame-zeus-postgres-1 psql -U zeus -d blamezeus`
      (fill in the Ovid `<TRANSLATOR>`/`<YEAR>` from A5). Verify: `SELECT id FROM sources ORDER BY id;`
      returns all 6 slugs.
- [x] **E2** Update `TODO-stage4.md` C1: the Ovid row's concrete translation/year (replacing
      `PD`/`null`), and note that V9 must reproduce **exactly** these 6 rows (its
      `ON CONFLICT DO NOTHING` then no-ops against the hand-inserted ones). Add the stance values
      used here so V9 doesn't have to re-derive them.

---

## Track F — Full ingestion run

_Depends on:_ A, B, C, D, E. Sequential from here.

- [ ] **F1** `pytest ingestion/tests/` — everything green before spending tokens.
- [ ] **F2** `cd ingestion && python main.py` (env via `.env`/`load_dotenv`, `EMBEDDING_MODEL=text-embedding-3-large`
      already set since DEV-028). Expected console shape: `Skipping 260 of 260…` for Apollodorus,
      then batch-committed inserts for the 5 new sources. On a mid-run crash: just re-run — DEV-024's
      skip-before-embed + `ON CONFLICT DO NOTHING` make it resumable at batch granularity.

---

## Track G — Verification + deviation logging (run last)

- [ ] **G1** Per-source row counts, all non-zero (the stage's Done-when):
      `SELECT source_id, count(*) FROM narrative_chunks GROUP BY source_id ORDER BY 1;` — 6 rows.
      Sanity-check magnitudes: Iliad/Odyssey/Ovid each ≫ Theogony (a tiny count for a big source ⇒
      truncated corpus file).
- [ ] **G2** Fallback-ref audit per source. `[DEVIATED - see DEVIATIONS.md #DEV-029, ADR-014]` —
      the query below replaces the original, which checked for `'.'`/`'ll.'`/`'book'`/`'hymn'`
      substrings; that check is now **wrong**, because Theogony's real refs (bare line numbers like
      `"116"`) contain none of those and would all be false-flagged as fallbacks. The real fallback
      shape is `f"{author}, {work}"` (a comma, no digits), which is distinguishable from every
      source's real notation (ADR-014) via a per-source numeric-shape check instead:
      ```sql
      SELECT source_id,
             count(*) FILTER (WHERE
               (source_id = 'apollodorus-bibliotheca' AND passage_ref !~ '^[0-9E]+(\.[0-9]+){2}$') OR
               (source_id = 'hesiod-theogony'         AND passage_ref !~ '^[0-9]+$') OR
               (source_id IN ('hesiod-homeric-hymns', 'homer-iliad', 'homer-odyssey', 'ovid-metamorphoses')
                                                       AND passage_ref !~ '^[0-9]+\.[0-9]+$')
             ) AS suspicious,
             count(*)
      FROM narrative_chunks GROUP BY source_id;
      ```
      — near-zero `suspicious` expected (only text before each file's first marker falls back).
      A high count ⇒ Gotcha #2 regression or an extractor miss.
- [ ] **G3** Spot-check 3 refs per new source against the actual text (does chunk content really
      belong to the ref shown, e.g. `"1.194"` for Iliad book 1 line 194 — see ADR-014's notation
      table) — passage-level provenance is the product's core claim; verify it, don't assume it.
- [ ] **G4** Idempotency + Apollodorus immutability: re-run `python main.py` → `Skipping N of N…`
      for **all 6** sources, total row count unchanged, and Apollodorus still exactly 260 rows
      (proves B2 kept its cleaning byte-identical — if this fails, `clear_source_chunks(conn, 'apollodorus-bibliotheca')`
      + re-embed once, and log it).
- [ ] **G5** Embedding hygiene: `SELECT count(DISTINCT embedding_model), min(embedding_model) FROM narrative_chunks;`
      → `1 | text-embedding-3-large`. Re-run the `EXPLAIN` halfvec check from ADR-013 — at a few
      thousand rows the planner may now choose `narrative_chunks_embedding_hnsw_idx` without
      `enable_seqscan=off`; either way the plan must show the index is *usable* (Index Scan when
      seq scan is disabled).
- [ ] **G6** Log DEV entries per `CLAUDE.md` protocol (append-only, next free DEV-NNN):
      the Gotcha #1 hand-insert incl. the Ovid `year_published NOT NULL` resolution; the Gotcha #2
      `clean()`/`SourceConfig` change (B4, may fold into one entry with D2/D3); one entry per
      extractor-regex widening from C1c/C2c/C3c/C4c; mark affected TODO items inline and add the
      stage banner to `IMPLEMENTATION_PLAN.md §4` if its assumptions changed.
- [ ] **G7** Tick off the Stage 3 summary items in `TODO.md` (and cross-link this file from there).
