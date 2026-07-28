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
separate registration call, just those two names, to be picked up. All **ten** checks are live:
**`duplicate_entities.py` (`A1`)**, **`drop_accounting.py` (`A2`)**, **`cycle_check.py` (`A3`)**,
**`relation_taxonomy.py` (`A4`)**, **`integrity.py` (`A5`)**, **`dropped_parents.py` (`A6`)**,
**`name_coverage.py` (`A7`)**, **`prominence.py` (`A8`)**, **`claim_type_distribution.py` (`A9`)**,
**`group_inventory.py` (`A10`)**.

**A note on what "reporting-only" has to mean for A8/A9/A10** (Stage P4 Track B9), because the
obvious reading of `contract.py` is wrong: `AuditRun.exit_code` is `1 if any(not f.waived for f in
self.all_findings) else 0` and **ignores `severity`**, so a check cannot emit
`Finding(severity="warning")` and still exit `0` — there is no "tolerated finding" severity.
"Reporting" therefore means these three checks return `CheckResult(findings=(), summary=…)` on
their normal path, with their tables (the A8 ranking, the A9 distribution, the A10 inventory)
going into `summary` and each module's own `--output` JSON artifact — **never** a `Finding`. The
*only* things A8/A9/A10 ever raise as findings are genuine anomalies: A9's mechanically-detected
unmapped formatting-duplicates (the `notable_claim`/`"notable claim"` class — never a semantic
collapse guess, that stays human-reviewed in Track G) and A10's `(a)`/`(b)`/`(c)` invariant
breaks (group-total drift, a broken arithmetic identity, or `zero_promoted` increasing — the
DEV-101/Track C corruption signature). A10's per-group rows themselves — all 835 of them today —
are never findings; only three prior checks (A2, A4, A6) emit one finding per row/label, which is
why those three need standing waiver policies (F0c) to ever reach a clean exit.

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

## `duplicate_entities.py` — the A1 fuzzy-duplicate scan

Formalizes DEV-044's one-off `rapidfuzz` triage scan (same threshold, 88, on lowercased names —
matching `extraction/entity_resolver.py`'s extraction-time dedup) into a reusable, tested,
runner-registered check over the confirmed ~2,000-entity set, plus a transliteration-normalized
second pass for DEV-043's spelling-variant bug class (`Cronos`/`Cronus`, `Athene`/`Athena`,
`Ocean`/`Oceanus`).

**A note on the transliteration heuristic's shape**, since a naive reading of "normalize K↔C,
`-os`↔`-us`, `-e`↔`-a`, `Ou`↔`U`" is a trap: collapsing masculine (`-os`/`-us`) and feminine
(`-e`/`-a`) endings into one shared bucket looks right for the three real DEV-043 pairs, but Greek
mythology routinely reuses a stem across a masculine/feminine pair that are genuinely **different
people** (e.g. a mother and son sharing a name root) — a first pass that merged the two buckets
flagged 150 mostly-false extra pairs on the live data. The buckets stay disjoint (feminine keys
carry an `@f` marker) and a hit requires the normalized keys to be **exactly** equal, not merely
fuzzy-similar — both changes were needed, verified by rerunning the scan against the real
1,969-entity set after each iteration, not just synthetic test fixtures.

A pair is suppressed (never a finding) when it's already documented as one entity under two
names — `known_aliases.json` (always) and, when a DB connection is available, the live
`entity_aliases` table too (both layers only exclude a pair when **both** names are actually
present as entities — e.g. `Jupiter`→`Zeus` never suppresses anything, since `Jupiter` itself was
never extracted as an entity).

```
python -m audit.duplicate_entities --candidates   # full pair list + fuzzy_score + matched_by
python -m audit.duplicate_entities --db           # same, over the live seeded entities table
```

Findings are triage leads for **Track J1** (the 29+ pair backlog in
`entities_fuzzy_duplicates_flagged_for_review.json`) — merge-and-alias or reject-with-a-note, same
as DEV-043's precedent, never decided automatically here.

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

## `drop_accounting.py` — the A2 raw→seeded drop explanation

Explains `relationships_candidates_cleaned.json` (seedgen's actual input, 6,009 rows today) →
seeded `V11` (2,494 rows) by reason, calling `relationships_gen._filter_and_dedup` and
`canonical_edge.resolve_canonical_edges` **directly** rather than re-deriving equivalent logic — if
those functions change, this check's numbers change with them automatically, so it can never
silently drift from what `seedgen` really does. Buckets: **unknown-entity-name** (from/to not in
the confirmed entity set), **exact-duplicate dedupe**, **contested-edge collapse**. The arithmetic
(`raw − unknown_name − exact_dup − contested_collapse == seeded`) always reconciles by
construction; a non-zero residual would itself be a finding (an uncounted drop path this check
doesn't know about yet).

The **unknown-name drilldown** is the highest-value output — every distinct name referenced by a
dropped row but absent from the confirmed entity set is either a genuinely missing/split entity
(the Io/DEV-042 precedent) or the `<UNKNOWN>` extraction placeholder (flagged separately, `info`
severity, since there's no entity to add). Live-verifying this (not just trusting a synthetic test
fixture) surfaced a real, previously-unnoticed gap: **367 distinct names** are referenced by
dropped rows but missing from the confirmed set, including major figures like `Nereus` (105
references), `Doris`, `Styx`, `Ceto`, and `Chiron` — none of them spelling variants of an existing
entity. A much larger missing-entity backlog than DEV-042's single Io case, now feeding Track J.

Unlike A1/A3/A4, `candidates`/`db` aren't independent equivalent sources here — this check explains
a *transformation*, so it always needs the candidate JSON. When a DB connection is also available,
it adds a **drift** check instead of repeating the same breakdown: does the live, already-seeded
`relationships` count still match what regenerating from the current candidates would produce right
now? (Today: yes, exactly — `live=2494`, `drift=0`.)

```
python -m audit.drop_accounting                 # candidates-only breakdown
python -m audit.drop_accounting --db            # + live-vs-regenerated drift check
```

## `relation_taxonomy.py` — the A4 label-canonicalization proposal

`relationships.relation` is 177 distinct free-text strings today: a steep head (`parent_of`,
`killed_by`, `married_to`, `sibling_of`) plus a long tail mixing genuine synonyms/inverses of that
head (`son_of`, `child_of`, `killed`, `father_of`, ...) with real, low-frequency mythological
semantics (`gave_scepter_to`, `abductor_of`, `companion_of`). `classify_relations` buckets every
observed label into **canonical** / **synonym** (same direction, different word) / **inverse**
(same edge, `from`/`to` swapped) / **legit-long-tail** (left untouched, ADR-019 Decision 4).

This is a **reporting** check, not a defect check (`docs/TODO-phase2-stage-p3.md` D4) — its
findings are *proposed* `relation_aliases` rows awaiting human review and Track F's V17 promotion,
not bugs. It deliberately does **not** guess at ambiguous cases: `SYNONYM_ALIASES` only covers
ADR-019's own named examples plus gendered/same-direction variants actually observed in the data.
Different-generation labels (`grandfather_of`, `descendant_of`, `ancestor_of`, ...) are **never**
folded into `parent_of`/`sibling_of` — that would be the same entity-conflation mistake DEV-068
logged, applied to relations instead of entities.

```
python -m audit.relation_taxonomy --candidates   # full per-label table + proposed seed-row SQL
python -m audit.relation_taxonomy --db           # same, over the live seeded vocabulary
```

`to_seed_rows` / `format_seed_rows_sql` extract just the synonym/inverse-bucket labels as
`(alias, canonical, inverse)` tuples, formatted as a pasteable `INSERT INTO relation_aliases ...`
block — Track F's V17 migration ingests this output directly (D3).

## `integrity.py` — the A5 alias/participant/direction integrity gate

**DB-only** — unlike A1/A3/A4, `entity_aliases`, `myth_participants`, and the direction invariants
below have no candidate-JSON equivalent to check against, so a `--candidates`-only run reports a
no-op ("no db connection given"), not a failure.

Two groups of checks, both cheap to run on every batch:

- **Referential integrity (E1)**: a dangling `entity_aliases.entity_id`, an alias string that
  shadows an existing canonical `entities.name`, an orphan `myth_participants.entity_id`. All three
  are already enforced by FK/schema constraints — implemented anyway as a defensive standing
  safety net (a future schema change or a superuser bypass would otherwise go unnoticed), the same
  posture A1/A3 already take elsewhere in this package.
- **DEV-040's direction invariants, re-run (E2)**: zero children with >1 distinct `parent_of`
  parent, zero spouses with >1 distinct `married_to` partner, zero victims with >1 distinct
  `killed_by` killer (together: no `WITH RECURSIVE` branching risk — DEV-054's root cause class),
  plus a defensive re-check that every `entities.type` is still one of the 8 `chk_entities_type`
  values. Reuses `cycle_check`'s own `Edge`/`_query_edges` directly rather than re-querying the
  relationships table a second way.

Today: **clean** — 0 findings against the live DB (27 `entity_aliases`, 22 `myth_participants`,
2,494 `relationships`, all passing every check).

## `name_coverage.py` — the A7 corpus-vs-candidates coverage check

**Candidates-only, and needs the corpus.** Added after DEV-098, which found that the extraction
model wrote every `Ares`/`Mars` as **`Arges`** — so the candidate rows held 71 `Arges` and **zero**
`Ares`, and `Ares`, a confirmed `olympian` since V10, was seeded with **no relationships at all**.

The point of this check is that **A1–A6 structurally could not see that**:

| check | why it missed the `Ares` erasure |
|---|---|
| A1 | compares *confirmed* names to each other; `Arges` was never a confirmed entity |
| A2 | *did* list `Arges` — but as a **missing entity to add**, the opposite of the truth |
| A3/A5 | reason over edges that exist; an entity with no edges is invisible |
| A4/A6 | operate on relation labels and dropped parents — neither is name-coverage |

The signal none of them look at is the **corpus itself**: an entity the sources name constantly that
no candidate row references. For each hit the check also names the likely **corruption partner** — an
unconfirmed name that carries rows and is fuzzy-similar (`rapidfuzz`, A1's 88 threshold). Run against
the pre-DEV-098 data it produces exactly the lead that was missed:

```
208 mentions / 0 rows  Ares <- likely 'Arges' (71 rows, 88.9)
```

Scope limits, all deliberate: the **corpus is not committed**, so a run without it reports "not
evaluated" rather than guessing; **split siblings are grouped by base name** (`Sterope (Pleiad)` →
`Sterope`) and their rows pooled, so a five-way split isn't flagged because one sibling got no rows;
**multi-word names are skipped**, not flagged (`Diomedes of Thrace` never appears verbatim in a
translation); and a **translation-name mismatch is a known false-negative** (Ovid says `Mars`), which
is the safe direction — it under-counts mentions and so under-flags.

The first sweep found **6**, all now worked (DEV-100): three were **not entities at all** —
`Argeiphontes` (a standing **epithet of Hermes**; A1 scores the pair 33.3), `Diomed` (More's
contraction of **`Diomedes`**; A1 misses it at **85.7**, just under the 88 threshold), and
`Acusilaus` (an **ancient mythographer Apollodorus cites**) — the first two now `entity_aliases`
rows via `V14_1`, the third removed outright. `Thisbe` was real and got the rows it was missing
(`Pyramus loves Thisbe` and back, Ovid `4.55-4.80`).

Today: **2 findings, both waived** — `Charybdis` and `Demodocus` are true positives with genuinely
nothing to extract (a sea hazard and a court minstrel; no kinship, marriage or death stated for
either anywhere in the six sources, and no relation in the vocabulary honestly fits). That is the
intended end state for this class: **waive with a written reason, don't invent a relation type to
zero the count** — an audit check must not get to dictate the data model.

## `prominence.py` — the A8 subject ranking (Stage P4 Track B1-B3)

The tranche-selection instrument every P4 batch reads before picking which `(subject,
claim_type)` groups to promote. `IMPLEMENTATION_PLAN_PHASE2.md §5` step 1 and `TODO2.md:389` both
assumed the audit package already emitted a prominence ranking — it didn't (`grep -rn
"prominence\|degree\|rank" ingestion/audit/*.py` returned nothing before this module).

Composite score is deliberately simple: **relationship degree (in + out) + candidate mention
count**, both reported alongside the composite so a reader can see why a subject ranked where it
did — a subject with high degree and no claim candidates is a different signal from the reverse.
Degree comes from the live `relationships` table when a `db_conn` is given, or from
`relationships_candidates_cleaned.json` otherwise. Subject names are resolved through
`known_aliases.json` (candidates-only) and the live `entity_aliases` table (when `db_conn` is
given) before ranking — reusing `duplicate_entities.load_entity_aliases_from_db` rather than
re-deriving alias resolution — so `Sky`/`Ouranos` (DEV-092) merge into one ranked row instead of
splitting one figure's degree across two.

Always reporting-only: `run()` never returns a `Finding`. `python -m audit.prominence` prints the
top-N table and writes the full ranking to `prominence_ranking.json`.

## `claim_type_distribution.py` — the A9 canonical claim_type breakdown (Stage P4 Track B5-B6)

Runs every candidate `claim_type` surface form through `extraction.claim_type_normalizer.normalize`
(reading the live `claim_type_aliases` table, never a hardcoded map — DEV-022's rule) and groups
by canonical, so the **7-member `notable*` family** (`notable_claim`, `notable`, `notable_deed`,
`notable_act`, `"notable claim"`, `"notable act"`, `notable_event` — 648 rows) shows up as one
canonical entry with its surface-form breakdown intact, rather than seven unrelated distribution
rows. This is how the "≥4 canonical claim_types" P4 exit-gate figure gets counted — canonical
values, not raw spellings.

The full raw→canonical→count table is reporting-only (`summary` + `--output` JSON). The **only**
`Finding`s this check raises are a narrow, mechanically-certain class: two raw surface forms that
fold to the same string once whitespace/underscore/case differences are removed
(`"notable claim"` vs `notable_claim`) *and* have no `claim_type_aliases` row connecting them yet
— a formatting variant, not a semantic judgment. Collapsing the full `notable*` family (is
`notable` the same concept as `notable_deed`, or two things?) is deliberately left to a human,
Track G's G1 — the same restraint `relation_taxonomy.py`'s docstring already documents for
relation labels ("guessing here risks making the seed data worse, not better").

## `group_inventory.py` — the A10 per-group inventory (Stage P4 Track B7)

One row per `(resolved subject, canonical claim_type)` group: candidate row count, distinct
`source_id` count, distinct `claim_value` count, promoted-row count, and the subject's A8 rank.
Emitted as machine-readable JSON so Track C's review notebook (C6) can read it directly.

**Reconciliation note on the group total**: the Contracts section's "839 groups" figure is
measured by *raw* `claim_type` (no `normalize()`), grouped by lowercased subject name only. This
module groups by *canonical* claim_type and alias-resolved subject, as B7 instructs, which is a
materially different key — measured live, it comes in at **835**, not 839. All of the difference
turns out to be claim_type normalization alone (exactly the 4 subjects — `Aphrodite`, `Athena`,
`Dionysus`, `Adonis` — that carry both a `birth` and a `parentage` candidate row, which V9_2's
alias merges into one canonical group each); no subject-alias merge changed the count at all,
verified directly rather than assumed. Recorded here rather than silently coding against the
stale 839 figure, per the Contracts section's own preamble.

**Only three things are ever findings, never the 835 rows themselves**: (a) the group total
drifting from this module's own **self-recorded baseline** (`group_inventory_baseline.json`,
committed like `audit-waivers.json`, set on this check's first-ever run and never rewritten
thereafter); (b) the arithmetic identity `groups_with_promotions + zero_promoted == groups_total`
breaking, a pure counting-bug detector; (c) `zero_promoted` **increasing** since the last run —
promotion is monotone, so growth means a promotion was lost, the DEV-101/Track C corruption
signature. A normal **decrease** — what every successful P4 batch produces — is printed as a
trend line against both the last run and the frozen starting baseline, never a finding: a check
that fires on ordinary progress is worse than no check.

## The Flyway checksum trap (shared with Track F)

`scripts/reseed-local.sh` is the only sanctioned way to re-seed `V10`–`V14` after an edit here.
**Never** hand-edit an already-applied migration file and expect Flyway to notice — once applied,
Flyway checksums it, and regenerating the file changes that checksum. On your own local DB,
`reseed-local.sh` clears the relevant `flyway_schema_history` rows first, so this is fine. On a
**shared** database, doing this breaks `flyway validate` for everyone else pointed at it — which is
exactly why `reseed-local.sh` refuses to run without `--local-only` / `ALLOW_RESEED=1`. Never run
`docker compose down -v` as a shortcut either: it drops `narrative_chunks`, whose embeddings cost
real OpenAI API calls to regenerate.

**`V17__create_relation_aliases.sql`** (Track F, DEV-072) is currently in this same free-regeneration
window — it has not been applied to any DB yet (only syntax/semantics-verified via a rolled-back
transaction), so its seed rows can still be freely edited in place as Track D's taxonomy findings
get reviewed/extended. The moment it's applied anywhere (Track I's first reseed), corrections must
switch to an additive follow-up migration (a `V17_1`-style file), exactly like `claim_type_aliases`
(V8_2) and the V10–V12 precedent above.

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
