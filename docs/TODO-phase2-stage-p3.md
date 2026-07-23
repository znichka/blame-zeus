# Stage P3 — Data audit & relation canonicalization: Detailed Checklist

**Done when:** (1) `python -m audit` runs end-to-end read-only over candidate JSON + the live DB and
emits `ingestion/audit/reports/<date>.md` plus machine-readable findings JSON, with **all five checks
(A1–A5)** registered and either **clean or explicitly waived with a written note**; (2) the two
documented backlogs are triaged to completion — the **29** `entities_fuzzy_duplicates_flagged_for_review.json`
pairs (merge-at-candidate-layer + alias, or reject-with-note) and the **203**
`relationships_flagged_for_review.json` rows (promote-with-fix or reject, recorded in the file); (3) the
**two P2 carry-over backlogs** are resolved or explicitly deferred with a note — DEV-068's 3
entity-conflation `parent_of` cycles and DEV-069's Q9 `Chaos`/`Ouranos` lineage gap; (4)
`relation_aliases` is **live** (new Flyway migration **V17**) and **applied by `seedgen`** —
`relationships_gen.py` normalizes every label and swaps `from_name`/`to_name` on `inverse` rows (at the
candidate/name layer, before dedup and ID resolution — see F4), exactly as `variant_claims_gen.py`
applies the claim-type map; (5) `SchemaIntrospector`'s advertised relation
vocabulary is **confirmed shrunk** to canonical + genuine long-tail (the DEV-041 lesson); (6) a full
fix-loop pass — `seedgen --strict` → `reseed-local.sh` → `python -m audit` clean → `python -m runner
--runs 3` → `compare.py` vs the P2-accepted run — shows **DATA/MIXED ≥ baseline and zero stable
regressions**, and the results dir + candidates + migrations are committed together.

> **Design source of truth:** `IMPLEMENTATION_PLAN_PHASE2.md §4` (the audit package A1–A5, the
> `relation_aliases` mechanism, the backlog fix loop, the P3 exit) and `§7`/`§8`/`§9` (DDL sketch,
> the Flyway-checksum trap, entity-merge fallout, critical files); **ADR-019** (the
> `relation_aliases` decision — table shape, generation-time application, inverse swap, legit
> long-tail preservation); **ADR-017 §Decision 4** (P3-before-P4 priority: fix existing relational
> data first). This checklist is the *granular task breakdown* — it does not re-justify the design.

> **Operating principle (CLAUDE.md + ADR-017):** **fix data at the candidate-JSON layer, never with a
> runtime/query-time patch.** Every relationship/entity correction lands in
> `ingestion/extraction/output/*.json` (the editable source of truth), then flows through `seedgen` →
> `reseed-local.sh`. The audit run is a **standing pre-seedgen gate**: no batch commits until `python
> -m audit` is clean (or a finding is waived with a written note). Never act on a single-run eval
> delta — the **3-run stable/flaky** classification is the contract (`§8` Flakiness-vs-regression). A
> keyword edit made to pass a run is a logged **eval-bug** fix, never silent tuning (DEV-048/050).

Before starting, re-read `DEVIATIONS.md` (deviation protocol). Relevant carry-overs:
- **DEV-066** — `ingestion/audit/cycle_check.py` already exists (built in P2 Track G) and **is audit
  check A3**. P3 does not rewrite it — it **registers** it into the new `python -m audit` runner and
  keeps running it every batch. Its two readers (`--candidates`, `--db`) and `find_cycles` pure core
  are the contract other checks' report emission should mirror.
- **DEV-068** — 3 `parent_of` cycles were left unfixed in P2 because they are **entity-conflation, not
  reversed edges** (findings at `ingestion/audit/findings-db.json`). `Aeolus ⇄ … ⇄ Endymion` is
  source-verified (Aeolus conflated with descendant Aetolus; Calydon with Calyce) → needs an **entity
  split**, not a merge. `Cecrops ⇄ Pandion ⇄ Erechtheus` likely the same (two Cecrops / two Pandions)
  but **not yet source-verified**. `Astyoche ⇄ Tros ⇄ Ilus ⇄ Laomedon` **not yet traced**. These are
  Track J1 work; re-run `cycle_check --db` after each fix.
- **DEV-069** — Q9 ("Trace Zeus's lineage back to Chaos") no longer `serviceError`s but still misses
  `Ouranos`/`Chaos`: `Sky` (Ouranos) carries only `married_to Earth`, no `parent_of Cronus`; `Chaos`
  has no edge to `Earth`/`Sky`. Genuine data gap needing either a schema/model change (allow >1
  canonical parent per child) or a restored second-parent `Sky parent_of Cronus` row, plus a decision
  on whether `Chaos → Earth`'s cosmogonic (non-parentage) relation is modeled at all. Track J2 work —
  **may exceed P3's relational-fix scope**; if so, deliberately defer to P5b with a written note (the
  P3 exit permits an explicit waiver).
- **DEV-022 / ADR-019** — `relation_aliases` is the **exact analogue** of `claim_type_aliases`:
  `extraction/claim_type_normalizer.py::load_alias_map(conn)` reads `SELECT alias, canonical FROM
  claim_type_aliases`; `variant_claims_gen.py` calls `normalize(alias_map, x)`. Track F mirrors this —
  a `relation_normalizer.py` reading `relation_aliases`, applied in `relationships_gen.py`. **Never
  hardcode the map in code or JSON** (the DEV-022 rule); new surface variants are follow-up migrations.
- **DEV-043 / DEV-042** — the entity dup/merge and split precedents. Fuzzy dups merge at the
  candidate layer + an `entity_aliases` row (DEV-043 K↔C, `-os`↔`-us`, `-e`↔`-a`, `Ou`↔`U` pattern);
  the Io "unknown-name drop hides a split entity" precedent (DEV-042) is how A2 finds missing entities.

**Deviation protocol:** the `python -m audit` runner (A1/A2/A4/A5 checks + report emission), the
`relation_aliases` table/migration/normalizer/seedgen wiring, and every entity split/merge and
relationship-direction fix are **new** relative to the MVP `IMPLEMENTATION_PLAN.md`. Log each as the
next `DEV-NNN` (**next free number is DEV-070**) and annotate per the CLAUDE.md protocol. Reserve,
indicatively: **DEV-070** `python -m audit` runner + findings/report contract; **DEV-071** A1
duplicate-entity check; **DEV-072** A2 candidate-drop accounting; **DEV-073** A4 relation-label
taxonomy; **DEV-074** A5 alias/participant integrity; **DEV-075** `relation_aliases` V17 +
normalizer + `relationships_gen` wiring; **DEV-076+** each entity split/merge and relationship-fix
batch (the 29 dups, the 203 flagged, the DEV-068 cycles, and the DEV-069 gap **only if fixed in P3** —
if deferred to P5b it gets a waiver note, not a DEV number).

---

## Contracts verified against the live tree (code against these exact shapes)

- **Audit package today** (`ingestion/audit/`): `__init__.py` (empty), `cycle_check.py` (A3, complete),
  `README.md`, `tests/`, plus committed `findings-candidates.json` / `findings-db.json` from P2. **There
  is NO `__main__.py`** — `python -m audit` is not yet wired (Track A builds it). Each new check is a
  sibling module (`duplicate_entities.py`, `drop_accounting.py`, `relation_taxonomy.py`,
  `integrity.py`) exposing a **pure core + a reader**, mirroring `cycle_check.py::find_cycles` +
  `load_from_candidates`/`load_from_db`.
- **Editable source-of-truth JSON** (`ingestion/extraction/output/`): `entities_candidates_confirmed_v1.json`
  (V10 input), `relationships_candidates_cleaned.json` (V11 input — where direction fixes land),
  `variant_claims_candidates.json` (V12 input), `entities_fuzzy_duplicates_flagged_for_review.json`
  (the **29-pair** backlog), `relationships_flagged_for_review.json` (the **203-row** backlog),
  `entities_candidates_raw.json` + `relationships_candidates_raw.json` (the pre-drop inputs A2 diffs
  against). `ingestion/extraction/known_aliases.json` is the manual alias cross-check for A1.
- **`claim_type_aliases` mechanism to mirror** (do NOT re-invent): `extraction/claim_type_normalizer.py`
  — `load_alias_map(conn) -> dict[str,str]` runs `SELECT alias, canonical FROM claim_type_aliases`;
  `normalize(alias_map, x)` = `alias_map.get(x.strip().lower(), x)`. `variant_claims_gen.py` imports
  and applies it. Track F's `relation_normalizer.py` adds the **`inverse`** dimension —
  `load_relation_alias_map(conn) -> dict[str, (canonical, inverse)]` and a
  `normalize_relation(map, label) -> (canonical, inverse_bool)`.
- **`seedgen/relationships_gen.py`** — `_filter_and_dedup` drops rows whose `from_name`/`to_name` are
  not in V10 (this is where A2's "unknown-name drops" live), then `build_relationship_rows(...,
  alias_map)` already receives an `alias_map` param and `canonical_edge.resolve_canonical_edges`
  collapses contested groups. Track F inserts `normalize_relation` **before** dedup/canonicalization
  (ADR-019 Consequences: normalization runs first, so contested edges compare on canonical
  relation+direction), swapping `from`/`to` when `inverse`.
- **Latest migration is `V16`** (`V16__clarify_type_and_generation_comments.sql`). `relation_aliases`
  takes the next fresh number **`V17`** (`§7`/`§8`: new tables always get a fresh V-number). It is a
  **DDL + seed-rows** migration (table + the initial alias rows from A4).
- **`scripts/reseed-local.sh`** is the only sanctioned reseed (re-applies V10–V16, soon V17, without
  dropping `narrative_chunks` embeddings). **Never `docker compose down -v`.** The Flyway-checksum trap
  (`§8`): regenerating an already-applied V10–V12 file is legal **only** while local-only; the moment a
  shared env applies them, corrections must be additive (`V12_1`-style). Currently local-only → free
  regeneration still holds for this stage.
- **`compare.py` / `runner`** — the P1 eval harness. The diff target is the **P2-accepted run** (the
  most recent committed results dir under `evaluation/results/`, label `p2`), not the P1 baseline.

---

## Parallelization Guide

```
Track A  audit runner: __main__.py + findings/report contract  ─┐ (foundational — registers A3,
         + register existing cycle_check (A3)                    │  hosts B/C/D/E checks)
                                                                 │
Track B  A1 duplicate-entity check (rapidfuzz + translit)  ──────┤ needs A's check-registration API
Track C  A2 candidate-drop accounting (raw→seeded diff)    ──────┤ needs A's check-registration API
Track D  A4 relation-label taxonomy → initial alias map    ──────┤ needs A; EMITS Track F's seed rows
Track E  A5 alias/participant integrity                    ──────┘ needs A's check-registration API

Track F  relation_aliases: V17 migration + relation_normalizer  ──── code independent; SEED ROWS need D
         + relationships_gen wiring (normalize + inverse swap)        (build against a stub map, fill from D)

Track G  SchemaIntrospector shrunk-vocabulary confirmation   ────  needs F applied + a reseed (verify)
Track H  docs: DEV entries, ADR-019 follow-up, README/banners ────  pure prose — do anytime

Track I  fix loop: seedgen --strict → reseed → audit → eval → compare   SERIAL — needs A–F merged + live stack
         (G verifies during/after I's first pass; H is prose, not a precondition)
Track J  backlog triage (data edits, fan-out then serialize at the gate):
  └─ J1  29 fuzzy-dup pairs      \  edit candidate JSON in parallel;
  └─ J2  203 flagged rels         }  each merges/reseeds/re-audits through
  └─ J3  DEV-068 3 conflation cycles (entity split)   Track I's SERIAL gate.
  └─ J4  DEV-069 Q9 Chaos/Ouranos gap (may defer→P5b, waived)
```

**Rule of thumb:** A is the only hard blocker for the audit side (B/C/D/E register into it; A3 already
exists and just needs registering). F's *code* (migration + normalizer + wiring) is independent and can
be built against a stub alias map from minute one — only its **seed rows** wait on D's taxonomy output.
G verifies F after a reseed. H is pure prose, anytime. **I is the integration gate**; **J is the data
work** — the four backlogs' candidate-JSON edits fan out in parallel, but every merge serializes through
I's `seedgen → reseed → audit → eval → compare` cycle (never batch two backlogs into one unaudited
reseed). Start A, D, and F-code together; D's output unblocks F's seed rows; then run J through I.

---

## Track A — `python -m audit` runner + findings/report contract (foundational; do first)

> ⚠️ [DEVIATED - see DEVIATIONS.md #DEV-070] — implemented; details below.

Pins the check-registration API and the findings/report shapes B–E emit against. Read-only over
candidate JSON + live DB; **no check mutates any file or table** (the README invariant).

- [x] **A1r** [DEVIATED - see DEVIATIONS.md #DEV-070] — `ingestion/audit/__main__.py`: `python -m audit` entrypoint. **Auto-discovers** every
      check module that conforms to the A2r contract (A1 duplicate-entities, A2 drop-accounting, **A3 the
      existing `cycle_check`**, A4 relation-taxonomy, A5 integrity), runs them read-only, aggregates
      findings. (This is the single registration model: "register into the runner" in B4/C4/D4/E3 means
      *conform to the A2r contract and be discoverable here* — not a separate `register()` call.) Flags: `--candidates`
      / `--db` / (default both, mirroring `cycle_check`), `--only <check>` for iterating one check,
      `--out <dir>` (default `ingestion/audit/reports/`). **Exit non-zero if any check reports an
      un-waived finding** (so it can gate `seedgen` in Track I).
- [x] **A2r** [DEVIATED - see DEVIATIONS.md #DEV-070] — define the **check contract**: a small protocol/dataclass every check module exposes —
      `name`, `run(candidates_dir, db_conn) -> CheckResult{findings: list[Finding], summary: str}`,
      where `Finding` carries `{check, severity, subject, detail, suggested_fix, waived: bool}`. A3's
      `cycle_check` gets a thin adapter to this shape (do **not** edit its pure `find_cycles` core).
- [x] **A3r** [DEVIATED - see DEVIATIONS.md #DEV-070] — **findings JSON emission**: write one machine-readable
      `ingestion/audit/reports/<date>-findings.json` (all checks' `Finding`s), keeping backward-compat
      with the existing committed `findings-candidates.json` / `findings-db.json` shape where the two
      overlap (A3). State in the module docstring whether the per-check files are superseded by the
      aggregate or kept alongside.
- [x] **A4r** [DEVIATED - see DEVIATIONS.md #DEV-070] — **`reports/<date>.md`** human report: one section per check, PASS/FINDINGS/WAIVED
      badge, a table of findings with `suggested_fix`, and a top-line summary line (counts per
      severity). This is the file a reviewer reads before a fix batch.
- [x] **A5r** [DEVIATED - see DEVIATIONS.md #DEV-070] — **waiver mechanism**: a finding can be marked waived (e.g. an `audit-waivers.json` or a
      per-finding note the runner reads) so a *known, explained* finding doesn't fail the exit code.
      The P3 exit explicitly allows "clean **or** waived with a note" — this is that mechanism. A
      waiver **requires** a written reason string.
- [x] **A6r** [DEVIATED - see DEVIATIONS.md #DEV-070] — **TDD**: `ingestion/audit/tests/test_runner.py` — a fake check reporting N findings →
      runner aggregates, writes both artifacts, exits non-zero; a waived finding → exits zero; `--only`
      runs exactly one check. Pure, no live DB (fixture conn or `--candidates` only).
- [x] **A7r** [DEVIATED - see DEVIATIONS.md #DEV-070] — update `ingestion/audit/README.md`: document `python -m audit`, the five checks, the
      report/findings artifacts, the waiver mechanism, and the **"audit is the pre-seedgen gate"** rule
      (cross-ref the Flyway-checksum-trap note already in the README).

---

## Track B — A1 duplicate-entity check (needs A; `rapidfuzz` + transliteration)

- [ ] **B1** — `ingestion/audit/duplicate_entities.py`: pure core `find_duplicate_pairs(names,
      known_aliases) -> list[Pair]`. `rapidfuzz` full-pairs over the V10 entity names (from
      `entities_candidates_confirmed_v1.json`), scored above a threshold. No I/O in the core.
- [ ] **B2** — **transliteration heuristics** for the known bug class (DEV-043): normalize K↔C,
      `-os`↔`-us`, `-e`↔`-a`, `Ou`↔`U` before/alongside fuzzy scoring (the Cronos/Cronus,
      Athene/Athena, Ocean/Oceanus pattern) so those pairs surface even when raw edit-distance is high.
- [ ] **B3** — **cross-check against known aliases**: subtract pairs already covered by
      `entity_aliases` (V14, read from live DB) **and** `ingestion/extraction/known_aliases.json`.
      Only **unaliased** candidate pairs become findings → triage (Track J1).
- [ ] **B4** — register into the runner (Track A2r contract); each finding's `suggested_fix` names the
      merge-target + the `entity_aliases` row to add (DEV-043 pattern).
- [ ] **B5** — **TDD**: `tests/test_duplicate_entities.py` — a fixture name list containing a
      Cronos/Cronus-style pair and an already-aliased pair → the former is a finding, the latter is
      suppressed; a genuinely distinct pair is not flagged. Assert the ~29-pair count is reproduced
      when run over the real fixture (sanity, not exact if the heuristic legitimately finds more/fewer —
      note any delta).

---

## Track C — A2 candidate-drop accounting (needs A; raw→seeded diff)

- [ ] **C1** — `ingestion/audit/drop_accounting.py`: pure core diffing
      `relationships_candidates_raw.json` (**6,026**) against the seeded/generated set (**2,496**),
      bucketing every dropped row by reason: **unknown-entity-name** (from/to not in V10 —
      `relationships_gen._filter_and_dedup`), **contested-edge collapse**
      (`canonical_edge.resolve_canonical_edges`), **exact-duplicate dedupe**.
- [ ] **C2** — **unknown-name drilldown** (the DEV-042 Io precedent): list the distinct unknown
      from/to names by drop-frequency. These are where **missing or split entities hide** — the
      highest-value output of A2. Each becomes a finding with `suggested_fix` = "add/split entity" and
      feeds Track J.
- [ ] **C3** — reconcile the arithmetic: `raw − unknown_name − contested_collapse − dedupe == seeded`.
      The runner reports the residual; a non-zero residual is itself a finding (an unaccounted drop
      path). Reuse `relationships_gen`'s actual filter/dedup functions rather than re-deriving them, so
      the accounting matches what `seedgen` really does.
- [ ] **C4** — register into the runner; **TDD** `tests/test_drop_accounting.py`: a small raw set with
      one of each drop reason → each bucket counted correctly and the arithmetic reconciles to zero
      residual.

---

## Track D — A4 relation-label taxonomy → initial `relation_aliases` map (needs A; **emits Track F's seed rows**)

- [ ] **D1** — `ingestion/audit/relation_taxonomy.py`: frequency-classify **all 131 distinct
      `relation` strings** (from `relationships_candidates_cleaned.json` / live V11) into four buckets:
      **canonical** (`parent_of`, `killed_by`, `married_to`, `sibling_of`, …), **synonym** (`son_of` /
      `child_of` / `daughter_of` → `parent_of`; `wife_of` / `wedded` → `marriage`), **inverse** (same
      edge, from/to swapped — `killed` vs `killed_by`, `child_of` vs `parent_of`), **legit-long-tail**
      (`gave_scepter_to`, `abductor_of`, `companion_of` — preserved as-is, ADR-019 Decision 4).
- [ ] **D2** — emit the classification as a **report table** (frequency + proposed bucket + proposed
      canonical + `inverse` flag per label) for human review — the taxonomy is **review-gated**, a
      human confirms the synonym/inverse assignments before they become alias rows.
- [ ] **D3** — emit the **initial `relation_aliases` seed rows** as data (`(alias, canonical, inverse)`
      tuples) that Track F's V17 migration ingests. Format so F can paste/generate the INSERT directly.
      Legit-long-tail labels get **no row** (`normalize_relation` returns them unchanged — ADR-019
      Decision 4).
- [ ] **D4** — register into the runner as a **reporting** check (it produces the map; it "passes"
      once a human has reviewed and the rows are promoted). **TDD** `tests/test_relation_taxonomy.py`:
      a fixture label set → `son_of`/`child_of` classified inverse-of-`parent_of`, `killed`
      inverse-of-`killed_by`, `gave_scepter_to` left as legit-long-tail (no alias row).

---

## Track E — A5 alias/participant integrity (needs A)

- [ ] **E1** — `ingestion/audit/integrity.py`: pure checks — **(a)** every `entity_aliases.alias`
      target `entity_id` exists in `entities`; **(b)** no alias string equals a canonical `entities.name`
      (a self-alias); **(c)** every `myth_participants` entity reference resolves to a real `entities`
      row. Read-only over the live DB.
- [ ] **E2** — **re-run DEV-040's invariants** here as part of A5 (the plan folds "DEV-040's invariants
      re-run after every fix batch" into the integrity surface) — confirm the P2/DEV-040 direction and
      subtype invariants still hold post-fix.
- [ ] **E3** — register into the runner; **TDD** `tests/test_integrity.py`: a dangling alias, a
      self-alias, and an orphan participant each surface as a finding; a clean fixture passes.

---

## Track F — `relation_aliases`: V17 migration + normalizer + `seedgen` wiring (code independent; seed rows ← D)

Mirror the `claim_type_aliases` mechanism exactly (DEV-022 rule — one DB source of truth, never
hardcoded in code/JSON). Build the code against a **stub map** immediately; fill the real rows from D3.

- [ ] **F1** — **V17 migration** `core-api/src/main/resources/db/migration/V17__create_relation_aliases.sql`:
      `relation_aliases(alias TEXT PRIMARY KEY, canonical TEXT NOT NULL, inverse BOOLEAN NOT NULL
      DEFAULT FALSE)` (ADR-019 §7 DDL). Include a schema comment (the V8_3/V15/V16 convention) and the
      **initial alias rows from D3**. `afterMigrate__grant_app_user.sql` already grants the app user —
      confirm the new table is covered (it grants schema-wide; verify, don't assume).
- [ ] **F2** — `ingestion/extraction/relation_normalizer.py` (sibling of `claim_type_normalizer.py`):
      `load_relation_alias_map(conn) -> dict[str, tuple[str, bool]]` runs `SELECT alias, canonical,
      inverse FROM relation_aliases`; `normalize_relation(map, label) -> tuple[str, bool]` returns
      `(canonical, inverse)` on a hit (keyed by `label.strip().lower()`), `(label, False)` otherwise
      (identity for legit long-tail). **TDD** `test_relation_normalizer.py` alongside.
- [ ] **F3** — wire into `seedgen/__main__.py`: load the relation alias map from the same live
      connection that already loads `claim_type_aliases` (`load_alias_map`), pass it into
      `relationships_gen.build_relationship_rows`.
- [ ] **F4** — apply in `seedgen/relationships_gen.py`: call `normalize_relation` **before**
      `_filter_and_dedup` / `resolve_canonical_edges` (ADR-019 Consequences: normalization runs first
      so contested edges compare on canonical relation+direction). On `inverse == True`, **swap
      `from_name`/`to_name`** so every row lands on the canonical relation *and* canonical direction
      (DEV-047: `parent_of` `from_id` = parent). Preserve `source_id`/`passage_ref` through the swap.
- [ ] **F5** — **TDD** `ingestion/seedgen/tests/` (or extend existing): a candidate set with a
      `son_of`-inverse row → generated V11 row is `parent_of` with `from`/`to` swapped; a
      `gave_scepter_to` legit row → passes through unchanged; a synonym-non-inverse row → relabeled,
      direction kept. Confirm dedupe now collapses rows that were previously split across synonym
      labels (the ADR-019 "counts stop fragmenting" claim).
- [ ] **F6** — regenerate `V11__seed_relationships.sql` via `seedgen --strict` (part of Track I's loop,
      not a standalone reseed) and eyeball a spot sample of former-synonym rows landing canonical.

---

## Track G — `SchemaIntrospector` shrunk-vocabulary confirmation (needs F applied + reseed)

- [ ] **G1** — after V17 + regenerated V11 are reseeded (via Track I), query the live distinct
      `relation` vocabulary and confirm it **shrank** to canonical + genuine long-tail (synonym/inverse
      labels gone). This is the ADR-019 net-effect acceptance.
- [ ] **G2** — confirm `SchemaIntrospector` (startup `information_schema` + value-vocabulary cache)
      **reflects** the shrunk set in the `TextToSqlAgent` system prompt (the DEV-041 frequency-ordered
      channel). No code change expected — this is a **verification**; if the vocabulary is still
      fragmented, that's a Track F bug, not a new task here.
- [ ] **G3** — record the before/after distinct-label counts in the P3 results/DEV note (evidence the
      vocabulary improved), and confirm the DATA/MIXED eval delta in Track I is consistent with it.

---

## Track H — Docs / DEV entries / banners (pure prose — do anytime)

- [ ] **H1** — `docs/DEVIATIONS.md`: append DEV-070..DEV-075 (audit runner, A1, A2, A4, A5,
      `relation_aliases`) and DEV-076+ per fix batch, using the Stage/Original-Plan/What-Changed/
      Reason/Impact/Date format. Convert relative dates to absolute.
- [ ] **H2** — mark the corresponding `TODO2.md` Stage P3 items and this file's tracks with
      `[DEVIATED - see DEVIATIONS.md #DEV-NNN]` inline per the CLAUDE.md protocol.
- [ ] **H3** — add the `> ⚠️ Deviations occurred in this stage.` banner to the P3 section of
      `IMPLEMENTATION_PLAN_PHASE2.md` (never overwrite the plan body).
- [ ] **H4** — ADR-019 **follow-up**: its Consequences list "Record DEV-059; author the migration at
      Stage P3." The DEV number actually used is DEV-075 (059 was consumed elsewhere) — reconcile the
      ADR's follow-up note to the real number, or add a one-line correction, so the ADR↔DEV linkage is
      accurate.
- [ ] **H5** — update `ingestion/audit/README.md` (done in A7r) **and** confirm the
      Flyway-checksum-trap note references V17 among the regenerable-while-local-only set.

---

## Track I — Fix-loop integration gate (SERIAL — needs A–F merged + live stack)

The standing per-batch loop. **No candidate edit reaches a commit except through this cycle.** Run it
once for the F/relation_aliases landing, then once per J backlog batch. **G and H are not preconditions
for I:** Track G is a *verification performed during/after* I's first (F/`relation_aliases`) pass —
it needs I's reseed, not the reverse (avoiding the G↔I circular dependency) — and Track H is pure prose
that can land anytime.

- [ ] **I1** — `python -m audit` (candidates + db) on the **current** tree → capture the baseline
      findings/report as the starting point (expect: the 29 dups, the 3 known DEV-068 cycles, drop-accounting
      residual, taxonomy proposal — an unexpected 4th cycle is itself a finding to trace).
- [ ] **I2** — apply the batch's candidate-JSON edits (a single backlog slice — see Track J; never two
      backlogs in one reseed).
- [ ] **I3** — `python -m seedgen --strict` → regenerates V10/V11/V12. **V17 is NOT seedgen-generated** —
      it is a hand-authored DDL+seed migration (F1) whose rows come from D3, and `relation_aliases` is
      seedgen's *input* (`load_relation_alias_map`, read from the live DB), never its output. For the F
      batch the V17 file is applied by `reseed-local.sh` (I4); its rows change only via a manual edit to
      the V17 file (or a `V17_1` follow-up once shared), exactly as `claim_type_aliases` (V8_2) works.
      `--strict` must pass (referential integrity: every `variant_claims` subject + name-based subquery
      still resolves after any entity rename/split — the `§8` entity-merge-fallout guard).
- [ ] **I4** — `scripts/reseed-local.sh` (local-only) → re-applies without dropping `narrative_chunks`
      embeddings. **Never `down -v`.**
- [ ] **I5** — `python -m audit` again → **must be clean or every remaining finding explicitly
      waived** (Track A5r). This is the pre-commit gate.
- [ ] **I6** — `python -m runner --runs 3 --label p3-<batch>` → `python -m compare.py <p2-accepted>
      <p3-batch>`. Require **DATA/MIXED ≥ baseline and zero stable PASS→FAIL** (`§8`
      flakiness-vs-regression: never act on a single-run delta). A regression → triage
      **data-gap / pipeline-bug / eval-bug**, fix or **revert the batch**.
- [ ] **I7** — green → **commit candidates + migrations + results dir together** (one atomic batch, the
      `§8`/critical-files convention). Red and un-fixable in-batch → revert, log why, re-slice.

---

## Track J — Backlog triage (data edits fan out; each batch serializes through Track I)

### J1 — 29 fuzzy-duplicate entity pairs (`entities_fuzzy_duplicates_flagged_for_review.json`)
- [ ] **J1a** — for each of the 29 pairs, decide **merge** (same entity, translit variant — DEV-043
      pattern: pick the canonical name, rewrite the loser's occurrences at the candidate layer, add an
      `entity_aliases` row) or **reject** (genuinely distinct — record the reason in the file).
- [ ] **J1b** — apply merges in `entities_candidates_confirmed_v1.json` **and** propagate the renamed
      name through `relationships_candidates_cleaned.json` + `variant_claims_candidates.json` (name-based
      references — the entity-merge-fallout guard; `seedgen --strict` + A5 catch stragglers).
- [ ] **J1c** — run the batch through Track I (audit A1 should now report those pairs resolved).

### J2 — 203 flagged relationships (`relationships_flagged_for_review.json`)
- [ ] **J2a** — triage each of the 203 rows: **promote-with-fix** (correct direction/relation/entity,
      move into `relationships_candidates_cleaned.json`) or **reject** (record the decision in the file
      — the file is the audit trail).
- [ ] **J2b** — batch these (they're numerous — slice into review-sized groups; each group is one
      Track I pass, never all 203 in one unaudited reseed).
- [ ] **J2c** — after promotion, re-run A2 drop-accounting: promoted rows should no longer appear as
      unknown-name/collapse drops.

### J3 — DEV-068: 3 entity-conflation `parent_of` cycles (entity SPLIT, not merge)
- [ ] **J3a** — `Aeolus ⇄ … ⇄ Endymion` (source-verified): **split** Aeolus from descendant Aetolus
      and Calydon from Calyce in `entities_candidates_confirmed_v1.json`; repoint the offending
      `parent_of` edges to the correct split entity in `relationships_candidates_cleaned.json`. Cite
      `apollodorus_bibliotheca_frazer1921.txt [1.7.1]–[1.8.1]`.
- [ ] **J3b** — `Cecrops ⇄ Pandion ⇄ Erechtheus`: **source-verify first** (two Cecrops / two Pandions
      hypothesis) against the corpus; if confirmed, split analogously; if not, defer with a note.
- [ ] **J3c** — `Astyoche ⇄ Tros ⇄ Ilus ⇄ Laomedon`: **trace it** (not yet traced) — identify whether
      reversed edge or conflation, fix or defer-with-note accordingly.
- [ ] **J3d** — after each fix: `cycle_check --db` (A3) must show the cycle gone; the batch goes through
      Track I. Target: **A3 reports the `parent_of` graph fully clean** (or remaining cycles waived
      with a written reason).

### J4 — DEV-069: Q9 Zeus→Chaos lineage gap (may exceed P3 scope)
- [ ] **J4a** — decide the model: **(a)** restore a second-parent `Sky (Ouranos) parent_of Cronus`
      row (accepting >1 canonical parent per child — a `relationships` design change), or **(b)** defer
      the multi-parent model to **P5b** with a written waiver. The P3 exit permits an explicit waiver;
      Q9's full pass is **not** a hard P3 gate (it's DATA-adjacent lineage depth, DEV-069's own note
      flags it as possibly beyond relational-fix scope).
- [ ] **J4b** — decide whether `Chaos → Earth`'s **cosmogonic (non-parentage)** relation is modeled at
      all in P3, or noted as a distinct semantic that P5c/geography or a later stage owns. Record the
      decision either way (don't silently drop it).
- [ ] **J4c** — if fixed in P3: run through Track I and confirm Q9 now names `Ouranos`/`Chaos` with
      **live-verified keywords** (DEV-050) — a keyword edit is an eval-bug fix, logged, never silent
      tuning. If deferred: log the waiver in the results/DEV note and in `docs/DATA-GAPS.md` (P5's
      backlog).

---

## Definition-of-done checklist (mirror of TODO2.md Stage P3)

- [ ] `python -m audit` runs end-to-end (A1–A5 registered, A3 = existing `cycle_check`), emits
      `reports/<date>.md` + findings JSON, exits non-zero on un-waived findings.
- [ ] All five checks **clean or explicitly waived with a written note**.
- [ ] 29 fuzzy-dup pairs triaged (merge+alias or reject-with-note); 203 flagged relationships triaged
      (promote-with-fix or reject-recorded).
- [ ] DEV-068's 3 conflation cycles resolved (entity split) or waived; **A3 `parent_of` graph clean**.
- [ ] DEV-069 Q9 Chaos/Ouranos gap fixed **or** explicitly deferred to P5b with a written note.
- [ ] `relation_aliases` **V17** live; `relation_normalizer.py` mirrors `claim_type_normalizer.py`;
      `relationships_gen.py` normalizes + swaps `from`/`to` on `inverse` (TDD green).
- [ ] `SchemaIntrospector`'s advertised relation vocabulary **confirmed shrunk** (before/after counts
      recorded).
- [ ] Full fix-loop pass: `seedgen --strict` → `reseed-local.sh` → `audit` clean → `runner --runs 3`
      → `compare.py` vs P2-accepted → **DATA/MIXED ≥ baseline, zero stable regressions**; results dir +
      candidates + migrations committed together.
- [ ] DEV-070..DEV-076+ logged in `DEVIATIONS.md`; `TODO2.md` + `IMPLEMENTATION_PLAN_PHASE2.md` P3
      annotated per protocol; ADR-019 follow-up DEV-number reconciled.
- [ ] `./gradlew :core-api:test` green (no Kotlin change expected — SchemaIntrospector verification
      only; run it to prove no regression from the reseeded vocabulary).
