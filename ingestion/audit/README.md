# `ingestion/audit/`

Data-quality checks over the extracted/seeded knowledge graph. Built in **Phase 2 Stage P2**
(Track G) as a standalone package; now hosts Phase 3's `python -m audit` runner
(`docs/IMPLEMENTATION_PLAN_PHASE2.md §4.1`, `docs/TODO-phase2-stage-p3.md` Track A
`[DEVIATED - see DEVIATIONS.md #DEV-070]`), which auto-discovers and aggregates every check.
Every check in this package **reports only** — none of them mutate any file or table. A human
(or a scripted fix loop) reads the findings and edits the source data.

## `python -m audit` — the aggregate runner

`__main__.py` walks the package for any sibling module exposing the contract in `contract.py`
(module-level `NAME: str` + `run(candidates_dir, db_conn) -> CheckResult`) — a module needs no
separate registration call, just those two names, to be picked up. Today that's just
**`cycle_check.py` (check `A3`)**, via the thin `NAME`/`run` adapter added around its unedited
`find_cycles` core; **A1/A2/A4/A5** (duplicate-entity detection, candidate-drop accounting,
relation-label taxonomy, alias/participant integrity) are Phase 3 Tracks B–E, not yet built.

```
python -m audit                    # both sources (default): candidate JSON + a live DB connection
python -m audit --candidates       # candidate JSON only, no DB connection opened
python -m audit --db               # live DB only (via the read-only zeus_app user)
python -m audit --only A3          # run exactly one check by NAME
```

Exits non-zero if any **un-waived** finding survives — this is the standing **pre-seedgen gate**
(`docs/TODO-phase2-stage-p3.md` Track I): no batch of candidate-JSON edits reaches a commit
except through a `seedgen --strict` → `reseed-local.sh` → `python -m audit` (clean or waived)
→ eval → `compare.py` cycle.

Each run writes two artifacts to `reports/` (default; `--out` overrides):
- **`<date>-findings.json`** — every check's `Finding`s in one machine-readable shape (`check`,
  `severity`, `subject`, `detail`, `suggestedFix`, `waived`, `waiverReason`). This is **additive,
  not a replacement** for the committed `findings-candidates.json` / `findings-db.json` snapshots
  from DEV-066 — those are one-off, manually-run artifacts in `cycle_check`'s own shape; the
  standalone `python -m audit.cycle_check` CLI (still present, unchanged) keeps producing that
  shape for direct/manual use, while the aggregate JSON here carries every check uniformly.
- **`<date>.md`** — a human report: one `## <CHECK> — PASS|FINDINGS|WAIVED` section per check with
  a findings table, plus a top-line summary count. This is the file a reviewer reads before a fix
  batch (per the P3 exit: "all five checks clean **or** explicitly waived with a note").

**Waivers** (`audit-waivers.json`, `--waivers` to override the path): a list of
`{"check", "subject", "reason"}` objects. A waiver **requires** a non-empty `reason` — `load_waivers`
raises if one is missing. A waived finding still appears in the report/findings JSON (marked
`waived: true` with its reason) but does not fail the run's exit code — this is exactly the "clean
or waived with a note" mechanism the P3 exit criteria call for (e.g. DEV-069's Q9 Chaos/Ouranos gap,
if deferred to P5b, gets a waiver entry here rather than a silently-ignored finding).

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
