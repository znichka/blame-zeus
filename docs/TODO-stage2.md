# Stage 2 — Ingestion Setup (Apollodorus only): Detailed Checklist

**Done when:** `python main.py` ingests Apollodorus .txt without error; rows appear in
`narrative_chunks` with correct `source_id`, `passage_ref`, and non-null `embedding`.

> ⚠️ Stage order changed by ADR-004 (`docs/adr/adr-004-seed-data-extraction-strategy.md`):
> ingestion now runs before seed data (formerly Stage 2, now Stage 4), since the extraction
> pipeline needs real ingested corpus text to run against. This stage was formerly numbered
> Stage 3.

Before starting, re-read `DEVIATIONS.md`. DEV-004 (LangChain4j beta5) and DEV-008/DEV-009
(Testcontainers/springdoc) are JVM-only and out of scope for the pure-Python `ingestion/`
package. **DEV-015 (ADR-008 + ADR-006 companion) touched this stage's code post-hoc:**
`config.py` now hard-requires the `EMBEDDING_MODEL` env var and `embedding_pipeline.py`
embeds with `config.EMBEDDING_MODEL` instead of a hardcoded literal (ADR-006 §1) — the
still-open Tracks H/I must run with `EMBEDDING_MODEL=text-embedding-3-small` set (present
in `.env.example`).

## ⚠️ Known ordering gotcha: `validate_source_ids` vs. Stage 4's `V9__seed_sources.sql`

`main.py`'s `validate_source_ids()` raises `RuntimeError` if `'apollodorus-bibliotheca'` is not
already a row in the `sources` table — but per the plan's renumbering, the migration that seeds
`sources` (`V9`) lives in **Stage 4**, which runs *after* this stage. Running `python main.py`
against a freshly-migrated (V1–V8 only) database will fail fast on this check by design.

Resolve this **before Track I verification** by hand-inserting a minimal row so Stage 2 can be
verified standalone, without pulling all of V9 forward:

```sql
INSERT INTO sources (id, author, work, translation, stance, year_published, role)
VALUES ('apollodorus-bibliotheca', 'Apollodorus', 'Bibliotheca', 'Frazer', 'mythographic-handbook', 1921, 'spine')
ON CONFLICT (id) DO NOTHING;
```

`V9` (Stage 4) will later insert the same row with `ON CONFLICT DO NOTHING`, so this is
idempotent and requires no cleanup. Log this as a deviation (`DEV-0NN`) when Stage 2 is actually
implemented, per `CLAUDE.md`'s Deviation Tracking Protocol — this file only flags the gotcha.

## Parallelization Guide

```
Track A (Python scaffold)      ─┐
Track B (corpus acquisition)    │
Track C (text_cleaner)          │
Track D (passage ref extractor) ├─→ Track F (source_registry) ─┐
Track E (text_chunker)          │                               ├─→ Track H (main.py) ─→ Track I (verify)
Track G (embedding_pipeline)   ─┘                               │
Track B (corpus file) ───────────────────────────────────────────┘
```

- **A, B, C, D, E, G have no dependency on each other** — start all six in parallel immediately.
  - E's tests use inline fixture extractors (per `IMPLEMENTATION_PLAN.md §8`), so it does not
    need D's real implementation to be written first — only the shared `Callable[[str],
    list[tuple[int, str]]]` type shape, which is already fixed by the plan.
- **F depends on D** — `SOURCE_REGISTRY` wires in the real `apollodorus_refs` function object.
- **H (`main.py`) depends on A, C, E, F, G** — it imports and sequences all of them.
- **I depends on H** (working pipeline) **and B** (the corpus .txt file must exist on disk) —
  and on the ordering gotcha above being resolved.

---

## Track A — Python project scaffold

_Directory:_ `ingestion/`. No dependency on anything else in this stage.

- [x] **A1** `ingestion/requirements.txt` — `openai>=1.0`, `psycopg2-binary`, `pgvector`,
      `tenacity>=8.2`, `python-dotenv`, plus `pytest>=8.0` for the test track
- [x] **A2** Decide `pyproject.toml` vs. `requirements.txt`-only (plan allows either) — if
      skipping `pyproject.toml`, note the decision inline in `requirements.txt`'s header comment
- [x] **A3** Create venv (`python3.12 -m venv .venv`) and `pip install -r requirements.txt`
      `[DEVIATED - see DEVIATIONS.md #DEV-010]` — python3.12 is not installed on the dev
      machine; used Homebrew's `python@3.14` instead (satisfies "Python 3.12+")
- [x] **A4** `ingestion/config.py` — reads env vars via `python-dotenv`: `OPENAI_API_KEY`,
      `POSTGRES_USER`, `POSTGRES_PASSWORD`, `POSTGRES_DB` (all already in `.env.example` from
      Stage 1b). *(Amended post-hoc per ADR-006/DEV-015: `config.py` now also reads
      `EMBEDDING_MODEL` — required, no default, single source of truth shared with core-api.)*
      **Gap:** `.env.example` has no `POSTGRES_HOST`/`POSTGRES_PORT` — add both with
      `localhost`/`5432` defaults in `config.py` (ingestion runs from the host, connecting to the
      Dockerized Postgres via its published port, not from inside the compose network)
  - Use `POSTGRES_USER`/`POSTGRES_PASSWORD` (superuser), **not** `POSTGRES_APP_USER` —
    `zeus_app` is `SELECT`-only (`docker/init/01_readonly_user.sql`, Stage 1b) and cannot
    `INSERT` into `narrative_chunks`
- [x] **A5** `ingestion/tests/__init__.py` (empty, makes the dir a package for pytest discovery)
- [x] **A6** Confirm `ingestion/.venv/` (or wherever the venv lands) is `.gitignore`d

---

## Track B — Corpus acquisition (manual, developer)

_No code dependency — can start immediately, in parallel with everything else._

- [x] **B1** Open `theoi.com/Text/Apollodorus1.html`, `Apollodorus2.html`, `Apollodorus3.html`,
      `ApollodorusE.html` (the Epitome) — copy Frazer's 1921 translation text from all four pages
      in order
- [x] **B2** Concatenate into `ingestion/corpus/apollodorus_bibliotheca_frazer1921.txt`,
      preserving the bracketed `[book.chapter.section]` markers exactly as Theoi presents them
      (needed by `apollodorus_refs` in Track D)
- [x] **B3** Manual QA pass: confirm no leftover HTML tags/entities, markers are intact and in
      ascending order, no duplicated page content at the page-boundary seams
  - Verified: zero HTML tags/entities (`<...>` matches are Frazer's own editorial notation,
    e.g. `<after himself>`, not markup); 386 `[book.chapter.section]`/`[E.x.x]` markers,
    strictly ascending, zero duplicates; all 3 book-transition seams inspected manually — each
    ends in Apollodorus's own narrative transition sentence, no repeated content

---

## Track C — `text_cleaner.py`

_Directory:_ `ingestion/loader/`. Independent — pure string transform, testable on inline fixtures.

- [x] **C1** `clean(text: str) -> str` — strip footnote markers with
      `re.sub(r'\[\d+\]', '', text)` (digits-only, so it never touches
      `[book.chapter.section]` markers, which contain dots)
- [x] **C2** Collapse multi-whitespace, normalize smart quotes (`'`/`'` → `'`, `"`/`"` → `"`)
- [x] **C3** Strip page headers/running titles (lines matching `^[A-Z\s]+$` alone on a line)
- [x] **C4** `ingestion/tests/test_text_cleaner.py` — assert `[1]`/`[42]` stripped; smart quotes
      normalized; multi-whitespace collapsed; assert a `[1.1.1]`-style marker survives unchanged
      (also covers `[E.1.1]` Epitome-style markers) — 8 tests, all passing; spot-checked against
      the full real corpus file too

---

## Track D — Passage reference extractor (Apollodorus)

_Directory:_ `ingestion/loader/source_registry.py` (or a co-located module). Independent — pure
regex over inline fixtures.

- [x] **D1** `apollodorus_refs(text: str) -> list[tuple[int, str]]` —
      `r'(?m)^\s*\[?(\d+\.\s*\d+\.\s*\d+)\]?'`, returns `(offset, ref)` pairs sorted ascending
      `[DEVIATED - see DEVIATIONS.md #DEV-011]` — regex widened to
      `r'(?m)^\s*\[?((?:E|\d+)\.\s*\d+\.\s*\d+)\]?'` so Frazer's Epitome (`[E.1.1]`-style)
      markers are also matched; verified against the real corpus: 386 refs total (209 numeric +
      177 `E.x.y`), strictly ascending, zero duplicates
- [x] **D2** `ingestion/tests/test_passage_ref_extractors.py` (Apollodorus cases only — this
      stage seeds only the one source; Stage 3 adds `homer_refs`/`ovid_refs`/etc.):
  - Clean fixture `"[1.1.1]"`, `"[1.2.3]"` → offsets + bracket-free captured group (`"1.1.1"`)
  - Unbracketed variant `"1.1.1"` → same ref still extracted (brackets optional in regex)
  - OCR-noise fixture `"[1. 1. 1]"` (extra spaces) → same ref still extracted
  - Bare footnote marker `"[3]"` (single integer, no dots) → **no** entry emitted — must not be
    confused with a passage ref
  - Fixture with text before the first marker → extractor returns `None` for that offset
    (the `f"{author}, {work}"` fallback is tested in `test_text_chunker.py`, not here)
  - Additional cases added per DEV-011: `"[E.1.1]"` and OCR-noise `"[E. 1. 1]"` Epitome markers
    also extracted correctly
  - 7 + 2 = 9 tests, all passing; spot-checked end-to-end (`clean()` → `apollodorus_refs()`)
    against the full real corpus file

---

## Track E — `text_chunker.py`

_Directory:_ `ingestion/chunker/`. Tests use an inline fixture extractor, so this does not block
on Track D's real implementation — only on the shared `Callable` signature already fixed by the
plan.

- [x] **E1** `Chunk` dataclass — `text`, `source_id`, `passage_ref`, `author`, `work`,
      `start_offset: int`
- [x] **E2** `split_sentences(text: str) -> list[tuple[int, str]]` — regex `(?<=[.!?])\s+`
      sentence boundary split, returns `(char_offset, sentence_text)` pairs
- [x] **E3** `chunk(text, source_id, author, work, extractor) -> list[Chunk]` — accumulate
      sentences to `CHUNK_SIZE=1500` chars, roll back `OVERLAP_SENTENCES=2` for the next chunk's
      start `[DEVIATED - see DEVIATIONS.md #DEV-012]` — the plan's literal loop hangs forever
      once the tail of a document has ≤`OVERLAP_SENTENCES` sentences left, and separately lets a
      chunk overshoot `CHUNK_SIZE` unboundedly; both fixed (loop now breaks once sentences are
      exhausted, rollback is clamped to `min(OVERLAP_SENTENCES, len(buf)-1)`, and the inner loop
      stops *before* a sentence would push the chunk past `CHUNK_SIZE` rather than after)
- [x] **E4** `_nearest_ref(refs, pos) -> str | None` — last ref with `offset <= pos`; falls back
      to `f"{author}, {work}"` in `chunk()` when `None`
- [x] **E5** `ingestion/tests/test_text_chunker.py`:
  - No chunk exceeds `CHUNK_SIZE * 1.2` characters
  - Last `OVERLAP_SENTENCES` sentences of chunk N appear verbatim at the start of chunk N+1
  - `passage_ref` on each chunk matches the nearest preceding marker in the input (use an inline
    fixture extractor here, independent of Track D)
  - Running `chunk()` twice on identical input produces identical `(chunk_text, passage_ref)`
    tuples per chunk (determinism — required for `ON CONFLICT DO NOTHING` re-run safety)
  - Fallback case: text before the first marker → chunk gets `f"{author}, {work}"` as
    `passage_ref`
  - Two regression tests added per DEV-012 (tail-exactly-overlap-sentences-left,
    single-sentence-exceeds-CHUNK_SIZE) — 8 tests total, all passing; verified end-to-end
    against the real corpus (260 chunks, max size 1508 chars, deterministic, zero fallback refs
    needed since `[1.1.1]` starts at offset 0)

---

## Track F — `source_registry.py`

_Directory:_ `ingestion/loader/source_registry.py`. _Depends on:_ Track D (needs the real
`apollodorus_refs` function object, not a stub).

- [x] **F1** `SourceConfig` dataclass — `source_id: str`, `author: str`, `work: str`,
      `file_path: str`, `passage_ref_extractor: Callable[[str], list[tuple[int, str]]]`
- [x] **F2** `SOURCE_REGISTRY: list[SourceConfig]` — single Apollodorus entry:
      `source_id='apollodorus-bibliotheca'`, `file_path='corpus/apollodorus_bibliotheca_frazer1921.txt'`,
      `passage_ref_extractor=apollodorus_refs`
  - Confirmed `source_id`/`author`/`work` match the hand-insert in the ordering-gotcha note
    above exactly (`'apollodorus-bibliotheca'`, `'Apollodorus'`, `'Bibliotheca'`); will need the
    same check against `V9__seed_sources.sql` once Stage 4 writes it
  - Verified `file_path` resolves relative to `ingestion/` and the file exists on disk

---

## Track G — `embedding_pipeline.py`

_Directory:_ `ingestion/pipeline/`. Independent of C/D/E/F — only needs Track A's dependencies
installed.

- [x] **G1** `embed_batch(texts: list[str]) -> list[list[float]]` — `OpenAI().embeddings.create(model="text-embedding-3-small", input=texts)`; `@retry` (tenacity: `wait_exponential(multiplier=1, min=2, max=60)`, `stop_after_attempt(5)`, `reraise=True`)
      — retry behavior verified with a mocked client (2 simulated transient failures, succeeded
      on 3rd attempt) *(amended post-hoc per ADR-006/DEV-015: the model name now comes from
      `config.EMBEDDING_MODEL`, not the hardcoded literal)*
- [x] **G2** `store_chunks(conn, chunks)` — `register_vector(conn)`; batch size 20 chunks per
      `embed_batch` call; `INSERT ... ON CONFLICT (source_id, passage_ref, content_hash) DO
      NOTHING`; `metadata` JSONB includes `source_id`, `author`, `work`, `passage_ref`,
      `chunk_size`, `overlap_sentences` `[DEVIATED - see DEVIATIONS.md #DEV-013]` — the plan's
      literal snippet had no batching loop at all (called `embed_batch` once on the whole
      `chunks` list) despite its own prose requiring batches of 20; added the loop. Also dropped
      `numpy`/`np.array()` (never in `requirements.txt`; `pgvector`'s `Vector` already accepts a
      plain `list[float]` directly). Verified with a mocked DB connection + mocked `embed_batch`:
      45 synthetic chunks → 3 calls of `[20, 20, 5]`; correct SQL/metadata per row
- [x] **G3** `validate_source_ids(conn, registry)` — `SELECT id FROM sources`; raise
      `RuntimeError` listing any `SOURCE_REGISTRY` entry whose `source_id` isn't present (this is
      the check the ordering-gotcha note above exists to satisfy) — verified with a mocked
      connection for both the present and missing cases
- [x] **G4** `clear_source_chunks(conn, source_id)` — manual utility, `DELETE FROM
      narrative_chunks WHERE source_id = %s`; not called from `main.py`'s normal path
      (`source_id` type hint corrected from the plan's stray `int` to `str`, matching
      `SourceConfig.source_id: str` and the TEXT-slug schema) — verified with a mocked connection
- [x] **G5** Import block includes `from tenacity import retry, stop_after_attempt,
      wait_exponential` at the top of the module

---

## Track H — `main.py` (integration)

_Depends on:_ A, C, E, F, G. This is the wiring step — no new logic, just sequencing.

- [x] **H1** `load_dotenv()` called **before** any `from config import ...` — Python evaluates
      top-level imports at parse time, so importing `config` first would read unset env vars
- [x] **H2** `psycopg2.connect(...)` using `config.py`'s values (Track A4)
- [x] **H3** `validate_source_ids(conn, SOURCE_REGISTRY)` — fail fast before any file I/O or API
      calls
- [x] **H4** Loop over `SOURCE_REGISTRY`: read `file_path` → `clean()` (Track C) → `chunk()`
      (Track E) → `store_chunks()` (Track G)
- [x] **H5** `conn.close()` on completion

---

## Track I — Verification (sequential, run last)

_Depends on:_ Track H (working pipeline), Track B (corpus file on disk), and the ordering gotcha
resolved.

- [x] **I1** `pytest ingestion/tests/` — all of `test_text_cleaner.py`, `test_text_chunker.py`,
      `test_passage_ref_extractors.py` pass — 31 tests, all passing
- [x] **I2** Apply the hand-insert `INSERT INTO sources (...) VALUES ('apollodorus-bibliotheca',
      ...)` from the ordering-gotcha note (or otherwise confirm the row exists) — applied via
      `docker exec blame-zeus-postgres-1 psql`; row confirmed present
- [x] **I3** `cd ingestion && OPENAI_API_KEY=... EMBEDDING_MODEL=text-embedding-3-small
      POSTGRES_HOST=localhost python main.py` — completes without error (`EMBEDDING_MODEL` is
      required by `config.py` since ADR-006/DEV-015; `load_dotenv()` can also supply it from
      `.env`) — ran via `.env`-sourced `load_dotenv()`, no manual env prefix needed; first attempt
      hit `openai.RateLimitError: insufficient_quota` (account billing, zero rows written), retry
      after quota was resolved completed cleanly
      *(Historical note: this run used `text-embedding-3-small` as planned; the corpus was
      subsequently re-embedded with `text-embedding-3-large` per ADR-013/DEV-028 — see
      DEVIATIONS.md. The verification itself remains valid.)*
- [x] **I4** `psql -U zeus -d blamezeus -c "SELECT count(*) FROM narrative_chunks WHERE
      source_id='apollodorus-bibliotheca'"` — non-zero — 260 rows
- [x] **I5** `psql -U zeus -d blamezeus -c "SELECT passage_ref, embedding IS NOT NULL AS has_embedding FROM narrative_chunks WHERE source_id='apollodorus-bibliotheca' LIMIT 5"` — `passage_ref`
      values look like real `[book.chapter.section]` refs (not all falling back to
      `"Apollodorus, Bibliotheca"`); `has_embedding` is `true` for all rows — confirmed: 0 rows
      with `embedding IS NULL`, 0 rows fell back to `"Apollodorus, Bibliotheca"`
- [x] **I6** Re-run `python main.py` a second time — no duplicate rows (`ON CONFLICT DO NOTHING`
      + chunker determinism from E5 holds) — `Skipping 260 of 260 chunks already embedded`, count
      unchanged at 260
- [x] **I7** Log the ordering-gotcha resolution as a deviation entry in `DEVIATIONS.md` per
      `CLAUDE.md`'s Deviation Tracking Protocol — logged as DEV-027
