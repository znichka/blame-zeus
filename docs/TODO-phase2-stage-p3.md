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
fix-loop pass — `seedgen --strict` → `reseed-local.sh` → `python -m audit` **clean or explicitly
waived with a written note** (same gate as (1); ADR-020/DEV-088 harmonised it, since a plain "clean"
is unreachable while the reversed-edge residue exists) → `python -m runner --runs 3` → `compare.py`
vs the P2-accepted run — shows **DATA/MIXED ≥ baseline and zero stable regressions**, and the
results dir + candidates + migrations are committed together; (7) **ADR-020's joint-parentage
carve-out has landed through that gate as DEV-088**, with its counts re-measured against the real
code.

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
- **DEV-069 / ADR-020 / DEV-088** — Q9 ("Trace Zeus's lineage back to Chaos") no longer
  `serviceError`s but still misses `Ouranos`/`Chaos`: `Sky` (Ouranos) carries only `married_to
  Earth`, no `parent_of Cronus`; `Chaos` has no edge to `Earth`/`Sky`. This is **Track J4** (not J2),
  and it is **no longer an open fork** — the multi-parent question was decided as **ADR-020**
  (2026-07-23; discriminator amended 2026-07-26 after measurement), with implementation pending as
  **DEV-088**: allow >1 canonical `parent_of` edge per child for genuine **joint parentage** only,
  discriminated by a four-part rule in `resolve_canonical_edges()`. GAP-001's Recommendation is
  **fix it in P3 proper** — it is offline-only (no DDL, no runtime code) and bounded, so the
  "may exceed P3 scope" hedge applies **only to J4b** (the `Chaos → Earth` cosmogonic relation),
  which may still be deferred to P5b with a written waiver. J4a's landing scope also covers GAP-001
  **Root cause 3** (the 612 rival parents recorded nowhere) — see Track J4 for the full statement and
  `docs/DATA-GAPS.md` GAP-001 for the evidence.
- **ADR-020's own warning** — every figure in it is a *simulation* against the candidate data. The
  implementer **re-measures against the real `canonical_edge.py` change** and records what the code
  produces; and **A3 cycle counts must always state their layer** (post-resolver `parent_of` vs
  pre-collapse candidates vs `audit --candidates` vs the live seeded DB — four incomparable graphs).
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
next `DEV-NNN` (**this checklist was authored when DEV-070 was next free; DEV-070…DEV-088 are now
taken — check `DEVIATIONS.md` for the current next free number**) and annotate per the CLAUDE.md
protocol. Reserve,
indicatively: **DEV-070** `python -m audit` runner + findings/report contract; **DEV-071** A1
duplicate-entity check; **DEV-072** A2 candidate-drop accounting; **DEV-073** A4 relation-label
taxonomy; **DEV-074** A5 alias/participant integrity; **DEV-075** `relation_aliases` V17 +
normalizer + `relationships_gen` wiring; **DEV-076+** each entity split/merge and relationship-fix
batch (the 29 dups, the 203 flagged, the DEV-068 cycles). **DEV-088 is already reserved and logged
for the J4a/ADR-020 landing** (the entry currently records the pre-implementation amendment —
documentation only; the implementation pass appends to it). Only **J4b** can still end as a waiver
note instead of a DEV number.

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
  └─ J4  DEV-069 Q9 lineage gap — NOT JSON triage, this one is CODE (ADR-020 / DEV-090, landed):
         J4a  DONE — canonical_edge.py (4-part rule) + relationships_gen.py (pre-dedup pairs)
              + conflict_detector.py (same-source parentage) + new dropped-parent check
              + test rewrites, landed through Track I with zero stable regressions
         J4b  DONE — Chaos cosmogony decided: deferred to P5b, waived (DEV-091)
  └─ J5  DONE — Sky/Heaven/Uranus merged into canonical Ouranos, DEV-092; Track J fully closed for P3
```

**Rule of thumb:** A is the only hard blocker for the audit side (B/C/D/E register into it; A3 already
exists and just needs registering). F's *code* (migration + normalizer + wiring) is independent and can
be built against a stub alias map from minute one — only its **seed rows** wait on D's taxonomy output.
G verifies F after a reseed. H is pure prose, anytime. **I is the integration gate**; **J is the data
work** — the backlogs' candidate-JSON edits fan out in parallel, but every merge serializes through
I's `seedgen → reseed → audit → eval → compare` cycle (never batch two backlogs into one unaudited
reseed). Start A, D, and F-code together; D's output unblocks F's seed rows; then run J through I.

**J4a is the exception to "J is data work":** it changes generator/extractor/audit *code*, not
candidate JSON, so it does not fan out with J1–J3 — it depends on Track A's check contract (for the
dropped-parent record), edits the module Track C owns (`drop_accounting.py`'s sibling), and its unit
tests must be green *before* it enters Track I. Land it as its own serial pass, never batched with a
JSON backlog.

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

> ⚠️ [DEVIATED - see DEVIATIONS.md #DEV-073] — implemented; details below. Reproduces **45** pairs
> over the live candidate set (not exactly ~29 — expected per B5's own note; see the entry for why).

- [x] **B1** [DEVIATED - see DEVIATIONS.md #DEV-073] — `ingestion/audit/duplicate_entities.py`: pure core `find_duplicate_pairs(names,
      known_aliases) -> list[Pair]`. `rapidfuzz` full-pairs over the V10 entity names (from
      `entities_candidates_confirmed_v1.json`), scored above a threshold. No I/O in the core.
- [x] **B2** [DEVIATED - see DEVIATIONS.md #DEV-073] — **transliteration heuristics** for the known bug class (DEV-043): normalize K↔C,
      `-os`↔`-us`, `-e`↔`-a`, `Ou`↔`U` before/alongside fuzzy scoring (the Cronos/Cronus,
      Athene/Athena, Ocean/Oceanus pattern) so those pairs surface even when raw edit-distance is high.
- [x] **B3** [DEVIATED - see DEVIATIONS.md #DEV-073] — **cross-check against known aliases**: subtract pairs already covered by
      `entity_aliases` (V14, read from live DB) **and** `ingestion/extraction/known_aliases.json`.
      Only **unaliased** candidate pairs become findings → triage (Track J1).
- [x] **B4** [DEVIATED - see DEVIATIONS.md #DEV-073] — register into the runner (Track A2r contract); each finding's `suggested_fix` names the
      merge-target + the `entity_aliases` row to add (DEV-043 pattern).
- [x] **B5** [DEVIATED - see DEVIATIONS.md #DEV-073] — **TDD**: `tests/test_duplicate_entities.py` — a fixture name list containing a
      Cronos/Cronus-style pair and an already-aliased pair → the former is a finding, the latter is
      suppressed; a genuinely distinct pair is not flagged. Assert the ~29-pair count is reproduced
      when run over the real fixture (sanity, not exact if the heuristic legitimately finds more/fewer —
      note any delta).

---

## Track C — A2 candidate-drop accounting (needs A; raw→seeded diff)

> ⚠️ [DEVIATED - see DEVIATIONS.md #DEV-074] — implemented; details below. "Raw" is
> `relationships_candidates_cleaned.json` (**6,009** today — seedgen's actual input), not the
> literal `relationships_candidates_raw.json` file (7,406, pre-B4-manual-cleanup) — the "6,026" this
> checklist names is itself the pre-DEV-067 count of the *cleaned* file, matching
> `IMPLEMENTATION_PLAN_PHASE2.md §4.1`'s own "the 6,026→2,496 relationship drop" framing. The
> three named buckets are exactly `relationships_gen.py`'s own mechanical filters, which only ever
> run over the cleaned file — the earlier raw→cleaned gap (B4's manual review + the 203-row
> `relationships_flagged_for_review.json` held-out set) is a separate, already-documented,
> one-off historical decision (DEV-043/044), not a repeatable arithmetic this check re-derives.

- [x] **C1** [DEVIATED - see DEVIATIONS.md #DEV-074] — `ingestion/audit/drop_accounting.py`: pure core diffing
      `relationships_candidates_raw.json` (**6,026**) against the seeded/generated set (**2,496**),
      bucketing every dropped row by reason: **unknown-entity-name** (from/to not in V10 —
      `relationships_gen._filter_and_dedup`), **contested-edge collapse**
      (`canonical_edge.resolve_canonical_edges`), **exact-duplicate dedupe**.
- [x] **C2** [DEVIATED - see DEVIATIONS.md #DEV-074] — **unknown-name drilldown** (the DEV-042 Io precedent): list the distinct unknown
      from/to names by drop-frequency. These are where **missing or split entities hide** — the
      highest-value output of A2. Each becomes a finding with `suggested_fix` = "add/split entity" and
      feeds Track J.
- [x] **C3** [DEVIATED - see DEVIATIONS.md #DEV-074] — reconcile the arithmetic: `raw − unknown_name − contested_collapse − dedupe == seeded`.
      The runner reports the residual; a non-zero residual is itself a finding (an unaccounted drop
      path). Reuse `relationships_gen`'s actual filter/dedup functions rather than re-deriving them, so
      the accounting matches what `seedgen` really does.
- [x] **C4** [DEVIATED - see DEVIATIONS.md #DEV-074] — register into the runner; **TDD** `tests/test_drop_accounting.py`: a small raw set with
      one of each drop reason → each bucket counted correctly and the arithmetic reconciles to zero
      residual.
- [x] **C5 — per-row dropped-parent record** [DEVIATED - see DEVIATIONS.md #DEV-090] — landed with
      J4a as audit check **A6** (`ingestion/audit/dropped_parents.py`). Live on the real, post-split
      candidate data: 697 dropped rows / 612 distinct child+parent pairs, 694 without existing
      promoted `variant_claims` coverage.

---

## Track D — A4 relation-label taxonomy → initial `relation_aliases` map (needs A; **emits Track F's seed rows**)

> ⚠️ [DEVIATED - see DEVIATIONS.md #DEV-071] — implemented; details below. Live candidate-JSON count
> is now **177** distinct labels (not the 131 this checklist was authored against — the corpus has
> grown since); the mechanism and buckets are unaffected, only the raw count differs.

- [x] **D1** [DEVIATED - see DEVIATIONS.md #DEV-071] — `ingestion/audit/relation_taxonomy.py`: frequency-classify **all 131 distinct
      `relation` strings** (from `relationships_candidates_cleaned.json` / live V11) into four buckets:
      **canonical** (`parent_of`, `killed_by`, `married_to`, `sibling_of`, …), **synonym** (`son_of` /
      `child_of` / `daughter_of` → `parent_of`; `wife_of` / `wedded` → `marriage`), **inverse** (same
      edge, from/to swapped — `killed` vs `killed_by`, `child_of` vs `parent_of`), **legit-long-tail**
      (`gave_scepter_to`, `abductor_of`, `companion_of` — preserved as-is, ADR-019 Decision 4).
- [x] **D2** [DEVIATED - see DEVIATIONS.md #DEV-071] — emit the classification as a **report table** (frequency + proposed bucket + proposed
      canonical + `inverse` flag per label) for human review — the taxonomy is **review-gated**, a
      human confirms the synonym/inverse assignments before they become alias rows.
- [x] **D3** [DEVIATED - see DEVIATIONS.md #DEV-071] — emit the **initial `relation_aliases` seed rows** as data (`(alias, canonical, inverse)`
      tuples) that Track F's V17 migration ingests. Format so F can paste/generate the INSERT directly.
      Legit-long-tail labels get **no row** (`normalize_relation` returns them unchanged — ADR-019
      Decision 4).
- [x] **D4** [DEVIATED - see DEVIATIONS.md #DEV-071] — register into the runner as a **reporting** check (it produces the map; it "passes"
      once a human has reviewed and the rows are promoted). **TDD** `tests/test_relation_taxonomy.py`:
      a fixture label set → `son_of`/`child_of` classified inverse-of-`parent_of`, `killed`
      inverse-of-`killed_by`, `gave_scepter_to` left as legit-long-tail (no alias row).

---

## Track E — A5 alias/participant integrity (needs A)

> ⚠️ [DEVIATED - see DEVIATIONS.md #DEV-075] — implemented; details below. "Subtype invariants"
> (E2) was ambiguous in this checklist — no earlier DEV entry defines a concrete subtype-specific
> rule beyond the `entities.type` CHECK enum, so E2 re-verifies that enum (defensively — it's
> already DB-enforced) alongside DEV-040's three documented direction invariants. All checks PASS
> clean against the live DB today (0 findings).

- [x] **E1** [DEVIATED - see DEVIATIONS.md #DEV-075] — `ingestion/audit/integrity.py`: pure checks — **(a)** every `entity_aliases.alias`
      target `entity_id` exists in `entities`; **(b)** no alias string equals a canonical `entities.name`
      (a self-alias); **(c)** every `myth_participants` entity reference resolves to a real `entities`
      row. Read-only over the live DB.
- [x] **E2** [DEVIATED - see DEVIATIONS.md #DEV-075] — **re-run DEV-040's invariants** here as part of A5 (the plan folds "DEV-040's invariants
      re-run after every fix batch" into the integrity surface) — confirm the P2/DEV-040 direction and
      subtype invariants still hold post-fix.
- [x] **E3** [DEVIATED - see DEVIATIONS.md #DEV-075] — register into the runner; **TDD** `tests/test_integrity.py`: a dangling alias, a
      self-alias, and an orphan participant each surface as a finding; a clean fixture passes.

---

## Track F — `relation_aliases`: V17 migration + normalizer + `seedgen` wiring (code independent; seed rows ← D)

> ⚠️ [DEVIATED - see DEVIATIONS.md #DEV-072] — F1–F5 implemented (code + migration + TDD); F6
> deliberately deferred to Track I as this checklist itself specifies ("part of Track I's loop, not
> a standalone reseed" — V17 has not been applied to any DB, only syntax/semantics-verified via a
> rolled-back transaction).

Mirror the `claim_type_aliases` mechanism exactly (DEV-022 rule — one DB source of truth, never
hardcoded in code/JSON). Build the code against a **stub map** immediately; fill the real rows from D3.

- [x] **F1** [DEVIATED - see DEVIATIONS.md #DEV-072] — **V17 migration** `core-api/src/main/resources/db/migration/V17__create_relation_aliases.sql`:
      `relation_aliases(alias TEXT PRIMARY KEY, canonical TEXT NOT NULL, inverse BOOLEAN NOT NULL
      DEFAULT FALSE)` (ADR-019 §7 DDL). Include a schema comment (the V8_3/V15/V16 convention) and the
      **initial alias rows from D3**. `afterMigrate__grant_app_user.sql` already grants the app user —
      confirm the new table is covered (it grants schema-wide; verify, don't assume).
- [x] **F2** [DEVIATED - see DEVIATIONS.md #DEV-072] — `ingestion/extraction/relation_normalizer.py` (sibling of `claim_type_normalizer.py`):
      `load_relation_alias_map(conn) -> dict[str, tuple[str, bool]]` runs `SELECT alias, canonical,
      inverse FROM relation_aliases`; `normalize_relation(map, label) -> tuple[str, bool]` returns
      `(canonical, inverse)` on a hit (keyed by `label.strip().lower()`), `(label, False)` otherwise
      (identity for legit long-tail). **TDD** `test_relation_normalizer.py` alongside.
- [x] **F3** [DEVIATED - see DEVIATIONS.md #DEV-072] — wire into `seedgen/__main__.py`: load the relation alias map from the same live
      connection that already loads `claim_type_aliases` (`load_alias_map`), pass it into
      `relationships_gen.build_relationship_rows`.
- [x] **F4** [DEVIATED - see DEVIATIONS.md #DEV-072] — apply in `seedgen/relationships_gen.py`: call `normalize_relation` **before**
      `_filter_and_dedup` / `resolve_canonical_edges` (ADR-019 Consequences: normalization runs first
      so contested edges compare on canonical relation+direction). On `inverse == True`, **swap
      `from_name`/`to_name`** so every row lands on the canonical relation *and* canonical direction
      (DEV-047: `parent_of` `from_id` = parent). Preserve `source_id`/`passage_ref` through the swap.
- [x] **F5** [DEVIATED - see DEVIATIONS.md #DEV-072] — **TDD** `ingestion/seedgen/tests/` (or extend existing): a candidate set with a
      `son_of`-inverse row → generated V11 row is `parent_of` with `from`/`to` swapped; a
      `gave_scepter_to` legit row → passes through unchanged; a synonym-non-inverse row → relabeled,
      direction kept. Confirm dedupe now collapses rows that were previously split across synonym
      labels (the ADR-019 "counts stop fragmenting" claim).
- [x] **F6** [DEVIATED - see DEVIATIONS.md #DEV-076] — regenerate `V11__seed_relationships.sql` via `seedgen --strict` (part of Track I's loop,
      not a standalone reseed) and eyeball a spot sample of former-synonym rows landing canonical.
      Done during Track I's first pass; re-run again during the second (J3 batch) pass. Confirmed
      zero occurrences of any of the 9 synonym/inverse labels in the regenerated file both times.
      *(A stale "Not yet done — deferred to Track I" sentence followed here, contradicting the two
      lines above it and this box's own `[x]`. It was written while F was in flight, before Track I
      ran, and never removed — deleted 2026-07-27 `[DEVIATED - see DEVIATIONS.md #DEV-093]`. F6 is
      done; the deferral it described is what DEV-076 discharged.)*

---

## Track G — `SchemaIntrospector` shrunk-vocabulary confirmation (needs F applied + reseed)

> ⚠️ [DEVIATED - see DEVIATIONS.md #DEV-076] — verified during Track I's first pass, as designed
> (G needs I's reseed, not the reverse). 124 → 116 distinct relations; 8 → 0 synonym/inverse
> candidates live. G2 verified indirectly (not a live debug-endpoint probe): the 3-run eval in the
> same DEV-076 pass exercised `TextToSqlAgent` against this exact restarted server, so its
> SQL-generation prompt necessarily used the post-reseed cached vocabulary already confirmed by G1.

- [x] **G1** [DEVIATED - see DEVIATIONS.md #DEV-076] — after V17 + regenerated V11 are reseeded (via Track I), query the live distinct
      `relation` vocabulary and confirm it **shrank** to canonical + genuine long-tail (synonym/inverse
      labels gone). This is the ADR-019 net-effect acceptance.
- [x] **G2** [DEVIATED - see DEVIATIONS.md #DEV-076] — confirm `SchemaIntrospector` (startup `information_schema` + value-vocabulary cache)
      **reflects** the shrunk set in the `TextToSqlAgent` system prompt (the DEV-041 frequency-ordered
      channel). No code change expected — this is a **verification**; if the vocabulary is still
      fragmented, that's a Track F bug, not a new task here.
- [x] **G3** [DEVIATED - see DEVIATIONS.md #DEV-076] — record the before/after distinct-label counts in the P3 results/DEV note (evidence the
      vocabulary improved), and confirm the DATA/MIXED eval delta in Track I is consistent with it.

---

## Track H — Docs / DEV entries / banners (pure prose — do anytime)

> ⚠️ Done throughout, incrementally, as each track landed (not as one separate pass) — H1/H2/H3/H5
> were satisfied inline by each track's own DEV entry + checklist annotation + README update; only
> H4 (the ADR-019 DEV-number reconciliation) needed a dedicated pass, done now.

- [x] **H1** — `docs/DEVIATIONS.md`: append DEV-070..DEV-075 (audit runner, A1, A2, A4, A5,
      `relation_aliases`) and DEV-076+ per fix batch, using the Stage/Original-Plan/What-Changed/
      Reason/Impact/Date format. Convert relative dates to absolute. Done through **DEV-077**
      (actual sequence: 070 runner, 071 A4, 072 relation_aliases, 073 A1, 074 A2, 075 A5, 076 Track
      I first pass, 077 J3 triage — order differs from the checklist's indicative guess, per each
      entry's own reconciliation note).
- [x] **H2** — mark the corresponding `TODO2.md` Stage P3 items and this file's tracks with
      `[DEVIATED - see DEVIATIONS.md #DEV-NNN]` inline per the CLAUDE.md protocol. Done in this file
      throughout; `TODO2.md` itself is the earlier, less granular planning doc superseded by this
      checklist (its own P3 section already just points here) — not separately annotated line-by-line.
- [x] **H3** — add the `> ⚠️ Deviations occurred in this stage.` banner to the P3 section of
      `IMPLEMENTATION_PLAN_PHASE2.md` (never overwrite the plan body). Added during Track A (DEV-070).
- [x] **H4** — ADR-019 **follow-up**: its Consequences list "Record DEV-059; author the migration at
      Stage P3." The DEV number actually used is DEV-075 (059 was consumed elsewhere) — reconcile the
      ADR's follow-up note to the real number, or add a one-line correction, so the ADR↔DEV linkage is
      accurate. **Reconciled** [DEVIATED - see DEVIATIONS.md #DEV-072, #DEV-076] — the real numbers
      are **DEV-072** (the migration/normalizer/wiring itself) and **DEV-076** (the `SchemaIntrospector`
      confirmation) — neither DEV-059 nor this bullet's own guess of DEV-075 was correct; `adr-019-relation-label-canonicalization.md`'s Follow-ups section corrected accordingly.
- [x] **H5** — update `ingestion/audit/README.md` (done in A7r) **and** confirm the
      Flyway-checksum-trap note references V17 among the regenerable-while-local-only set. Done
      during Track F (DEV-072).

---

## Track I — Fix-loop integration gate (SERIAL — needs A–F merged + live stack)

> ⚠️ [DEVIATED - see DEVIATIONS.md #DEV-076] — first pass (F/relation_aliases landing) complete:
> I1–I6 done; I7 (commit) initially withheld pending an explicit decision, per this project's
> standing "never commit without being asked" convention — **later committed** as `64fe772` +
> `962c521`. Along the way: fixed
> a Flyway out-of-order bug in `scripts/reseed-local.sh` (it predated V17 and only knew about
> V10–V16), and a staleness bug in A2 (`drop_accounting.py` had hardcoded "no relation_alias
> normalization", now stale since V17 is genuinely live). **A live cycle count really did go 3→4**
> in A3 (exactly the scenario I1's own note below anticipated) — `Creon ⇄
> Menoeceus` and `Agastrophus ⇄ Paeëon`, both newly-visible because normalization unified
> `child_of`/`son_of` into `parent_of` for the first time; the pre-existing `Astyoche ⇄ Tros ⇄ Ilus
> ⇄ Laomedon` cycle disappeared as a side effect. Logged as a new Track J lead, not fixed in this
> pass (never two backlogs in one reseed).
>
> ⚠️ [DEVIATED - see DEVIATIONS.md #DEV-083] — **second pass** (the batched J3 backlog — DEV-077
> through DEV-082, 6 entity splits) complete: single reseed (no chicken-and-egg this time,
> `relation_aliases` already live), `python -m audit --db` now reports **A3: 0 `parent_of`
> cycles** — the graph is fully clean for the first time. Eval: zero stable regressions, identical
> profile to the first pass (none of the 16 gold questions touch the entities this batch fixed).
> I7 (commit) initially withheld again — **later committed** as `43d951f`.

The standing per-batch loop. **No candidate edit reaches a commit except through this cycle.** Run it
once for the F/relation_aliases landing, then once per J backlog batch. **G and H are not preconditions
for I:** Track G is a *verification performed during/after* I's first (F/`relation_aliases`) pass —
it needs I's reseed, not the reverse (avoiding the G↔I circular dependency) — and Track H is pure prose
that can land anytime.

- [x] **I1** [DEVIATED - see DEVIATIONS.md #DEV-076] — `python -m audit` (candidates + db) on the **current** tree → capture the baseline
      findings/report as the starting point (expect: the 29 dups, the 3 known DEV-068 cycles, drop-accounting
      residual, taxonomy proposal — an unexpected 4th cycle is itself a finding to trace).
- [x] **I2** [DEVIATED - see DEVIATIONS.md #DEV-076] — apply the batch's candidate-JSON edits (a single backlog slice — see Track J; never two
      backlogs in one reseed). **No-op for this batch** — the F/relation_aliases landing needs no candidate edits.
- [x] **I3** [DEVIATED - see DEVIATIONS.md #DEV-076] — `python -m seedgen --strict` → regenerates V10/V11/V12. **V17 is NOT seedgen-generated** —
      it is a hand-authored DDL+seed migration (F1) whose rows come from D3, and `relation_aliases` is
      seedgen's *input* (`load_relation_alias_map`, read from the live DB), never its output. For the F
      batch the V17 file is applied by `reseed-local.sh` (I4); its rows change only via a manual edit to
      the V17 file (or a `V17_1` follow-up once shared), exactly as `claim_type_aliases` (V8_2) works.
      `--strict` must pass (referential integrity: every `variant_claims` subject + name-based subquery
      still resolves after any entity rename/split — the `§8` entity-merge-fallout guard).
- [x] **I4** [DEVIATED - see DEVIATIONS.md #DEV-076] — `scripts/reseed-local.sh` (local-only) → re-applies without dropping `narrative_chunks`
      embeddings. **Never `down -v`.** Required a **two-reseed sequence** for this specific batch
      (reseed → `seedgen --strict` (now able to read the live `relation_aliases`) → reseed again) —
      a chicken-and-egg specific to landing a *new* seedgen-input table for the first time; ordinary
      Track J batches (no new input table) will only need one reseed per pass.
- [x] **I5** [DEVIATED - see DEVIATIONS.md #DEV-076] — `python -m audit` again → **must be clean or every remaining finding explicitly
      waived** (Track A5r). This is the pre-commit gate. **Not fully clean**: A5 clean; A1/A2/A4
      unchanged from I1 (pre-existing Track J backlog); A3 went 3→4 (see banner above) — none of
      these are waived yet, so I7 (commit) is correctly gated pending Track J or explicit waivers.
      This is expected for the *first* Track I pass (which only lands F, not any Track J batch).
- [x] **I6** [DEVIATED - see DEVIATIONS.md #DEV-076] — `python -m runner --runs 3 --label p3-<batch>` → `python -m compare.py <p2-accepted>
      <p3-batch>`. Require **DATA/MIXED ≥ baseline and zero stable PASS→FAIL** (`§8`
      flakiness-vs-regression: never act on a single-run delta). A regression → triage
      **data-gap / pipeline-bug / eval-bug**, fix or **revert the batch**.
- [x] **I7** — green → **commit candidates + migrations + results dir together** (one atomic batch, the
      `§8`/critical-files convention). Red and un-fixable in-batch → revert, log why, re-slice.
      This F/relation_aliases pass's own commit predates this session (folded into the git history
      already in place when Track J work began); every subsequent Track I pass through DEV-092 has
      also since been committed (`dc22459`, `b26e69b`, `201eac8`, `5eed421`, `35fb379`).

---

## Track J — Backlog triage (data edits fan out; each batch serializes through Track I)

### J1 — 29 fuzzy-duplicate entity pairs (`entities_fuzzy_duplicates_flagged_for_review.json`)
- [x] **J1a** [DEVIATED - see DEVIATIONS.md #DEV-084] — for each of the 29 pairs, decide **merge** (same entity, translit variant — DEV-043
      pattern: pick the canonical name, rewrite the loser's occurrences at the candidate layer, add an
      `entity_aliases` row) or **reject** (genuinely distinct — record the reason in the file). **All
      48 live pairs triaged** (A1's live count grew from 29 to 45 to 48 as Track J3's entity splits
      added incidental leads): **8 merged** (`Ilithyia`→`Eileithyia`, `Alcmene`→`Alcmena`,
      `Atropus`→`Atropos`, `Euneos`→`Euneus`, `Cebrenus`→`Cebren`, `Perimela`→`Perimele`,
      `Lampetia`→`Lampetie`, `Epicaste`→`Epicasta` for its Jocasta portion only), **40 rejected**
      with specific recorded reasons. `Epicaste` turned out to be a **third** multi-way name
      conflation (Jocasta + Calydon's daughter + Augeas's daughter) — split, not merged wholesale,
      matching the `Menoeceus`/`Astyoche` precedent; got **no** blanket `entity_aliases` row for
      that reason (ambiguous in the source itself). One pair (`Coeranos`/`Coeranus`) was downgraded
      from a tentative merge to reject after finding `Coeranus` itself likely already covers two
      different Iliad casualties — flagged as a new, deeper lead, not fixed here.
- [x] **J1b** [DEVIATED - see DEVIATIONS.md #DEV-084] — apply merges in `entities_candidates_confirmed_v1.json` **and** propagate the renamed
      name through `relationships_candidates_cleaned.json` + `variant_claims_candidates.json` (name-based
      references — the entity-merge-fallout guard; `seedgen --strict` + A5 catch stragglers). No
      `variant_claims_candidates.json` rows referenced any losing name (checked, confirmed empty).
      `V14__create_entity_aliases.sql` and `known_aliases.json` both updated with the 7 genuine 1:1
      aliases (mirroring the DEV-043 dual-file convention).
- [x] **J1c** [DEVIATED - see DEVIATIONS.md #DEV-089] — run the batch through Track I. **Landed
      2026-07-26**, bundled with J2/J3f/J3g/J3h in one pass: `seedgen --strict` → `reseed-local.sh`
      → `python -m audit --db` (A1 39 pairs, matching candidates-mode exactly — the 8 merges took;
      A3 1 finding, waived — see J3h's note below, unrelated to J1) → `runner --runs 3` vs
      `p3-j3-batch` → **no stable regressions** (identical 11/16). `Coeranos`/`Coeranus` (flagged
      here as a new lead) untangled in J3h (DEV-087) — turned out to be 3 distinct figures, not 2.

### J2 — 203 flagged relationships (`relationships_flagged_for_review.json`)
- [x] **J2a** [DEVIATED - see DEVIATIONS.md #DEV-085] — triage each of the 203 rows: **promote-with-fix**
      (correct direction/relation/entity, move into `relationships_candidates_cleaned.json`) or
      **reject** (record the decision in the file — the file is the audit trail). **All 203 triaged**
      via a 3-tier method (majority-vote by corroborating-row count → `SPINE_PRIORITY` tie-break →
      manual corpus verification): **202 resolved** (895 rows promoted), **1 rejected**
      (`Eumelus`/`Pheres` — a generation-skip extraction error, no valid claim either direction).
      Triage surfaced 2 more entity conflations needing splits (a second `Helen`/`Hellen` instance at
      entry 16; a 4th `Creon` — `Creon (father of Lycomedes)` — at entry 173) and a `Phorcus`→`Phocus`
      mislabeling spanning entries 114/200 **plus 3 pre-existing main-file rows** fixed alongside.
- [x] **J2b** [DEVIATED - see DEVIATIONS.md #DEV-085] — batch these (they're numerous — slice into
      review-sized groups; each group is one Track I pass, never all 203 in one unaudited reseed).
      **All 203 processed and written as one batch** (not sliced further — the 3-tier method made
      per-entry review tractable in one pass); sits with J1 for one future Track I pass, matching the
      cost-minimization convention established for J3.
- [x] **J2c** [DEVIATED - see DEVIATIONS.md #DEV-089] — after promotion, re-run A2 drop-accounting.
      **Landed 2026-07-26** in the same Track I pass as J1c (see there for the full
      seedgen/reseed/audit/eval sequence). Note: A2's read is `--candidates`-only (it needs the
      candidate JSON to diff raw→seeded), so it wasn't re-run post-reseed in `--db` mode — the
      pre-batch `--candidates` snapshot already reflected the promoted 895 rows correctly (matches
      seedgen's own V11 count of 2,492).

### J3 — DEV-068: 3 entity-conflation `parent_of` cycles (entity SPLIT, not merge)
- [x] **J3a** [DEVIATED - see DEVIATIONS.md #DEV-078] — `Aeolus ⇄ … ⇄ Endymion` (source-verified): **split** Aeolus from descendant Aetolus
      and Calydon from Calyce in `entities_candidates_confirmed_v1.json`; repoint the offending
      `parent_of` edges to the correct split entity in `relationships_candidates_cleaned.json`. Cite
      `apollodorus_bibliotheca_frazer1921.txt [1.7.1]–[1.8.1]`. **Correction on re-verification**:
      `Calydon`/`Calyce` were already two separate entities (no split needed there); the real gap was
      `Aetolus` (missing entirely) and a **second, previously-unflagged conflation** — `Protogenia`
      also refers to two different people (Deucalion's daughter vs. Calydon's daughter) — both now
      split. Cycle confirmed gone via `cycle_check` (candidates mode). **Batched, not yet reseeded**:
      sits alongside DEV-077's `Agastrophus` fix for one future Track I pass (user's explicit
      cost-minimization call — Track I runs once per batch, not once per edit).
- [x] **J3b** [DEVIATED - see DEVIATIONS.md #DEV-079] — `Cecrops ⇄ Pandion ⇄ Erechtheus`: **source-verify first** (two Cecrops / two Pandions
      hypothesis) against the corpus; if confirmed, split analogously; if not, defer with a note.
      **Confirmed and split** — two Cecrops as hypothesized, but **three** Pandions (a wholly
      unrelated third Pandion from the Danaid myth, `[2.1.5]`, surfaced only by checking every row
      referencing the name, not just the cycle's own 3 edges). Cycle confirmed gone (candidates
      mode). **Batched, not yet reseeded** — sits with DEV-077/DEV-078 for one future Track I pass.
- [x] **J3c** [DEVIATED - see DEVIATIONS.md #DEV-080] — `Astyoche ⇄ Tros ⇄ Ilus ⇄ Laomedon`: **trace it** (not yet traced) — identify whether
      reversed edge or conflation, fix or defer-with-note accordingly. **Root-caused**: the `--db`
      disappearance (DEV-076) was a **masking artifact**, not a fix — an unrelated bare `Ilus son_of
      Dardanus` row (Homer, `11.368-11.410` — the same passage checked for DEV-077's `Agastrophus`
      fix, about a *different*, ancient "Ilus, son of Dardanus... an elder... in days of old") got
      normalized by Track F into a new competing `parent_of` claim that happened to win the
      alphabetical tie-break over the real `Tros parent_of Ilus`, hiding the cycle without actually
      fixing anything (confirmed still present in `--candidates` mode the whole time, which applies
      no normalization/collapse). **Fixed the real cause**: `Astyoche` conflates Erichthonius's wife
      (Tros's mother, `[3.12.2]`: "Astyoche, daughter of Simoeis") with Laomedon's daughter (Priam's
      sister, `[E.6.15c]`) — split both out, plus repointed the `Ilus`/`Dardanus` mislabel to the
      already-existing `Ilus (son of Dardanus)` entity. Cycle confirmed gone (candidates mode) for a
      genuine reason this time. **Noted, not fixed** (at the time — both resolved later in J3h,
      DEV-087): `Astyoche` still ambiguously covering more distinct people, and 3
      `Aeneas parent_of/ancestor_of Ilus` rows whose cited Ovid passages never mention "Ilus" at all.
      **Batched, not yet reseeded** — sits with DEV-077/078/079.
- [x] **J3d** [DEVIATED - see DEVIATIONS.md #DEV-083] — after each fix: `cycle_check --db` (A3) must show the cycle gone; the batch goes through
      Track I. Target: **A3 reports the `parent_of` graph fully clean** (or remaining cycles waived
      with a written reason). **Achieved** — `python -m audit --db` reports **A3: 0 parent_of
      cycles** after the second Track I pass landed all of DEV-077–082 in one batch.
- [x] **J3e** [DEVIATED - see DEVIATIONS.md #DEV-081] — **`Creon ⇄ Menoeceus`** (surfaced by Track I's
      F-landing pass, DEV-076 — newly visible once `child_of`/`son_of` normalized into `parent_of`):
      **source-verified as a namesake collision, not a reversed edge** — `apollodorus_bibliotheca_frazer1921.txt`
      `[3.5.8]` ("Creon, son of Menoeceus, succeeded to the kingdom") names Menoeceus **the elder**,
      Creon's father; `[3.6.7]` ("Menoeceus, son of Creon, would offer himself... slew himself before
      the gates") names Menoeceus **the younger**, Creon's son who sacrifices himself in the Seven
      Against Thebes war. Both edges are individually correct; extraction merged two different people
      into one entity. **Split, and turned out bigger than diagnosed**: `Creon` actually names
      **three** people (Thebes, Corinth, son of Hercules — the last two already partially
      disambiguated in an earlier pass, the same "some rows got the memo, some didn't" pattern
      DEV-080 found for `Ilus`). Added `Creon (king of Corinth)`, `Menoeceus (father of Creon)`,
      `Menoeceus (son of Creon)`; repointed 8 rows. Verified via the same simulated-resolved-graph
      method DEV-080 used (this cycle only exists post-normalization, invisible to plain
      `cycle_check --candidates`). **New unrelated lead found while verifying, not fixed**: the
      simulated graph's one remaining cycle (`Aeolus ⇄ Athamas ⇄ Hellen`) traces to `Athamas`'s
      daughter **`Helle`** (of Hellespont fame, `[1.9.1]`) extracted as `Hellen` (the male
      ancestor-figure) — a fresh spelling conflation, not yet its own checklist item. **Batched, not
      yet reseeded** — sits with DEV-077/078/079/080.

### J3f — new lead (DEV-081): `Helle`/`Hellen` spelling conflation
- [x] **J3f** [DEVIATED - see DEVIATIONS.md #DEV-082] `Athamas parent_of Hellen` (`apollodorus-bibliotheca`,
      `1.9.1`) should be `Athamas parent_of Helle` — Athamas's daughter `Helle` (who fell into the
      strait later named the Hellespont after her) was extracted under the name of the unrelated,
      much more heavily-referenced `Hellen` (Deucalion's son, eponym of the Greeks). **Turned out to
      be a 3-way, 60-row conflation, not a 1-row typo**: bare `Hellen` mixed the real `Hellen`
      (5 rows), `Helle` (3 rows), and **`Helen` of Troy** (52 rows — married to Menelaus, then
      Paris, then Deiphobus; daughter of Zeus/Leda; mother of Hermione). Split all three out
      (bucketed by passage-ref, verified against source, asserted exact bucket sizes 5/3/52 before
      writing). Simulated post-Track-F resolved graph now has **zero** `parent_of` cycles (was 1);
      `--candidates` cycle count dropped 100 → 89 (11 fewer, not 1 — `Hellen`'s conflated edges were
      threading through several already-observed tangled chains too). [DEVIATED - see
      DEVIATIONS.md #DEV-089] **Landed 2026-07-26**, bundled with J1/J2/J3g/J3h in one Track I pass
      — see J1c for the sequence.

### J3g — new lead (DEV-085/086): 8 pre-existing majority/minority reversed-direction pairs surfaced by J2
- [x] **J3g** [DEVIATED - see DEVIATIONS.md #DEV-086] — promoting J2's 895 rows unexpectedly raised A3's
      `parent_of` cycle count from 89 to 127. Investigated and confirmed all 8 new "near-certain"
      (2-node) cycles (`Achilles⇄Peleus`, `Priam⇄Hector`, `Telamon⇄Ajax`, `Penelope⇄Telemachus`,
      `Clymene⇄Oceanus`, `Cronus⇄Hestia`, `Zeus⇄Cronus`, `Tantalus⇄Niobe`) were **pre-existing**
      majority/minority direction splits already in `relationships_candidates_cleaned.json`
      (unrelated to the J2-promoted rows), previously hidden inside larger already-counted tangled
      SCCs — `cycle_check.py` reports only one back-edge per SCC (documented as non-exhaustive), and
      adding 895 new edges changed DFS iteration order enough to surface these specific back-edges
      directly. Reversed the 45 minority-direction rows across the 8 pairs to match the (mythologically
      standard) majority direction, keeping original `source_id`/`passage_ref` citations. A3 dropped
      127 → 99 with 0 remaining 2-node cycles. [DEVIATED - see DEVIATIONS.md #DEV-089] **Landed
      2026-07-26**, bundled with J1/J2/J3f/J3h in one Track I pass — see J1c for the sequence.
      Remaining 99 (candidates-mode)/96 (post-J3h) cycles are longer chains, a separate
      not-yet-triaged backlog; the live `--db` graph post-landing shows exactly **1** cycle
      (`Eurymachus⇄Polybus`, unrelated to J3g, waived — see DEV-089).

### J3h — loose-lead cleanup (DEV-087): `Coeranos`/`Coeranus`, `Astyoche`'s remaining 2 meanings, `Aeneas`/`Iulus`, `Megaera`/`Megara`
- [x] **J3h** [DEVIATED - see DEVIATIONS.md #DEV-087] — closed out four leads that had been noted in
      passing (J1c, J3c, J3e) but never promoted to their own checklist items. `Coeranos`/`Coeranus`:
      3-way split (`Coeranus (Lycian warrior)`, `Coeranus (charioteer of Meriones)`, `Coeranus (father
      of Polyidus)`), `Coeranos` merged into the first via an `entity_aliases` row (also fixed a
      reversed `Polyidus parent_of Coeranus` edge — should be the father→son direction). `Astyoche`:
      split the 2 remaining meanings J3c had flagged but not named — `Astyoche (daughter of Phylas)`
      (Tlepolemus's mother), `Astyoche (daughter of Niobe)`, `Astyoche (daughter of Actor)` (mother of
      Ascalaphus/Ialmenus) — zero bare `Astyoche` rows remain. `Aeneas`/`Ilus`: all 3 flagged rows
      actually cite passages naming **Iulus** (Ascanius), not the unrelated Trojan `Ilus` — renamed to
      the already-existing `Ascanius` entity. `Megaera`/`Megara`: confirmed the real Fury `Megaera`
      (`Sky parent_of Megaera`) is untouched; the 8 rows for Heracles's wife (every citing passage
      spells her "Megara") were retitled to a new `Megara` entity. `python -m audit --candidates`:
      A1 40→39, A3 99→96. [DEVIATED - see DEVIATIONS.md #DEV-089] **Landed 2026-07-26**, bundled
      with J1/J2/J3f/J3g in one Track I pass — see J1c for the full sequence (seedgen → reseed →
      audit → eval, zero stable regressions vs `p3-j3-batch`). Post-reseed `--db` audit: A1 39
      (matches candidates-mode), A3 1 finding (`Eurymachus⇄Polybus`, pre-existing and unrelated to
      any J1/J2/J3f/J3g/J3h edit — waived per DEV-089 with the fix deferred to J4a-8).

### J4 — DEV-069: Q9 Zeus→Chaos lineage gap (both J4a and J4b done: J4a landed 2026-07-26/DEV-090; J4b decided 2026-07-26/DEV-091, deferred to P5b)
> Full technical write-up (root causes, live-verified evidence, decision options): `docs/DATA-GAPS.md` GAP-001.
- [x] **J4a** [DEVIATED - see DEVIATIONS.md #DEV-090] — **DECIDED 2026-07-23; discriminator AMENDED
      2026-07-26 (ADR-020 / `docs/DATA-GAPS.md` GAP-001), IMPLEMENTED AND LANDED 2026-07-26 as
      DEV-090.** Chose option (a): allow >1
      canonical `parent_of` edge per child for genuine joint parentage. The discriminator in
      `resolve_canonical_edges()` is **four-part, all four required**, over **co-mention pairs** —
      two distinct parents of one child sharing a `(source_id, passage_ref)`, every unordered pair
      where a passage co-names 3+ (the old "3+ ⇒ collapse" clause does **not** survive): (1)
      **contested-aware**: `is_contested=true` rows excluded from couple candidacy, evaluated *per
      row, not per parent*; (2) **winner-anchored**: the pair must contain `_pick_winner`'s winner
      (unmodified — spine order, alphabetical within the spine source; no spine ⇒ most distinct
      sources, then alphabetical), capping every child at 2 parents; (3) **corroboration-ranked**
      tie-break (most distinct sources → spine rank → alphabetical); (4) **deny-listed** (hand-
      maintained not-a-couple list, seeded with Io). **Rules 1×2 interact:** a winner named only in
      flagged rows can never couple, which is why `Helen → Leda` alone — intended, and it must be
      preserved in tests. The originally-decided bare co-mention count is
      **superseded** — measured, it gives children up to 6 parents, injects false edges, adds 6 cycles,
      and mis-couples Io (the entity filter drops `Piren` *before* the count). Pairs must be
      formed **pre-dedup** (`_filter_and_dedup` keeps only the first row per
      `(from, relation, to, source_id)`, so a later co-naming passage is lost — 34 children).
      **Offline-only, no DDL, no runtime code** (`relationships` already permits multiple edges per
      child), but **not resolver-only** — it also touches `relationships_gen.py`,
      `conflict_detector.py` and `drop_accounting.py`/A2r. Measured by simulation:
      the live graph has **0** children with two parents; **472** regain a co-parent (the earlier
      "442" used unrecorded co-mention semantics — **re-measure against the real code and record
      what it produces**). Option (b) (defer to P5b) rejected. **Re-measured against the real code
      (DEV-090): 472 exactly — matches the simulation.**
      **Landing scope also covers GAP-001 Root cause 3** (the other half of the loss): a per-row
      dropped-parent audit check (A2r contract, alongside `drop_accounting.py`) + a same-source
      qualifying condition in `conflict_detector.detect_conflicts` for `parentage`. ⚠️ **Scope
      reality:** of the **612** rivals still collapsed after the carve-out, that detector change
      reaches only the **145** in single-source groups; the other **467** are in groups that already
      clear the ≥2-source gate — candidates are emitted for them *today* and they stall at ADR-004
      review. The promotion gate is unchanged and unowned, so **J4a landing does not make parentage
      conflicts user-visible** — confirmed in the DEV-090 landing notes, exactly as predicted.
      Expected A3 to report **1 new cycle** (`Salmoneus → … → Enarete → Salmoneus`, a latent reversed
      edge the restored co-parent exposes) — this cycle **was found (simulated) and fixed before the
      first reseed** (J4a-8, an entity split not a reversal), so the **live** A3 count never actually
      reached 2; it stayed at the pre-existing, already-waived baseline of **1**
      (`Eurymachus ↔ Polybus`). Measured at the **post-resolver `parent_of`** layer throughout. Quote
      the layer whenever citing A3 here; the candidate-layer counts (62 raw, 93 post-split via
      `audit --candidates`) and the "0 live cycles" exit criterion measure different graphs and are
      not comparable to these.
      **Landed through a Track I pass (DEV-090):** `seedgen --strict` → `reseed-local.sh` → `python -m
      audit --db` (A1 39 pre-existing/unrelated, A3 clean-or-waived at 1, A4 116 unchanged, A5 clean
      — see the note below on A5's own pre-ADR-020 invariant needing a fix, A6 candidates-only 697
      rows/612 pairs) → `runner --runs 3` → `compare.py` vs `p3-j1j2j3fgh-batch` → **zero stable
      regressions**, MIXED actually improved 50%→100% once a same-day regression (below) was fixed.
      ⚠️ **A5 needed its own fix, discovered live, not anticipated by ADR-020 or this checklist:**
      `ingestion/audit/integrity.py`'s E2 check asserted "zero children with >1 `parent_of` parent" —
      a pre-ADR-020 invariant, now structurally false by design for every couple. Post-reseed `--db`
      showed exactly **472** A5 findings (one per couple) before raising the threshold to >2 (leaving
      `married_to`/`killed_by` at >1, unaffected by ADR-020); 0 after. **A regression also needed
      fixing before landing could be called clean:** the first eval pass showed a real, gate-blocking
      stable regression on Q12 (MIXED) — an LLM per-request token-limit failure, root-caused to
      `MixedQueryHandler`/`SqlQueryHandler` feeding the *entire*, uncapped SQL row set into their
      LLM-facing prompts (only the `DebugCapture` display copy was ever row-capped). ADR-020's
      legitimate branching was the first thing to push a real query's row count high enough to
      matter. Both handlers now cap at `DebugCapture.SQL_ROWS_CAP` before building their prompts, not
      only before the debug-capture copy — `:core-api:test` 178/178 green (later 180/180 after
      DEV-092 added 2 more). Full account: DEVIATIONS.md #DEV-090. **Committed** (`b26e69b`, `201eac8`).

  **J4a work items** (ADR-020 *Traceability* names each of these; none is optional) — **all landed
  2026-07-26, DEV-090**:
  - [x] **J4a-1** — `canonical_edge.py`: the four-part rule in `resolve_canonical_edges()`; `RelRow`
        gains `is_contested`; `_pick_winner` **stays unmodified** (rules 1×2 depend on it not
        consulting the flag).
  - [x] **J4a-2** — `relationships_gen.py`: pre-dedup co-mention plumbing (pairs formed on the
        entity-filtered but **pre-dedup** rows, via a new `_filter_by_entities`/`_dedup` split;
        `_filter_and_dedup` kept as a back-compat wrapper). **Did not widen the dedup key** — `A2`'s
        drop accounting was instead updated to build pairs the same pre-dedup way, so it stays
        accurate rather than silently drifting.
  - [x] **J4a-3** — the **deny-list**: lives at `ingestion/extraction/parentage_deny_list.json`
        (mirrors `known_aliases.json`'s convention), loaded via `canonical_edge.load_deny_list()`,
        seeded with **Io**.
  - [x] **J4a-4** — `conflict_detector.detect_conflicts`: same-source qualifying condition for
        `parentage` (reaches the **145** single-source rivals; emits `trust_tier=3` candidates only —
        the ADR-004 promotion gate is unchanged).
  - [x] **J4a-5** — the per-row dropped-parent check landed as new audit check **A6**
        (`ingestion/audit/dropped_parents.py`), auto-discovered by `python -m audit`. Live count on
        the real, post-split data: 697 dropped rows / 612 distinct child+parent pairs, 694 without
        existing promoted `variant_claims` coverage.
  - [x] **J4a-6 — TDD, and the one existing test was *rewritten, not deleted*:**
        `test_gyes_shape_same_source_multi_value_ties_break_alphabetically` renamed to
        `test_gyes_shape_same_source_couple_kept_both_parents` and now asserts the couple outcome.
        New tests pin: `Cronus`/Gyes-shape → couple kept, couple capped at 2 with an unrelated third
        candidate present, `Hellen → Deucalion + Pyrrha` (rule 1), `Helen → Leda alone` (the
        rules-1×2 corollary), `Heracles → Alcmena + Zeus` (rule 3, corroboration ranking), `Io → one
        father` via both a synthetic and the real deny-list file (rule 4), and `married_to` staying
        unaffected — plus integration-level tests in `test_relationships_gen.py` (including the
        literal pre-dedup "34 children" scenario) and `test_conflict_detector.py` (the Io
        "not detected" test rewritten to assert it now *is*, scoped to `parentage` only).
        273/273 ingestion tests green.
  - [x] **J4a-7** — `canonical_edge.py`'s module docstring rewritten: no longer cites Gyes as a
        *contested* example (it documents the couple case and the four-part rule instead).
  - [x] **J4a-8** — traced the predicted cycle in the corpus before touching anything: every edge is
        independently well-attested; the cycle is an **entity conflation, not a reversed edge**
        (DEV-068's *other* known A3 shape) — `Deimachus` conflated Neleus's son (Pylian generation)
        with Enarete's father (Aeolid generation, `apollodorus_bibliotheca_frazer1921.txt [1.7.3]`
        vs `[1.9.9]`). Split into `Deimachus (son of Neleus)` / `Deimachus (father of Enarete)`,
        repointed all 3 referencing relationship rows. Fixed **before** the first reseed, so the
        predicted A3 1→2 never happened live — it stayed at 1 (the pre-existing, unrelated,
        already-waived `Eurymachus⇄Polybus`).
  - [x] **J4a-9** — re-measured against the **real** code: **472** children regain a co-parent (exact
        match to the simulation), max 2 parents per child (no exceptions), post-resolver cycle count
        1→2 in simulation (confirmed by directly re-running `find_cycles` over the resolved graph,
        naming the exact predicted cycle) but **1** live post-reseed (J4a-8 fixed it first). Recorded
        in `docs/DEVIATIONS.md` #DEV-090, not #DEV-088 (DEV-088 remains the pre-implementation
        amendment record).
- [x] **J4b** [DEVIATED - see DEVIATIONS.md #DEV-091] — decided whether `Chaos → Earth`'s
      **cosmogonic (non-parentage)** relation is modeled at all in P3. **Deferred to P5b, waived.**
      Re-verified the corpus directly (`hesiod_theogony_evelynwhite1914.txt [104]-[121]`) before
      deciding, not just against GAP-001's prior quote of it: Chaos and Earth arise independently
      ("came to be... next... came to be"), not as parent and child — no `parent_of` edge should
      exist here, so option (a) ("model a new relation") is the only live path, and it's genuinely
      new schema/prompt-modeling work (deciding how many other Theogony entities get it, a
      `SchemaIntrospector`/`TextToSqlAgent` few-shot update, a two-relation-type `WITH RECURSIVE`
      union) — scoping that down to make only Q9 pass would be the "patch data to pass one query"
      anti-pattern this project's conventions forbid. GAP-001 status + Recommendation + the decision
      block under Root cause 2 all updated to record this.
- [x] **J4c** [DEVIATED - see DEVIATIONS.md #DEV-090] — ran through Track I and recorded Q9's live
      output (`evaluation/results/2026-07-26T15-03-32Z__b26e69b__p3-j4a-joint-parentage-fixed/`).
      **Q9 failed on content, exactly as predicted — not treated as a success condition.** Route ✓,
      author ✓, content ✗ (2/3, stable-fail). The traversal reaches `Cronus` and `Earth` (the winning
      half of the restored Sky/Earth couple) instead of dead-ending at Cronus, and the composed answer
      even narrates on to `Chaos` via RAG's conflict-aware backstop — but the required `Ouranos`
      keyword never appears: `Sky`, `Heaven` and `Uranus` are still three separate confirmed entities
      (`Heaven` still carries `Earth` as its own parent) and the restored co-parent edge attaches to
      `Sky` — needs Track J5, not J4a. `Chaos` needs J4b, still deferred. DATA/MIXED showed **zero
      stable regressions** (MIXED actually improved). **Did not edit the keyword list** (a keyword
      edit is only an eval-bug fix under DEV-050 when the keyword is *wrong*; here it is right and
      the data is missing).

### J5 — `Sky` / `Heaven` / `Uranus` duplicate-entity merge (GAP-001 standing blocker; previously unowned) — LANDED 2026-07-26, DEV-092
> Split out of J4c because it is J1-shaped work that **J1 did not cover and A1 cannot find** — it had
> no checklist item in any TODO until now.
- [x] **J5a** [DEVIATED - see DEVIATIONS.md #DEV-092] — merged the three separate confirmed entities
      into one canonical **`Ouranos`** (`type=primordial`, reconciling `Sky`'s inconsistent
      `other_god`), following the DEV-043 merge-at-candidate-layer + `entity_aliases` pattern.
      ⚠️ **Correction to this item's own premise**: "`Heaven` carries `Earth` as its own parent" is
      **not a data error** — re-verified against `hesiod_theogony_evelynwhite1914.txt [104]-[121]`
      ("And Earth first bare starry Heaven... to cover her on every side"): Earth parthenogenically
      bearing Ouranos before later marrying him is the actual, correct cosmogony. Left untouched, only
      renamed. **A genuine error was found and fixed instead**: `Uranus`'s only edge
      (`Uranus parent_of Pontus`, malformed `passage_ref`) contradicted the corpus — Pontus is
      Earth's parthenogenic child alone (`Earth parent_of Pontus` already correctly existed) —
      dropped rather than carried forward. **Canonical-name decision** (a real judgment call, made
      without asking first — see DEV-092's *Reason* for the full justification): `Ouranos`, not
      `Uranus`, reversing a pre-existing but wrongly-directed `Ouranos→Uranus` alias row, because
      neither spelling appears anywhere in the corpus (verified: 0 hits both, across all six `.txt`
      files) and `Ouranos` is the only choice that makes the literal gold-question keyword
      achievable at all, while also matching this project's existing Greek-canonical convention
      (`Heracles`, `Odysseus`, `Athena`, `Oceanus`). ⚠️ **A1 confirmed it never flags this pair**, as
      predicted — the merge needed this explicit item, not an audit re-run.
- [x] **J5b** [DEVIATED - see DEVIATIONS.md #DEV-092] — re-ran J4a's measurements post-merge: **472
      children with 2 parents, unchanged**; max-2 invariant holds; **1** post-resolver cycle,
      unchanged. `Cronus`'s couple still resolves to `{Earth, Ouranos}`, exactly as predicted the
      *mechanism* changed from a spine-rank tie-break (two separate 1-source pairs) to outright
      corroboration-count (one pair now attested by 2 distinct sources) — same outcome, no code
      change needed, `resolve_canonical_edges()` itself is untouched.
- [x] **J5c** [DEVIATED - see DEVIATIONS.md #DEV-092] — re-checked Q9's `Ouranos` keyword live.
      **First pass still failed** — traced to a second, previously-unnoticed row-cap defect
      (DEV-090's flat row-count cap could exhaust its budget on repeated citations of
      `Earth`/`Cronus` before ever reaching `Ouranos`, alphabetically later in `ORDER BY name ASC`);
      fixed (`dedupeByName` in both `MixedQueryHandler`/`SqlQueryHandler`, TDD-first, `:core-api:test`
      180/180 green) and re-verified: **Q9 now stable-pass 3/3** — route ✓, author ✓, content ✓,
      both `Ouranos` and `Chaos` genuinely appear in the composed answer (`Chaos` via RAG's retrieved
      cosmogony context, not a fabricated edge — J4b's deferral stands, untouched). Zero stable
      regressions; **overall eval reached 12/16 = 75%, the P1 target, for the first time.**
      `gold-questions.json` was never edited.

---

## Definition-of-done checklist (mirror of TODO2.md Stage P3)

- [x] `python -m audit` runs end-to-end (A1–A5 registered, A3 = existing `cycle_check`; **A6 added by
      J4a/DEV-090**, the per-row dropped-parent check), emits `reports/<date>.md` + findings JSON,
      exits non-zero on un-waived findings. [DEVIATED - see DEVIATIONS.md #DEV-070, #DEV-071,
      #DEV-072, #DEV-073, #DEV-074, #DEV-075, #DEV-090]
- [ ] All five (now six) checks **clean or explicitly waived with a written note**. [DEVIATED - see
      DEVIATIONS.md #DEV-089, #DEV-090, #DEV-092] Currently (post-J5 landing, live `--db`,
      2026-07-26): **A3 clean-or-waived** (1 finding — `Eurymachus⇄Polybus`, pre-existing/unrelated to
      any Track J batch, waived per `ingestion/audit/audit-waivers.json`; unaffected by the
      Sky/Heaven/Uranus merge), **A5 clean** (472 findings before its DEV-090 threshold fix, 0 since,
      still 0 after J5), **A4 clean** (116 db relations, unchanged); **A1 39 pairs** still un-triaged
      (permanent long-tail — A1 only suppresses documented aliases, never "reject, distinct"
      outcomes, so this will never reach literal zero without per-pair waivers; confirmed it never
      flagged Sky/Heaven/Uranus either, per J5a); **A2** not re-run in `--db` mode this pass; **A6**
      candidates-only, 684 real findings (612 distinct dropped-parent pairs, unchanged by the merge)
      — by design (GAP-001 Root cause 3's promotion half is unowned, P4 work), not something this box
      expects to reach zero. **Track J itself is now fully closed for P3** (J4a/J4b/J5 all landed and
      committed) — box stays open permanently by design on A1's and A6's residue alone; I7 (commit)
      is no longer a blocker, everything through DEV-092 is committed.
- [x] 29 (grown to 48 live) fuzzy-dup pairs triaged (merge+alias or reject-with-note) — J1, DEV-084.
      [x] 203 flagged relationships triaged (promote-with-fix or reject-recorded) — J2, DEV-085.
- [x] DEV-068's 3 conflation cycles resolved (entity split) or waived; **A3 `parent_of` graph clean**.
      [DEVIATED - see DEVIATIONS.md #DEV-078, #DEV-079, #DEV-080, #DEV-081, #DEV-082, #DEV-083] —
      all 3 resolved by split (plus 2 more discovered along the way: `Agastrophus`/`Paeëon` a
      reversed edge, `Hellen`/`Helen`/`Helle` a 3-way conflation); **A3 confirmed 0 live cycles**
      after the second Track I pass.
- [x] **J4a / ADR-020 joint parentage landed** [DEVIATED - see DEVIATIONS.md #DEV-090]: four-part rule
      + pre-dedup pairs + deny-list + same-source detector condition + per-row dropped-parent record
      (new check A6), through one Track I pass with **A3 clean or waived** (live count stayed at the
      pre-existing baseline of 1 — the predicted new cycle was fixed as an entity split, J4a-8, before
      the first reseed), counts re-measured against the real code (472 children, exact match to the
      simulation), zero stable eval regressions (a same-day token-budget regression on Q12 was found
      and fixed in the same pass — DEV-090), and the run notes stating plainly that **parentage
      conflicts are still not user-visible** (the 467 already-emitted candidates stall at the unowned
      ADR-004 promotion gate — GAP-001 option a′, carried to P4). **Committed** (`b26e69b`, `201eac8`).
- [x] **J4b** decided [DEVIATED - see DEVIATIONS.md #DEV-091]: deferred to P5b, with a written waiver
      + GAP-001 status update (both in `docs/DATA-GAPS.md` Root cause 2).
- [x] **J5** [DEVIATED - see DEVIATIONS.md #DEV-092] `Sky`/`Heaven`/`Uranus` merged into canonical
      `Ouranos` + `entity_aliases` rows added. Also fixed a second row-cap defect the merge exposed
      (`dedupeByName` in both SQL-facing handlers) — see J5c above for the full account.
- [x] DEV-069's Q9 itself: **went green after J5 landed — recorded as a genuine pass, not treated as
      the original pass/fail-gate exemption anymore.** Q9's live output is recorded (route ✓, author
      ✓, content ✓ — stable-pass 3/3, both `Ouranos` and `Chaos` genuinely present in the composed
      answer) in `docs/DATA-GAPS.md` GAP-001. Its keywords were never edited at any point.
- [x] `relation_aliases` **V17** live; `relation_normalizer.py` mirrors `claim_type_normalizer.py`;
      `relationships_gen.py` normalizes + swaps `from`/`to` on `inverse` (TDD green). [DEVIATED - see
      DEVIATIONS.md #DEV-072, #DEV-076]
- [x] `SchemaIntrospector`'s advertised relation vocabulary **confirmed shrunk** (before/after counts
      recorded). [DEVIATED - see DEVIATIONS.md #DEV-076] — 124 → 116 distinct relations live.
- [ ] Full fix-loop pass: `seedgen --strict` → `reseed-local.sh` → `audit` **clean or explicitly
      waived** → `runner --runs 3`
      → `compare.py` vs P2-accepted → **DATA/MIXED ≥ baseline, zero stable regressions**; results dir +
      candidates + migrations committed together. [DEVIATED - see DEVIATIONS.md #DEV-089, #DEV-090,
      #DEV-092] **Mechanism proven five times now** (DEV-076, DEV-083, DEV-089, DEV-090, DEV-092 —
      all zero stable regressions; DEV-090/DEV-092 additionally proved the loop catches *real*
      regressions, not just data edits — two separate application-code row-cap defects, both found
      via the eval and fixed before landing). **Overall eval reached 12/16 = 75%, the P1 target, for
      the first time**, in the DEV-092 landing pass. **The commit half of this line is now done** —
      every Track I pass through DEV-092 is committed (`dc22459`, `b26e69b`, `201eac8`, `5eed421`,
      `35fb379`), migrations/results dirs/waiver file/core-api changes included. Stays unchecked
      purely because "audit clean" here means *all six* checks clean-or-waived **together**, and
      **A1/A6 both carry real, permanent-by-design findings** (long-tail fuzzy-dups for A1, unowned
      P4 promotion backlog for A6) that will never literally reach zero — this box cannot be ticked
      as worded without either a policy change (accept a standing category-level waiver for A1/A6)
      or working through A6's backlog in P4.
- [x] DEV-070..DEV-076+ logged in `DEVIATIONS.md`; `TODO2.md` + `IMPLEMENTATION_PLAN_PHASE2.md` P3
      annotated per protocol; ADR-019 follow-up DEV-number reconciled. Logged through **DEV-092** as
      of this check.
- [x] `./gradlew :core-api:test` green (no Kotlin change expected — SchemaIntrospector verification
      only; run it to prove no regression from the reseeded vocabulary). Re-verified against the
      *current* (three-times-regenerated) `V10`/`V11` migrations — `BUILD SUCCESSFUL`. **Re-verified
      again after DEV-090 and DEV-092**, both of which — unlike prior passes — needed real Kotlin
      changes: 180/180 tests green (178 + DEV-092's 2 new `dedupeByName` tests).
