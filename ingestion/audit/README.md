# `ingestion/audit/`

Data-quality checks over the extracted/seeded knowledge graph. Built in **Phase 2 Stage P2**
(Track G) as a standalone package; **becomes audit check `A3`** in Phase 3's `python -m audit`
runner (`docs/IMPLEMENTATION_PLAN_PHASE2.md §4.1`), which will add more checks alongside it.
Every check in this package **reports only** — none of them mutate any file or table. A human
(or a scripted fix loop) reads the findings and edits the source data.

## `cycle_check.py` — the DAG invariant

A genealogy is a directed acyclic graph: nothing is its own ancestor. `parent_of` edges that form
a cycle — a self-loop (`A parent_of A`), a 2-cycle (`A parent_of B` **and** `B parent_of A`), or a
longer loop — are a **near-certain reversed-direction edge** (occasionally a split/duplicated
entity instead, the Io/DEV-042 precedent; that class is flagged for Phase 3 entity-merge work, not
fixed here). This is the root cause behind `DEV-054`'s Q9/Q12 `serviceError`s
(`docs/TODO-phase2-stage-p2.md`): a recursive SQL query over a graph with a cycle either times out
or the model declines to emit unbounded recursion.

**The fix always lands at the candidate-JSON layer**, never as a query-time guard:

1. `python -m audit.cycle_check --candidates` (or `--db` to check what's actually seeded) —
   read-only, reports every cycle plus a machine-readable `findings.json`. Exits non-zero if any
   cycle is found.
2. Edit `ingestion/extraction/output/relationships_candidates_cleaned.json` — reverse or drop the
   offending edge, using `source_id` / `seedgen/canonical_edge.py`'s spine-priority order as the
   tie-breaker when sources disagree on direction.
3. `python -m seedgen --strict` to regenerate `V11__seed_relationships.sql`.
4. `scripts/reseed-local.sh --local-only` to re-apply it (see the checksum-trap note below).
5. `python -m audit.cycle_check --db` again — repeat until clean.

## The Flyway checksum trap (shared with Track F)

`scripts/reseed-local.sh` is the only sanctioned way to re-seed `V10`–`V14` after an edit here.
**Never** hand-edit an already-applied migration file and expect Flyway to notice — once applied,
Flyway checksums it, and regenerating the file changes that checksum. On your own local DB,
`reseed-local.sh` clears the relevant `flyway_schema_history` rows first, so this is fine. On a
**shared** database, doing this breaks `flyway validate` for everyone else pointed at it — which is
exactly why `reseed-local.sh` refuses to run without `--local-only` / `ALLOW_RESEED=1`. Never run
`docker compose down -v` as a shortcut either: it drops `narrative_chunks`, whose embeddings cost
real OpenAI API calls to regenerate.

## Design notes

- `find_cycles` (the pure core) is a DFS back-edge detector over the directed graph, deduped by a
  rotation-invariant signature of each cycle's node sequence. It reports **one representative
  cycle per strongly-connected component**, not every elementary cycle inside it — a tangled
  region with several overlapping reversed edges shows up as one (possibly long) reported chain.
  That's sufficient to flag "this area needs manual untangling"; exhaustive elementary-cycle
  enumeration (Johnson's algorithm) is left for Phase 3 if it turns out to matter.
- Filters to `relation == "parent_of"` by default; `--relation a,b` (or the `relations` param on
  `find_cycles`) widens it — Phase 3's `A3` is expected to check more relation types.
- Two readers share the same pure core: `load_from_candidates` (the editable source of truth a fix
  actually lands in) and `load_from_db` (the live, already-seeded graph, read via the read-only
  `zeus_app` user under the same `statement_timeout` guardrail `core-api` runs under) — running
  both confirms the seeded graph actually matches what's in the candidates file.
