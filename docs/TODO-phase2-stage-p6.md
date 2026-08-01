# Stage P6 — Entity identity: namesake splitting, resolution provenance, and the merge gate

Implements **ADR-022** (`docs/adr/adr-022-entity-identity-and-namesake-resolution.md`). Closes
`docs/DATA-GAPS.md` **GAP-009** (fuzzy/alias false-positive merges) and **GAP-010** (exact-name
namesake collisions) — for existing data *and* for entities that do not exist yet.

> **P6 runs OUT OF ORDER: it interrupts Stage P5 *inside* Track C1.** Numbered P6 because it was
> scoped after P5, executed before P5 finishes. This follows P5's own precedent — see
> `docs/TODO-phase2-stage-p5.md` → *Track order*, where E5 and A9 run ahead of Track A for verified
> reasons.
>
> **Interrupt point: after Track C1 batch 3** (7 of C1's 100 passages adjudicated), **before Track C1
> batch 4.** C1 is *not* finished first — the whole argument below is that every further batch grows
> the re-key exposure and spends adjudication against identities P6 corrects, and C1's remaining ~93
> passages are batches like any other. `TODO-phase2-stage-p5.md`'s *Track order* block and its **C1**
> item carry the matching gate.

---

## Context — why this stage exists, and why now

Both gaps have one root cause: **entity identity is decided by string matching, silently, with no
evidence artifact and no review gate.** The full argument is in ADR-022 *Context*; the operational
summary is:

- `EntityResolver.resolve()` matches exact → `known_aliases.json` → rapidfuzz@88 and returns a
  canonical string. It does not know which passage the name came from, and it has no access to the
  confirmed entity set.
- `relationships` inherits that decision **with no human gate at all**. `variant_claims` inherits it
  through a gate that reviews *what the claim says* and takes *who the subject is* as given.
- Track C measured the cost: **≥82 confirmed collisions across the first 7 passages**
  (DEV-136/137/138), 20-30% of every batch's rejections and the largest single rejection cause in
  each one. Each is found by hand, by cross-referencing live `entities`/`relationships` per row.

### The class-1 set — five defects already in live data

Enumerated **once, here**. Every other statement in this repo about "the already-live defects" refers
to this table rather than restating a count; it is the set G4 fixes and the sole reason this stage
interrupts P5 at all.

| item | defect | table | rows | gate it got past |
|---|---|---|---|---|
| **G4.1** | `Cronus parent_of Leonteus` — should be the mortal `Coronus` (`3.10.8-3.11.1`) | `relationships` | 1 | none — seeded, never gated |
| **G4.2** | Amphitryon conflated with Amphictyon across `2.4.5`, `2.4.6`, `2.4.7-2.4.8`, `1.8.2` | `relationships` | 2-6; the exact count **is** G4.2's own output | none |
| **G4.3** | Perses/Perseus on one entity, **promoted** at `trust_tier=1` (`2.4.5`) | `variant_claims` | 1 | ADR-004's gate — it passed |
| **G4.4** | `Lynceus` @ `2.1.5` — Aphareus's son and Egyptus's son in one entity | `entities` | 1 | none |
| **G4.5** | `Agave` / `Autonoe` carry `subtype='nereid'` while also being Theban royalty | `entities` | 2 | none |

**Five defects, 7-11 live rows, three tables.** Two of the five (G4.1, G4.2) are GAP-009's near-miss
mechanism; three are GAP-010's exact-name mechanism.

> **DEV-138 records "three separate instances" with different membership** — it counts `Lynceus`
> inside its three and names the promoted Perses/Perseus row separately, and it predates
> `Agave`/`Autonoe` being classed as a split rather than a `trust_tier` call. That entry is committed
> and stays verbatim; **this table supersedes its count.**

### Why before the next Track C batch, not after Track C

`build_candidates` applies `resolve()` to segment facts **whether or not they came from the
checkpoint cache**, so a resolver or registry change takes effect on a plain re-run at **zero API
cost**. But it rewrites `subject_name`, which is part of `_CLAIM_IDENTITY`, so
`_write_claims_preserving_review` cannot match the changed rows and reports them under
`WARNING: N reviewed row(s) are no longer produced by extraction`.

Exposure today — construction:
`Counter(r.get('trust_tier', 3) for r in variant_claims_candidates.json)` →
**569 tier-1 + 523 tier-2 = 1,092 decisions**, against 7,429 rows.

That exposure grows with every batch — including C1's own remaining batches, which is why the
interrupt lands at batch 3 rather than at the C1/C2 boundary. Running P6 now costs a bounded re-key
of 1,092 decisions; running it after Track C costs a re-key at maximum volume **and** spends all of
C1 batch 4 through C4's adjudication effort against known-wrong identities.

### The measurement that rules out the obvious fix

Construction: `rapidfuzz.fuzz.ratio(a, b)`, the scorer `entity_resolver.py` uses.

| pair | ratio | what it is |
|---|---|---|
| `Atas` / `Atlas` | 88.9 | confirmed false positive (DEV-137) |
| `Philaemon` / `Philammon` | 88.9 | confirmed false positive |
| `Amphitryon` / `Amphictyon` | 90.0 | confirmed false positive, already live |
| `Rhodea` / `Rhode` | 90.9 | confirmed false positive |
| `Aesacus` / `Aeacus` | 92.3 | confirmed false positive |
| `Coronus` / `Cronus` | 92.3 | confirmed false positive, already live |
| `Perses` / `Perseus` | 92.3 | confirmed false positive, already promoted |
| `Cronos` / `Cronus`, `Athene` / `Athena`, `Ocean` / `Oceanus`, `Iphis` / `Iphitus` | 83.3 | legitimate spelling variants — **already below** the 88 cutoff |

Every confirmed false positive is at 88.9-92.3; every variant the threshold nominally protects is at
83.3, i.e. handled by the curated alias layers, not by the fuzzy step. **Raising the threshold
removes nothing and can only lose recall.** Whether the fuzzy step earns its keep at all is measured
in **G2**, under a pre-registered decision rule — not assumed here.

---

## Standing rules for this stage

P5's cross-cutting rules (`docs/TODO2.md` → *Cross-cutting rules*) apply unchanged. How each binds
here:

### The seeding rule
Two items add rows to a user-visible table and must name their table and expected row count **before
starting**, closing only on an `A16` coverage move stated against the **reachable ceiling**: **G4**
(entity splits) and **G5** (the bounded sweep's splits). Every other item adds no rows and instead
names the seeding work it unblocks.

### The detector budget — **zero spent by this stage**
At most one new `audit/` check module per 250 net rows, with bugfixes to an existing check spending
the same budget. **This stage adds and modifies no `audit/` check.** All new tooling lives in
`ingestion/extraction/`, which is **outside the `audit` package**: `discover_checks()`
(`audit/__main__.py:47`) walks `pkgutil.iter_modules(audit_pkg.__path__)`, so an extraction-side
module is never enumerated and the `NAME`/`run` attribute check is never reached. The invariant is
**location, not the absent attribute** — the same module moved into `audit/` and given a `NAME`
*would* register. Same structural argument P5 Track B1 made for `claim_evidence.py`. E1's "A16 is
the last one" holds.

The recall safety net for G2's change to the fuzzy step is **A1** (`audit/duplicate_entities.py`),
which scans the confirmed set at threshold 88 **and runs a second, transliteration-normalized pass**
(`_translit_key`, DEV-043's Cronos/Cronus lesson). The second pass is the one that carries the guard:
the legitimate variants score **83.3**, *below* 88, so a threshold-only check would be blind to
exactly the recall at risk. Using an existing check as the guard is what keeps the budget at zero.

### The findings rule
- **Class 1 (reaches users now — the only class that interrupts):** the five live defects tabulated
  in *The class-1 set* above. That is **G4**, and it is why this stage interrupts P5 at all.
- **Class 4 (needs new tooling):** everything else. Row-yield hypothesis stated in G5 as the rule
  requires, and stated honestly rather than extrapolated linearly.
- New findings surfaced *during* P6 are routed by the same 5-class scheme into `docs/DATA-GAPS.md`,
  not chased.

### Recorded figures name their construction
Every count in this file states the query or function call that produced it (E3). The DEV entry for
this stage cites a `promotion_log.json` `batchLabel` rather than restating measurements, and stays
under ~4 KB.

### Flyway
V10-V12 are regenerated by `seedgen` while local-only; never hand-edit an applied migration. New
tables would need fresh V-numbers — this stage adds none.

### Live runs
`seedgen`, `scripts/reseed-local.sh`, `python -m audit` against the DB, and the `evaluation/` harness
are **run only on explicit request**. Items below are authored first, run when asked.

---

## Track G0 — Pre-flight: protect the 1,092 existing review decisions

Runs **first**. Nothing that changes `resolve()` may land before this is in place.

- [x] **G0.1** — Snapshot `ingestion/extraction/output/variant_claims_candidates.json` before any
      resolver change (copy alongside, not committed over). → `variant_claims_candidates.pre-p6-rekey.json`,
      7,429 rows, 569 tier-1 + 523 tier-2.
- [x] **G0.2** — `[DEVIATED - see DEVIATIONS.md #DEV-140]` Key-migration helper in
      `ingestion/extraction/claim_evidence.py` (still exposes no `NAME`): maps old→new `_claim_key`
      5-tuples using the ledger's preserved `surface` field, re-applies the carried `trust_tier`, and
      emits the unmapped remainder as an explicit re-review list. Reuse
      `run_extraction._CLAIM_IDENTITY` / `_claim_key` — do not re-derive the identity tuple.
      **Landed with four departures** (DEV-140): the map joins **two** ledgers (pre- and post-change)
      on `(source_id, passage_ref, lower(surface))`, so G1's ledger must be captured *before* G2/G3
      touch `resolve()`; `claim_value` is re-keyed as well as `subject_name`, since relationship-derived
      rows embed the resolved counterpart there and it is part of `_CLAIM_IDENTITY`; a third outcome
      `absorbed` joins carried/re-review, for decisions merging onto a key another decision already
      carries with the same verdict; and `_write_claims_preserving_review`'s drop counter was corrected
      (it could print a negative N and net a genuine loss toward the gate's own pass condition).
- [x] **G0.3** — Record the migration in `ingestion/audit/promotion_log.json` under its own
      `batchLabel` (`p6-g0-identity-rekey`). A re-key is a decision about promoted rows and earns the
      same audit trail as a promotion. **Authored and unit-tested (`record_key_migration`); not yet
      executed** — no resolver change has landed, so there is no rename to record. Runs with G3.
- [x] **G0.4** — Unit tests for the migration: a renamed subject carries its tier; an unmapped row
      appears in the re-review list and **never** silently keeps or loses a tier.
      → `ingestion/audit/tests/test_claim_rekey.py`, 18 tests.

**Exit:** the post-run `WARNING: N reviewed row(s) are no longer produced` count is **0**, or every
remaining row is listed by name for re-review. Tier counts before/after (569 / 523) are preserved or
explicitly accounted for, row by row.

> **Exit status:** the machinery is in place and verified on a no-op (the snapshot migrated against
> itself carries all 1,092 decisions, 0 re-review, `accounted` true). The exit itself is **pending
> G1/G3** — it can only be evaluated against a run in which identities actually change. Note that
> "before/after 569 / 523" is the *file's* count: a plain re-run today writes 572/523, because 3
> duplicate identity tuples span mixed tiers and a carried tier applies per matching row. That is
> pre-existing behaviour, reproduced deliberately by `apply_key_migration`, not introduced here, and
> **inert downstream** — `seedgen/variant_claims_gen.py:38` collapses exact duplicates before V12, so
> the extra 3 seed nothing. Expect 572/523, not 569/523, when evaluating this exit.

---

## Track G1 — The resolution ledger

- [x] **G1.1** — `entity_resolver.py`: `resolve(name, source_id=None, passage_ref=None)`. **All four**
      call sites in `run_extraction.build_candidates` already hold `source.source_id` and
      `seg.passage_ref` — `run_extraction.py:118` (entities), `:124` and `:125` (the two relationship
      endpoints), `:131` (variant-claim subjects). Thread all four; `:118` is the one that
      establishes the canonical names everything downstream keys on, so missing it silently defeats
      the ledger. → all four threaded via a shared `where` dict; guarded by
      `test_build_candidates_threads_corpus_location_into_the_ledger_at_all_four_call_sites`.
- [x] **G1.2** — `[DEVIATED - see DEVIATIONS.md #DEV-141]` Record **every** decision, not only fuzzy:
      `{surface, canonical, method, score, source_id, passage_ref}` with
      `method ∈ {exact, alias, registry, fuzzy, new}`. Today the alias path that produced
      `Pluto`→Hades leaves no trace at all, and `fuzzy_merges` is printed by `write_output` and then
      discarded. **Two calls the enum did not settle** (DEV-141): a memo hit re-reports the method
      that *established* it (`new`→`exact` thereafter, but `fuzzy`/`alias` keep reporting their
      layer, or G2's denominator and G6's signal both go blind on repeat sightings); and an
      alias-rewritten first sighting is `alias`, not `new`. `registry` is declared with no producer
      until G3.
- [x] **G1.3** — Persist to `ingestion/extraction/output/entity_resolutions.json` from
      `write_output`, next to the three existing candidate files. Keep `fuzzy_merges` and its
      existing print working so nothing downstream breaks. → written blind (no merge-on-write);
      `fuzzy_merges` still appends per merge *event*, so the existing print is unchanged.
- [x] **G1.4** — Unit tests: one ledger row per `resolve()` call; `method`/`score` correct for each
      of the five paths. → 12 tests; four paths asserted, `registry` deferred to G3 (no producer yet).

**Exit:** a re-run of `build_candidates` (cached segments, **zero API cost**) produces a ledger
covering every resolution in the corpus. **Unblocks:** G2's measurement, G6's `resolved_by` signal,
G0's key migration.

> **Updated based on DEV-140.** That ledger run is the migration's **baseline** and must be captured
> and kept **before** G2 or G3 changes `resolve()` — `build_rename_map` joins the pre- and
> post-change ledgers on `(source_id, passage_ref, lower(surface))`, and with only the post-change
> ledger there is nothing to join an old canonical against. The track order already puts G1 ahead of
> G2/G3; this makes the *artifact* (not just the code) a prerequisite. Persist it as
> `entity_resolutions.baseline.json` alongside G1.3's `entity_resolutions.json`.

> **Exit MET (DEV-141/142).** Run performed 2026-07-31 over the cached checkpoint at **0 API calls**
> (all 1,204 segments verified cached `ok` beforehand). Ledger: **34,654 rows**, every one carrying a
> corpus location. Baseline captured as `entity_resolutions.baseline.json` before `resolve()` changed.
> The run also surfaced a re-key backlog G0 did not cover — see DEV-142.

---

## Track G2 — Measure the fuzzy step, then decide

"Root cause first, code fix only if still needed" — the decision rule is registered **before** the
measurement so the outcome is not chosen after seeing it.

- [x] **G2.1** — Re-run `build_candidates` (cached → zero API cost); tabulate ledger `method=fuzzy`
      rows by score band. → 2,066 fuzzy occurrences over **270 distinct merge pairs** (179 @ 88–93,
      91 @ 93–100). The *pair* is the sampling unit: the step decides once per pair, so sampling
      occurrences would over-weight names that merely recur.
- [x] **G2.2** — `[DEVIATED - see DEVIATIONS.md #DEV-143]` Hand-check a **stratified sample of 50** merges against their cited segments, drawn
      across the **whole live band, 88-100** — not 88-93 alone. The confirmed false positives top out
      at 92.3, so 93-100 is precisely the region no evidence covers yet and the region most likely to
      hold *true* merges; sampling only the low band and then deciding for the whole step would
      pre-load the answer. Draw proportionally from `88-93` and `93-100` per G2.1's own band counts,
      and record the two sub-rates separately.
- [x] **G2.3** — **Result: 88–93 → 84.8% (28/33); 93–100 → 41.2% (7/17); whole band → 70.0% (35/50).
      Branch taken: DEMOTE.** The split-decision clause was available (the sub-rates do diverge
      sharply) and was rejected *on the numbers*: 41.2% is cleaner, not clean, and keeping auto-merge
      above 93 would leave ~37 more false merges live among that band's 91 pairs. Apply the
      pre-registered rule to the **whole-band** false-positive rate:
      - **≥70% false positives** → **demote fuzzy from auto-merge to suggestion**. `resolve()`
        registers the name as new and records `method="fuzzy_suggestion"` with the near match and
        score; the curated layers (`known_aliases.json`, `entity_aliases`, the G3 registry) own
        identity outright.
      - **<70%** → keep the fuzzy step and add a `never_merge` list to the registry file for the
        confirmed pairs.
      - The two branches partition every outcome, so there is no "rule not met" case. The one
        degenerate case that **is** reachable: if G2.1 finds **fewer than 50** fuzzy merges in the
        band, the sample *is* the population — say so, report the exact rate rather than a sampled
        one, and apply the same threshold. Do not re-cut the sample after seeing it.
      - If the two sub-rates diverge sharply (≥93 measurably cleaner than 88-93), the honest outcome
        is a **split decision** — demote below the crossover, keep above it — recorded with both
        rates. Choose this only from the numbers, never to avoid a branch.
- [x] **G2.4** — A1 unchanged at 41 waived pairs / 1,990 entities — **no new findings**. The
      substantive recall check was *not* A1 (it scans the confirmed set, which the demote does not
      touch): all **15** sample-confirmed genuine merges lacked a curated alias and were added to
      `known_aliases.json` (58 → 73), each evidence-backed. **Recall guard, either branch:** `python -m audit --only A1`, whose threshold-88 pass
      **and** transliteration pass (`_translit_key`) together cover both the 88-100 band and the
      83.3-scoring variants below it. No new check.
- [x] **G2.5** — Recorded in DEV-143; re-key batches `p6-g2-fuzzy-demote-rekey` /
      `p6-g2-alias-restore-rekey` in `promotion_log.json`.

**Exit, branch-conditional** — "no new A1 finding" is *not* the criterion on both branches:

- **Keep branch:** A1 shows **no new** duplicate-entity finding.
- **Demote branch:** A1 is **expected to report new findings** — every correctly-demoted pair is two
  names at 88.9-92.3 in the confirmed set, which is exactly what A1 scores. The criterion is that
  each new finding is **accounted for**: matched against the G2.2 sample and either confirmed as an
  intended split, or suppressed via `known_aliases.json` where the merge was genuine. An
  unaccounted-for A1 finding fails the exit; a merely *new* one does not.

---

## Track G3 — The passage-scoped namesake registry

The mechanism that survives re-extraction, and the only one that reaches GAP-010.

- [x] **G3.1** — Create `ingestion/extraction/namesake_registry.json`. Entry shape:
      `{name, source_id, passage_ref, identity, reason}` — mirrors `parentage_deny_list.json`
      (ADR-020 rule 4) and `known_aliases.json`; a `reason` is mandatory.
- [x] **G3.2** — Wire the lookup into `resolve()` **first — ahead of the exact-match memo**, not just
      ahead of the alias and fuzzy steps. Keyed `(lower(name), source_id, passage_ref)` →
      `(lower(name), source_id)` → global. Ledger `method="registry"`.
      **Why the memo, and not only the alias/fuzzy steps:** `entity_resolver.py:43-45` checks
      `self._seen` before anything else, so a lookup placed "before the alias step" sits *behind* the
      exact hit and never fires for GAP-010 — where the strings are byte-identical and that exact hit
      is the entire defect. GAP-010 is ≥82 of the confirmed instances, i.e. the majority of what this
      stage exists to fix.
- [x] **G3.2a** — **Make the resolution memo passage-aware.** `_seen` is today one per-run dict keyed
      on `name.strip().lower()`, so caching a registry answer under the bare name would return
      `Pluto (Oceanid)` for *every* later passage — the same defect inverted, one layer up. A
      registry hit is memoized under `(source_id, passage_ref, lower(name))`; surfaces with no
      registry entry keep today's global memo and today's behaviour byte-for-byte. Without this,
      G3.2 alone cannot produce passage-scoped resolution at all.
- [x] **G3.3** — Seed from the **already-adjudicated** evidence in DEV-136/137/138 — nothing
      speculative:
      | passage | shape |
      |---|---|
      | `apollodorus-bibliotheca 3.12.5` | the Priam-sons catalogue (`Atas`, `Lycaon`, `Idomeneus`, `Aesacus`, `Philaemon`, …) |
      | `hesiod-theogony 346-403` | the Oceanid catalogue (`Pluto`, `Urania`, `Europa`, `Rhodea`, …) |
      | `hesiod-theogony 233-269` | the Nereid catalogue (`Agave`, `Autonoe`, …) |
      | `apollodorus-bibliotheca 2.1.5` | the Danaid catalogue (31 of 40 rows rejected — the extreme case) |
      | `apollodorus-bibliotheca 1.2.1-1.2.7`, `2.4.5` | `Erato`, `Amphitryon`, `Idas`, `Oeneus` |
      | `apollodorus-bibliotheca 3.10.8-3.11.1` | `Coronus` |
- [x] **G3.4** — Unit tests beside `ingestion/audit/tests/test_parentage_direction.py`: registry beats
      **exact** match — assert against a resolver that has *already* resolved the bare name in an
      earlier passage, or the test passes vacuously and proves nothing; registry beats **fuzzy**; the
      three-level key falls back in order; an absent entry changes nothing. Plus G3.2a's case: **the
      same surface resolves to different canonicals in two passages within one run**, asserted in
      both passage orders.

**Intended behaviour when a registry `identity` is not yet in `entities`:** those rows land in
`claim_evidence` **bucket `Z_HOLD`** and route to Track D's entity work. A held row is the correct
outcome — strictly better than a confidently wrong one — and it must be stated in the DEV entry so
the hold does not read as a regression.

**Exit MET (DEV-144)** — all **28** confirmed instances from DEV-136/137/138 resolve to their correct
identity on a re-run, verified against the ledger (131 registry resolutions, 40 split identities).
`[DEVIATED - see DEVIATIONS.md #DEV-144]` **Scoped down on evidence:** G2's demote had already
dissolved every *fuzzy* collision in G3.3's table, so the 45 seeded entries cover only genuine
GAP-010 exact-name collisions plus the `Pluto`→Hades alias case. G3.2a is satisfied by the registry
holding **no state** rather than by a scoped memo — same invariant, strictly simpler.

---

## Track G4 — Fix the live defects (findings-rule class 1)

The part that cannot wait, and the reason this stage interrupts P5. Scope is exactly the **five**
defects tabulated in *The class-1 set* above — G4.1 ↔ table row 1, and so on. Nothing else is
class 1.

**Seeding-rule declaration:** target table `entities`, **expected +4 rows** — `Coronus` (G4.1), the
`Lynceus` split (G4.4), the `Agave` and `Autonoe` splits (G4.5) — plus **+1 conditional** if G4.2
establishes that `Amphictyon` is not yet an entity in its own right, for a declared range of
**+4 to +5**. Target table `relationships`, **4-8 rows reassigned, 0 net added** (1 from G4.1, the
rest G4.2's own row-by-row output across `2.4.5`/`2.4.6`/`2.4.7-2.4.8`/`1.8.2`). Target table
`variant_claims`, **1 row demoted 1 → 2, 0 added** (G4.3). Closes on an `A16` re-run showing
`relationships` edge coverage unchanged-or-up and the entity name-space count moved by the stated
amount.

- [x] **G4.1** — `relationships`: `Cronus parent_of Leonteus` → `Coronus`
      (`apollodorus-bibliotheca 3.10.8-3.11.1`). Via `relationships_candidates_cleaned.json` +
      `seedgen`, **never** by hand-editing `V11__seed_relationships.sql`.
- [x] **G4.2** — `relationships`: the Amphictyon/Amphitryon conflation across `2.4.5`, `2.4.6`,
      `2.4.7-2.4.8`, `1.8.2`. Verify each row individually — the two are genuinely different figures
      and some rows may legitimately belong to Amphictyon.
- [x] **G4.3** — The **promoted** (`trust_tier=1`) Perses/Perseus `variant_claims` row at `2.4.5`:
      demote through the keyed workflow (`rejected_keys` + a `promotion_log.json` entry), **never** a
      silent edit. ADR-004's gate binds demotions exactly as it binds promotions.
- [x] **G4.4** — `Lynceus` @ `2.1.5` — entity split: Aphareus's son (the sharp-eyed Argonaut, 3
      sources) vs. Egyptus's son (Hypermnestra's husband, Abas's father — that passage's own central
      plot thread). **Not reachable by a registry key** (both figures share the passage) — fixed by
      hand, per ADR-022's stated limit.
- [x] **G4.5** — `Agave` / `Autonoe` — `entities.subtype='nereid'` is set on figures who are also
      established Theban royalty, so the collision is baked into the entity record from original
      extraction. A split, not a `trust_tier` call.
- [x] **G4.6** — Verify each fix **against the reseeded DB**, not against the candidate files.

**Exit MET (DEV-145)** — all five verified against the reseeded DB. `[DEVIATED - see DEVIATIONS.md
#DEV-145]` **Declaration variance, stated:** `entities` **+5** (inside the declared +4 to +5), but
`relationships` **24 reassigned against a declared 4-8** — G4.2 alone was 15 rows, not 2-6, and G4.5
contributed 4 the declaration treated as entities-only work. **G4.3 needed no action**: G2's demote
plus G3's split had already dissolved the promoted Perses/Perseus row, which now sits at tier 3 under
the correct identity `Perses (son of Perseus)`. A16 gate met (entities 1,990 → 1,995; relationships
coverage 48.92% → 49.1%; contested_collapse 1,035 → 1,026).

---

## Track G5 — Bounded sweep of everything else

- [x] **G5.1** — Run the G1 ledger + G6 risk signal across all **1,059** passages **offline, at zero
      API cost**, and rank. "Offline" means **no LLM calls and no re-extraction** — it does *not*
      mean no segment reading: two of G6's four signals (`surface_absent`, `catalogue_context`) are
      computed *from* segment text, and `assess_collision_risk` takes `segment_text` as a parameter.
      Segments are already on disk and are read through `build_segment_map`, the same path Track C's
      `review_passage` uses. Running the sweep without them would leave G6.2's HIGH rule with neither
      conjunct of either disjunct and silently reduce the ranking to `established_elsewhere` alone —
      the exact hand-ranking this stage exists to remove.
- [x] **G5.2** — **Size N from the exit criterion, not from a round number.** P5 Track D is the
      precedent: its 20-name bound was measurably unreachable and had to be raised to 60 after the
      yield was computed. Fix N only after G5.1 produces a real denominator.
- [x] **G5.3** — Work the top-N by A8 prominence (`audit/prominence.py`), splitting via registry
      entries (one per `(name, passage)`) rather than per-row edits.
- [x] **G5.4** — Everything below the bound is recorded in `docs/DATA-GAPS.md` with its rows-at-stake
      line, per the findings rule's "one destination".

> **Outcome (DEV-147)** `[DEVIATED - see DEVIATIONS.md #DEV-147]` — denominator **3,897** eligible
> tier-3 `(name, passage)` pairs across 1,122 passages. **G5.3's specified A8-prominence ranking
> measured P@10 = 10%, *below* the 27% base rate**, and was replaced by a parent-conflict ranking
> (P@10 = 90%, P@25 = 60%); **N = 25** sized from where precision stops beating 2x base rate.
> Realised 18/25 = 72%; **+18 registry entries** (45 → 63). `entities` **+0** as declared (splits →
> `Z_HOLD`, Track D); A16 relationships coverage **unchanged at 49.1%**, gate met. Residue in
> GAP-010: 3,872 pairs / 7,219 rows / 838 names.

**Row-yield hypothesis, stated as the findings rule requires — and stated honestly.** ≥82 instances
in 7 passages does **not** linearly extrapolate to ~12,000: those 7 were the *highest-yield* passages
by B4's contested-first sort, and the confirmed instances are overwhelmingly **catalogue** passages
(Priam's sons, Oceanids, Nereids, Danaids), which are a small minority of the corpus. G5.1's own
output replaces this guess with a measured denominator before N is fixed. If the sweep's first pass
yields nothing promotable, it is recorded as a dead end rather than iterated — the A13 precedent.

---

## Track G6 — The collision signal for reviewers

In `ingestion/extraction/claim_evidence.py` — no `NAME`, no detector budget spent.

- [x] **G6.1** — `assess_collision_risk(claim, segment_text, ledger, …) -> CollisionRisk`. Four
      signals, each reusing existing machinery:
      | signal | source | catches |
      |---|---|---|
      | `resolved_by` | G1 ledger: surface + method + score | GAP-009 outright — the reviewer currently has no way to see that "Atlas" was spelled "Atas" in the text |
      | `surface_absent` | `claim_evidence._name_present` (`claim_evidence.py:155`) / `parentage_direction._spellings` (`parentage_direction.py:62`) — **reads `segment_text`** | canonical name unattested in its own cited segment (partly why such rows already fall into buckets D/E — this makes the *reason* visible) |
      | `catalogue_context` | distinct proper-name density; long `X, Y, Z and W` conjunction runs — **reads `segment_text`** | the shape **every** one of the 82+ confirmed instances has |
      | `established_elsewhere` | `audit/prominence.py` (A8, degree + mention count) | subject already carries rows/edges from passages disjoint from this one |
- [x] **G6.2** — Risk is **HIGH** when `catalogue_context ∧ established_elsewhere`, or when
      `resolved_by ∈ {fuzzy, alias} ∧ surface_absent`.
- [x] **G6.3** — `review_passage` in `ingestion/notebooks/02_verify_conflicts.ipynb` prints the risk
      line beside the existing `_BUCKET_LABEL` output.
- [x] **G6.4** — Unit tests beside the existing `claim_evidence` bucketing tests.

**ADR-004 Amendment 1 binds this track**: the signal may **order and annotate**; it may **never
promote**. No code path writes `trust_tier=1`, and no code path splits an entity.

**Exit MET (DEV-146)** — both DEV-137-rejected subjects still present at `3.12.5` are flagged HIGH,
0 missed, from the candidate files and ledger alone (no DB read). `[DEVIATED - see DEVIATIONS.md
#DEV-146]` **Measured and recorded:** G6.2's rule scores **65% recall at 19% precision** over the 7
adjudicated Track C1 passages (58 of 60 rows HIGH at `3.12.5`, including `Priam`/`Hector`). An
asymmetry refinement reached 70% precision on `3.12.5` alone but **did not generalise** (45%/29%
across all seven; 0 recall at `233-269`), so the specified rule was **left unchanged** and asymmetry
ships as an *ordering* key (`rank_key`) instead — which is what G5.3 consumes.

---

## Track G7 — Close

- [x] **G7.1** — Standard loop, on request:
      ```
      python -m seedgen --strict
      scripts/reseed-local.sh --local-only
      python -m audit --only A16 --out reports/coverage    # redirected, and run FIRST
      python -m audit
      ```
      `--out` is not optional and the order matters: both invocations write
      `reports/<today>-findings.json` / `reports/<today>.md` from the same date-derived filename
      (`audit/__main__.py:208-210`), so an unredirected `--only A16` overwrites the 16-check report.
      **Gate:** exit 0 with a **non-growing deferral count**, not exit 0 alone.
- [x] **G7.2** — DEV entry (next free `DEV-NNN`), ≤4 KB, citing `promotion_log.json` `batchLabel`s
      rather than restating counts; then `python3 scripts/deviations-index.py` (**never** hand-edit
      the index; `--check` verifies).
- [x] **G7.3** — Flip ADR-022 → **Accepted**, recording what actually landed vs. what it proposed
      (the ADR-020 precedent: the ADR carries its own landing note).
- [x] **G7.4** — Update GAP-009 and GAP-010 in `docs/DATA-GAPS.md` with their closing status and
      their mandatory **"rows at stake"** lines (E6).
- [x] **G7.5** — `evaluation/` harness `--runs 3` vs. the prior result directory. CONFLICT must not
      regress. Never act on a single-run delta; a run containing transport timeouts is invalid, not
      evidence.
- [x] **G7.6** — Hand back to **P5 Track C1 batch 4** (the interrupt resumes *inside* C1, not at C2),
      with the collision signal live in the sprint loop.

---

## Track order

```
G0  -> key migration in place            (nothing may change resolve() before this)
G1  -> the ledger                        (G2, G6 and G0's mapping all read it)
G2  -> measure the fuzzy step, decide    (pre-registered rule; A1 branch-conditional recall guard)
G3  -> the namesake registry             (seeded only from adjudicated evidence; G3.2a re-keys _seen)
G4  -> the five live defects             (class 1; could run earlier, but G3 fixes 2 of 5 for free)
G6  -> the reviewer signal               (before G5, which consumes it)
G5  -> the bounded sweep                 (N sized from G5.1's denominator)
G7  -> close, hand back to P5 C1 batch 4
```

**G0 → G1 → G3 is a hard edge, not a preference.** A registry entry changes a canonical name, which
re-keys review decisions; without G0's migration in place, G3 silently drops part of the 1,092
existing tier-1/tier-2 verdicts through `_write_claims_preserving_review`'s "no longer produced" path.
**G3.2a is inside that edge**, not after it: re-keying `_seen` is what makes a registry entry take
effect at all, so it changes canonical names on the same run G3.2 does.

**G6 before G5** because G5's ranking consumes the risk signal; running the sweep first means ranking
by hand, which is the manual cross-referencing this whole stage exists to remove.

---

## Stage done — 2026-08-01 (DEV-148)

**All eight tracks complete (G0–G7); ADR-022 Accepted.** Evidence, in the order the criteria below
ask for it: all **28** confirmed GAP-009/GAP-010 instances resolve correctly on a plain re-run
(G3, verified against the ledger); all **five** class-1 defects fixed and verified against the
reseeded DB (G4, A16 gate met); the fuzzy step **demoted** at a measured **70.0%** false-positive
rate with its branch-conditional A1 check accounted for (G2); the collision signal live in
`review_passage` with its own **19%-precision** measurement recorded rather than hidden (G6);
GAP-009 **closed** and GAP-010 **mechanism-closed / residue-open**, both carrying rows-at-stake
lines (G7.4); **1,092 decisions = 1,029 live + 63 individually re-queued** (exact). Evaluation
**88% → 92%**, CONFLICT **7/7 → 7/7**, "no stable regressions", zero timeouts. Audit exit 0,
backlog unchanged at 949. **P5 Track C1 batch 4 is unblocked.**

## Stage done when

Every confirmed GAP-009/GAP-010 instance from DEV-136/137/138 resolves correctly on a plain re-run;
**all five** class-1 defects (the *class-1 set* table, G4.1-G4.5) are fixed and verified against the
reseeded DB; the fuzzy-step decision is recorded with its measurement and its branch-conditional A1
check; the reviewer signal is live in `review_passage`; GAP-009 and GAP-010 carry closing status and
rows-at-stake lines; the 1,092 existing review decisions are preserved or individually re-queued;
ADR-022 is Accepted; and **P5 Track C1 batch 4** can resume with identity no longer the largest
rejection cause.

---

## Deviation protocol

Per CLAUDE.md. Each of these needs a `docs/DEVIATIONS.md` entry and inline
`[DEVIATED - see DEVIATIONS.md #DEV-NNN]` markers:

- The P6 interrupt itself — a new stage inserted ahead of an in-flight one — and ADR-022
- The `resolve()` signature change and the resolution ledger (G1)
- The fuzzy-step decision and the branch taken (G2)
- The namesake registry as a new curated-JSON layer in the resolution order, **and the `_seen` memo
  re-key that makes it effective** (G3, G3.2a) — the memo change alters resolution for every
  registry-covered surface, so it is a behaviour change, not a refactor
- Each of the five live-data fixes, with its corpus-count line (G4)
- The key migration and any row that could not be mapped (G0)
