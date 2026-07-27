# Data Gaps

Documented, deliberately-unfixed gaps in the relational data model or extracted corpus data —
things that are **known and understood**, not silent failures. Each entry records the symptom, the
root cause(s), why it wasn't fixed in the stage that found it, and the decision still needed.
Referenced from `docs/TODO-phase2-stage-p3.md` (Stage P3, Track J4) as the landing place for any
gap deferred to Phase 5b.

| Gap | Summary | Status | Home |
|---|---|---|---|
| **GAP-001** | Q9 cannot reach `Ouranos`/`Chaos` | Closed for everything P3 owned; root cause 3's promotion half (a′) open | P4 (a′), P5b (J4b, waived) |
| **GAP-002** | 367 entities referenced by candidate relationships but absent from the confirmed set | **Open, un-triaged** | Stage P3b |
| **GAP-003** | DATA floor breach — Q6/Q7/Q8 all stable-fail | **Open** — the only failing eval gate | Stage P3b |

---

## GAP-001 — Q9 "Trace Zeus's lineage back to Chaos" cannot reach `Ouranos`/`Chaos`

**Status:** Root cause 1 landed 2026-07-26 (DEV-090); root cause 2 decided 2026-07-26 — deferred to
P5b, waived (DEV-091); root cause 3 partly landed (the detection half, with J4a) and partly unscoped
(the promotion half, still no owner); the standing `Sky`/`Heaven`/`Uranus` blocker landed 2026-07-26
as Track J5 (DEV-092). **Q9 now stable-passes** (route ✓, author ✓, content ✓ — confirmed live,
`evaluation/results/2026-07-26T17-49-26Z__5eed421__p3-j5-ouranos-merge-fixed/`): `Ouranos` is
reachable now that the merge landed; `Chaos` was never expected to be, since root cause 2 was
deferred by design, not by accident. Re-read the per-cause status below before quoting this entry as
progress — Q9 passing doesn't mean every root cause here is closed.
- **Root cause 1 (J4a — joint parentage): DECIDED 2026-07-23, discriminator AMENDED 2026-07-26,
  IMPLEMENTED AND LANDED 2026-07-26 — see ADR-020 (`docs/adr/adr-020-joint-parentage-multi-edge.md`),
  DEV-088 (the amendment) and DEV-090 (the landing).** The four-part discriminator in
  `resolve_canonical_edges()` — contested-aware, winner-anchored, corroboration-ranked, deny-listed
  — is live in the seeded DB. Re-measured against the real code, every headline simulated figure
  matched exactly: **472 children** regain a co-parent, max 2 parents per child (no exceptions),
  **612** distinct rival parents remain dropped. Landed through one Track I pass with **zero stable
  eval regressions** and A3 clean-or-waived (the predicted new cycle was found and fixed as an entity
  split — `Deimachus` conflated two different people — before it ever reached the live DB). A
  same-day regression (an LLM per-request token-limit failure on a real gold question, caused by
  legitimate branching finally exposing a pre-existing uncapped-row gap in two handlers) was found
  and fixed in the same pass — see DEV-090 for the full account. **Committed** (`b26e69b`, `201eac8`).
- **Root cause 2 (J4b — Chaos cosmogony): DECIDED 2026-07-26 — deferred to P5b, waived (DEV-091).**
  No new relation is modeled in P3; a `Chaos → Earth`/`Sky` cosmogonic edge would misrepresent the
  source (Hesiod states they arise independently, not as parent and child) and the alternative —
  an honestly-named non-`parent_of` relation — is scoped as new schema/prompt-modeling work, which
  belongs after P3 per ADR-017 §Decision 4, not as a one-question patch. See the decision block
  under Root cause 2 for the full reasoning.
- **Root cause 3 (dropped rival parents are recorded nowhere): detection half landed with J4a
  (DEV-090); promotion half still open.** Broader than Q9 — it is the second half of the same data
  loss. The per-row dropped-parent record (new audit check **A6**, `ingestion/audit/dropped_parents.py`)
  and the same-source detector condition (`conflict_detector.detect_conflicts`, scoped to
  `parentage`) are both live and reach **145** of the **612** surviving rivals; the other **467** are
  already-detected candidates blocked at ADR-004 review, and that promotion half (option a′) still
  has **no owner and no scope** — it outlives the J4a landing exactly as predicted. A6's live count on
  the real, post-split candidate data: **697** dropped rows (**612** distinct child+parent pairs),
  **694** with no existing promoted `variant_claims` coverage.
- **Standing blocker (`Sky`/`Heaven`/`Uranus` duplicate entities): LANDED 2026-07-26 as Track J5
  (DEV-092).** Merged into one canonical `Ouranos` entity (chosen over `Uranus` specifically so the
  literal keyword is achievable — see DEV-092 for the full reasoning, including reversing a
  pre-existing but wrongly-directed `Ouranos→Uranus` alias). Fixing this exposed a second,
  previously-unnoticed defect: DEV-090's flat row-count cap could still silently drop `Ouranos` from
  a lineage answer, because a `WITH RECURSIVE` traversal returns one row per *citation*, not per
  entity, and heavily-corroborated ancestors (`Earth`, `Cronus`) could exhaust the cap before a
  less-corroborated one was ever reached. Fixed in the same pass (`dedupeByName` in both handlers).
  **Q9 now stable-passes fully** — confirmed live, not assumed.

### Symptom

Gold question **Q9** (`evaluation/gold-questions.json`, DATA category):

```json
{
  "id": 9,
  "category": "DATA",
  "question": "Trace Zeus's lineage back to Chaos.",
  "expected_route": "SQL",
  "required_keywords": ["Cronus", "Ouranos", "Chaos"],
  "sql_must_contain": ["WITH RECURSIVE"]
}
```

`TextToSqlAgent` generates a correctly-bounded `WITH RECURSIVE` query (DEV-069's Rung 1 fix
resolved the earlier `serviceError`/timeout — see `docs/DEVIATIONS.md` #DEV-069). The query itself
is no longer broken. But the traversal dead-ends at `Cronus`: it can never reach `Ouranos` or
`Chaos`, because those edges don't exist in the live `relationships` graph. Route ✓, author ✓,
content ✗ — 2/3 eval dimensions pass, the third fails on missing data, not a code defect.

There are **two separate, unrelated root causes** behind Q9 specifically, both confirmed by direct
inspection (not assumption) — this is why the fix splits into two independent decisions (J4a, J4b)
rather than one. A **third root cause**, broader than Q9, was found while measuring the first: the
rival parents discarded by every contested collapse are recorded nowhere. It is documented below
because it is the other half of the same data loss, and it lands with J4a.

### Root cause 1 (J4a) — single-canonical-parent design silently drops genuine joint parentage

`ingestion/extraction/output/relationships_candidates_cleaned.json` (the candidate layer, before
seeding) genuinely contains **both**:

```
Sky    parent_of Cronus   [apollodorus-bibliotheca, 1.1.1-1.1.7]
Earth  parent_of Cronus   [apollodorus-bibliotheca, 1.1.1-1.1.7]   -- same passage
Earth  parent_of Cronus   [hesiod-theogony,         104-146]
Heaven parent_of Cronus   [hesiod-theogony,         104-146]       -- same couple, `Heaven` duplicate
```

(Four rows, not two — Hesiod states the same couple using `Heaven` rather than `Sky`. That second
pair loses the rule-3 tie-break on spine rank, which is the only reason the restored co-parent is
`Sky`. It is also the `Sky`/`Heaven`/`Uranus` duplicate showing up inside this gap's own headline
case.)

Apollodorus's own sentence (`[1.1.1]`) describes Sky (Uranus) and Earth (Gaia) as a married pair
who *jointly* produced the Titans, Cyclopes, and Hundred-Handers — this is one source stating one
fact with two true parents, not two sources disagreeing about who the parent is.

`ingestion/seedgen/canonical_edge.py`'s `resolve_canonical_edges()` collapses every "contested"
group (≥2 distinct values for the same subject) down to a single canonical edge, so
`WITH RECURSIVE` never has to branch at query time (ADR-007 §6). Its grouping key can't distinguish
"multiple sources disagree" from "one source names two co-parents" — both look identical
structurally (≥2 distinct `from_name` values for the same `to_name`). It always picks exactly one
winner via `SPINE_PRIORITY = ("apollodorus-bibliotheca", "hesiod-theogony", "homer-iliad")`, then
alphabetically among same-source rows.

Directly verified by running the resolver against the current candidate data:

```python
>>> resolve_canonical_edges(rows, alias_map)
Cronus parent_of winners: [('Earth', 'apollodorus-bibliotheca'), ('Earth', 'hesiod-theogony')]
```

`Earth` wins (alphabetically first of the two apollodorus-sourced rows); `Sky`'s edge is dropped
from every seeded/live graph. **This is not unique to Cronus** — the module's own docstring already
names the identical pattern for `Gyes` ("has parent_of candidates from Sky, Earth... and Cronos"),
and by construction it affects **every child of Sky+Earth** — the entire Titan/Cyclops/Hecatoncheir
generation loses one of its two true parents in the queryable graph, not just this one case.

**Decision (made 2026-07-23 — ADR-020; discriminator amended 2026-07-26; implementation pending as
DEV-088):** option (a). Allow >1 canonical `parent_of` edge per child **only** for genuine joint
parentage, told apart from a contest in `resolve_canonical_edges()` by a four-part rule, all four
parts required:

A **co-mention pair** is two distinct parents of the same child whose candidate rows share one
`(source_id, passage_ref)`; where a passage co-names 3+ parents, every unordered pair among them is a
candidate pair (the superseded rule's "3+ ⇒ alternatives" clause does not carry over — rules 1–4 do
that job, and this is what rescues `Hellen`). Pairs are formed pre-dedup. Then:

1. **Contested-aware** — rows flagged `is_contested = true` by the extractor are excluded from couple
   candidacy (that flag is the source naming mutually-exclusive alternatives). Already present on
   every candidate row; previously unused by the resolver. Evaluated **per row, not per parent** — a
   parent flagged in one passage can still couple from an unflagged row elsewhere.
2. **Winner-anchored** — the canonical winner is picked exactly as today by the unmodified
   `_pick_winner` (first spine source that backs any value, alphabetically within it; no spine source
   ⇒ most distinct corroborating sources, then alphabetical); a couple is kept only if the co-mention
   pair *contains* that winner. Caps every child at 2 parents.
3. **Corroboration-ranked** — among qualifying pairs, keep the one attested by the most distinct
   sources, then spine rank, then alphabetical.
4. **Deny-listed** — a hand-maintained not-a-couple list (child, pair, written reason) suppresses the
   known false-couple residue. Seeded with **Io**.

**Rules 1 × 2 interact, deliberately.** `_pick_winner` does not consult `is_contested`, so the winner
may be a parent named only in flagged rows; rule 1 then removes it from every pair and rule 2 makes a
couple impossible, collapsing the child to that lone winner *even when other unflagged parents were
co-named*. That — not an absence of unflagged candidates — is what produces `Helen → Leda only`.

- **No schema/DDL change** — `relationships` (V4) already permits multiple `parent_of` rows per
  child; single-canonical was enforced only in the resolver.
- **Pairs must be formed pre-dedup.** `relationships_gen._filter_and_dedup` keys on
  `(from, relation, to, source_id)` and keeps only the **first** row per key, discarding later
  passages of that source with their `passage_ref`. A co-mention survives only if the passage naming
  both parents is the first one retained for *each* of them; where it isn't, the pair vanishes —
  **34 children** (Agamemnon, Ajax, Antiope, Auge, …). Do not widen the dedup key — that shifts V11's
  row count and A2 drop accounting for unrelated reasons.
- Verified outcomes: Cronus → Earth+Sky · Zeus → Cronus+Rhea · Aphrodite → Dione+Zeus (foam-birth
  stays a `variant_claims` conflict) · Achilles → Peleus+Thetis · Heracles → Alcmena+Zeus ·
  Hellen → Deucalion+Pyrrha · Endymion → Aethlius+Calyce · Helen → Leda only · Hephaestus → Hera only ·
  Io → one father (via deny-list).

**Why the originally-decided bare co-mention count was replaced (measured, not argued).** Simulating
"exactly 2 co-named ⇒ couple, 3+ ⇒ collapse" against the live candidate data:
- gives children up to **6** parents (`antiphus`: Hecuba, Heracles, Laothoe, Myrmidon, Pisidice,
  Priam) — it keeps every 2-pair from every passage, unanchored to the canonical resolution;
- injects false parents (`Athena parent_of Zeus`, Iliad 5.864 — an extraction error);
- introduces **6 new `parent_of` cycles** (vs 1 under the adopted rule);
- still drops a true parent on couple-plus-rival groups: Hellen (Deucalion, Pyrrha + flagged rival
  Zeus) and Endymion (Aethlius, Calyce + flagged rival Zeus) both count 3 and collapse to one;
- and **mis-couples Io — ADR-020's own worked example.** `Piren` is not in the confirmed entity set,
  so `_filter_and_dedup` reduces Io to *exactly two* rival fathers (Iasus, Inachus) before the
  resolver ever counts them. Io is one of the three ADR-004 floor conflicts.

**Other rejected alternatives:** `married_to` link — semantically wrong, most Greek co-parents were
never married; sexed labels `father_of`/`mother_of` — absent in the data (9 rows vs ~4,475
`parent_of`); "same source + same passage" alone — fails on Io; a new `entities.sex` column —
deferred (needs up-front gender curation; the adopted rule needs no new data). Full rationale in
ADR-020.

**Blast radius (re-measured 2026-07-26, second pass).** The live graph holds **2,492 canonical edges
over 1,145 children with a parent and 0 children with two** — the loss is total, not partial.
**472 children** regain a co-parent under the adopted rule (487 under the naive count), measured by
replaying the real pipeline (relation aliases → `_filter_and_dedup` → `resolve_canonical_edges`). Two
earlier figures are superseded: "~665" was counted over the *raw* candidates before the entity filter
`seedgen` applies; **"442" came from a simulation whose co-mention semantics were never written down**
— re-simulating under the explicit definition above gives 472, reproduces every baseline number here
and all ten worked outcomes, and no other reading of the rule returns 442 (460 / 465 / 467 / 480 were
tried). All of these are simulations: **the implementer re-measures against the real
`canonical_edge.py` change and records what the code produces.**

**Landing note:** A3 `cycle_check` will report one new cycle —
`Salmoneus → Tyro → Neleus → Deimachus → Enarete → Salmoneus`, closed by the restored and
mythologically *correct* `Enarete parent_of Salmoneus` edge running into a pre-existing reversed hop.
Restoring co-parents exposes latent direction errors; budget a reversed-edge fix pass at the
candidate-JSON layer. The gate is a **clean-or-explicitly-waived A3**, not a clean one.

Measured at the **post-resolver `parent_of`** layer (what V11 seeds from today's candidates): baseline
**1** cycle (`Eurymachus ↔ Polybus`, unrelated), going to **2** under the adopted rule. Three other A3
numbers are on record and none is comparable to these: **62** cycles at the pre-collapse candidate
layer, **96** from DEV-087's `python -m audit --candidates`, and "**0** live cycles" in the P3 exit
criteria — the last referring to the currently seeded DB, which predates the J1/J2/J3g candidate
edits. Always state the layer when quoting an A3 count.

Option (b) (defer to P5b with a waiver) was **not** taken — the loss was too broad and the fix is
offline-only (seedgen + extraction; no DDL, no runtime code), bounded, and safe.

### Root cause 2 (J4b) — Chaos is not Earth's parent in the source material

**Decided 2026-07-26 (DEV-091): option (b) — defer to P5b, waived.** No cosmogonic relation is
modeled in P3. See *Decision* below for the two options and the reasoning; re-verified directly
against the corpus text before deciding, not just against this entry's prior quote of it.

Independent of J4a: even a fully-restored `Sky parent_of Cronus` edge still can't reach `Chaos`,
because **no `parent_of` edge between `Chaos` and `Earth`/`Sky` should exist** — this isn't a
missing extraction, it's what Hesiod's *Theogony* actually says.

Direct corpus check, `ingestion/corpus/hesiod_theogony_evelynwhite1914.txt`, the cosmogony passage
(`[116]`–`[121]`):

> "Verily at the first Chaos came to be, but next wide-bosomed Earth... From Chaos came forth
> Erebus and black Night... And Earth first bare starry Heaven, equal to herself, to cover her on
> every side..."

Chaos and Earth arise **independently, in sequence** — Chaos does not beget Earth; they are
separate primordial entities that both "come to be" at (or near) the beginning. Chaos's actual
offspring are Erebus and Night, and those edges are already correctly present:

```
Chaos parent_of Erebus  [hesiod-theogony, 104-146]
Chaos parent_of Night   [hesiod-theogony, 104-146]
```

Confirmed via the resolver that, correctly, **no edge connects `Chaos` to `Earth`/`Sky` at all** —
resolving the candidates produces only the two edges above for `Chaos`, nothing else. Inventing a
`Chaos parent_of Earth` (or similar) edge to make Q9's traversal succeed would misrepresent the
source — exactly the kind of "patch data to pass one query" fix this project's conventions forbid
(`CLAUDE.md`'s review-gated `variant_claims` principle extends the same spirit here: don't assert a
claim the corpus doesn't make).

**Decision:**
- **(a)** Model an honestly-named, non-`parent_of` relation for "arose before/alongside" (e.g.
  `precedes_in_cosmogony`) so a graph traversal *can* connect the primordial generation to Chaos
  without asserting a false parent-child claim.
- **(b)** *(chosen)* Accept that Q9's literal "trace lineage back to Chaos" premise doesn't hold as a
  strict genealogical chain in this mythology, and that a full answer belongs to RAG/narrative
  synthesis (which can correctly explain Chaos and Gaia as co-primordial) rather than the
  relational/SQL model. Defer to P5b, waived, rather than force a same-shape edge that doesn't
  reflect the myth.

**Reasoning (DEV-091):** (a) is more than a data fix — it is new schema/prompt-modeling work, which
ADR-017 §Decision 4 places after P3 (data-quality/relational-fix) and before P5 (new data types),
exactly where this belongs. Concretely, (a) would need: deciding how many other Theogony entities
get the same relation (Tartarus, Eros, Pontus, and Night's children all "come to be" in the same
`[104]-[121]` passage without `parent_of` edges — this is not a one-off, Chaos is just the one Q9
happens to ask about), a `SchemaIntrospector`/`TextToSqlAgent` few-shot update teaching the model
when "lineage" should traverse a cosmogony edge and when it shouldn't, and a `WITH RECURSIVE` UNION
across two differently-typed relations for one query. Doing that scoped narrowly enough to make only
Q9 pass, without the broader design work, is exactly the "patch data to pass one query" anti-pattern
this project's conventions forbid — the same principle CLAUDE.md states for `variant_claims` extends
here. (b) is not a concession: Hesiod's own text already gives RAG everything it needs to answer this
correctly in prose (Chaos and Earth as co-primordial, arising in sequence, not parent and child) —
the relational model doesn't need to fake a shape the mythology doesn't have.

### Root cause 3 — every *contested* collapse also loses its rivals, with no record anywhere

Discovered 2026-07-26 while measuring Root cause 1. Independent of Q9, and broader than it: this is
the second half of the same data loss, and it is what stops the project from holding "a full family
tree, including contested claims."

Measured over the entity-filtered candidates:

| Quantity | Count |
|---|---|
| Distinct `parent_of` values dropped by the collapse today | **1,084** |
| Recovered by ADR-020's co-parent carve-out | 472 |
| Still collapsed, i.e. genuine rival parents | **612** |
| …of those, in groups citing **one** source — detector blind | **145** |
| …of those, in groups citing **≥2** sources — detector already fires | **467** |
| Children with ≥2 candidate parents | 641 |
| …all rows from a single source | 338 |
| …citing ≥2 sources (detector gate passes) | 303 |
| …where *some one source* names ≥2 parents (the "608") | 608 — of which **270 clear the gate** |
| Subjects with any `parentage` row in V12 | **2** (Aphrodite, Io) |

ADR-007 §6's promise is that a collapsed contest is not lost, because "the contradiction lives in
`variant_claims`." For parentage that promise is currently not kept — but **for two different reasons
that split the residue unevenly**, and conflating them was the original error in this entry:

1. **Detection cannot see same-source contests — 145 of the 612.**
   `extraction/conflict_detector.py::detect_conflicts` emits a candidate wherever a
   `(subject, claim_type)` group has **≥2 distinct `source_id`s** (`conflict_detector.py:82`). Where
   every row in a child's group comes from one source (338 children), the gate never fires and the
   rivals are structurally invisible. The module docstring already names this blind spot and defers it
   to "must be hand-added (TODO-stage4 B6/B7)".

   ⚠️ Note the gate counts distinct sources **across the whole group** — not within the disagreeing
   pair, and it does not require ≥2 distinct *values* at all. So the frequently-quoted "608 of 641 are
   contested within a single source" does **not** imply 608 undetected children: that figure counts
   children where *some one source* names ≥2 parents, and **270 of those 608 also cite a second
   source**, which clears the gate. `parent_of` maps into this group via
   `claim_type_aliases('parent_of' → 'parentage')` (V8_2), so these are all one `parentage` group per
   child.
2. **Detected candidates are never promoted — 467 of the 612.** For 303 children the gate already
   passes and candidates *are* emitted today; they stop at the ADR-004 human review gate, which no one
   has run over parentage beyond the hand-curated floor. This is a **review-throughput** problem and
   **no detector change touches it.**
3. **Nothing surfaces the dropped values for review — all 612.** The resolver discards them silently;
   audit check A2 (`drop_accounting.py`) reports contested-collapse as an aggregate count, not per
   dropped parent value, so a reviewer has no per-row list to promote from. This is the one gap common
   to both buckets, and the highest-leverage of the three.

Consequently the only parentage conflicts a user can ever see are the two hand-curated floor subjects.
A concrete instance: `Hellen` has `Zeus` named as a rival father by Apollodorus alongside the
Deucalion + Pyrrha couple, and that rival is dropped at seed time and recorded nowhere.

> **Not** an instance: an earlier draft of this entry used "who was Perseus's father?" as the example.
> That is wrong and points at a *fourth*, separate gap — `relationships_candidates_cleaned.json`
> contains **zero** `parent_of` rows into `Perseus`. The only Perseus rows are `Nestor` and
> `Anaxibia` → *"Perseus son of Nestor"*, a different figure. Nothing was dropped for the hero
> Perseus; his parentage was never extracted. Extraction-coverage gaps of that shape are not covered
> by GAP-001 — they are **GAP-003** as of 2026-07-27 (`[DEVIATED - see DEVIATIONS.md #DEV-093]`);
> this exact Perseus case is GAP-003's root cause 3 and the reason gold Q8 stable-fails.

**Decision needed** — the record-every-dropped-parent half is folded into J4a's landing scope (it
reads the same resolver pass); the promotion half is **not** code work and is scoped separately:
- **(a)** Emit a generated per-row record of every dropped parent (child, dropped value, source,
  passage, plus whether the subject already has a `variant_claims` parentage row) as a new
  A2r-contract audit check, **and** add a same-source qualifying condition to `detect_conflicts` for
  `parentage` so those rivals become `trust_tier=3` candidates. The ADR-004 human promotion gate to
  V12 stays exactly as-is — no unreviewed row reaches runtime. *(Recommended; chosen 2026-07-26.)*

  **Scope truth-in-advertising:** this closes the **145** detector-blind rivals and gives a reviewable
  artifact for all **612**. It does **not** by itself put a single new row in V12 — every candidate
  still waits on human promotion, and for the **467** rivals already detected today the detector
  change is a no-op. Do not record J4a's landing as "conflict surfacing now works for parentage."
- **(a′)** *(still open, not part of J4a)* Decide how the ~612-row review artifact actually gets
  worked: a bounded first tranche (e.g. the gold-question subjects plus the Olympian/Titan spine), a
  sampling policy, or an explicit P5b deferral. Without this, (a) produces a backlog and no
  user-visible change. **This is the binding constraint on the promise in ADR-007 §6, not the
  detector.**
- **(b)** Record the loss here and defer to P5b. Rejected: it leaves the product's defining feature
  (conflict surfacing) structurally unable to fire on the single most common conflict dimension.

### J4c — contingent follow-up

**Superseded by Track J5 landing (DEV-092) — Q9 now fully passes.** J4a alone (DEV-090) left Q9 at
route ✓, author ✓, content ✗, exactly as predicted: the traversal reached `Cronus`/`Earth` but the
required `Ouranos` keyword never appeared, since `Sky`/`Heaven`/`Uranus` were still three separate
entities. Track J5 (2026-07-26, DEV-092) merged them into canonical `Ouranos` specifically so that
keyword becomes reachable — confirmed live: Q9 is now **stable-pass 3/3**
(`evaluation/results/2026-07-26T17-49-26Z__5eed421__p3-j5-ouranos-merge-fixed/`), both `Ouranos` and
`Chaos` genuinely appear in the composed answer (`Chaos` via RAG's retrieved cosmogony context, not
a fabricated edge — J4b's deferral decision was never revisited or reversed). `gold-questions.json`
was never edited — the keywords were always correct; the data (and, as DEV-092 found, a row-cap
defect hiding it) was the gap, exactly as the DEV-048/DEV-050 precedent anticipates.

### Recommendation

- **J4a + Root cause 3's detection half: LANDED 2026-07-26 (DEV-090).** Both were genuine, recurring
  data-loss bugs, not one-offs, and both were offline seedgen/extraction work: bounded, no DDL, no
  runtime-code *design* change — though landing surfaced one real runtime-code fix on evidence (a
  token-budget regression in `MixedQueryHandler`/`SqlQueryHandler`, unrelated to the discriminator
  design itself, see DEV-090). Confirmed **not** "resolver-only": the landing touched
  `canonical_edge.py` (the four-part rule), `relationships_gen.py` (pre-dedup pair plumbing),
  `conflict_detector.py` (same-source parentage condition) and the new `dropped_parents.py`/A6 check.
  Landed through one Track I gate with zero stable eval regressions and A3 clean-or-waived.
- **Root cause 3's promotion half (a′): still unscoped — unchanged by the landing.** The detector
  change reaches 145 of 612 rivals; the other 467 are already-emitted candidates waiting on human
  review. **J4a's landing does not make parentage conflicts visible to users** — this was the
  predicted outcome, not a surprise, and it holds exactly as GAP-001 said it would.
- **J4b: DECIDED 2026-07-26 (DEV-091) — deferred to P5b.** Correctly modeling cosmogony-vs-genealogy
  semantics is a bigger design question than this stage's scope, and Q9 can likely be answered
  adequately via RAG/narrative coverage even without a `parent_of`-shaped edge to `Chaos`.
- **`Sky`/`Heaven`/`Uranus` merge: LANDED 2026-07-26 (DEV-092).** Merged into canonical `Ouranos`;
  Q9's `Ouranos` keyword confirmed passing live
  (`evaluation/results/2026-07-26T17-49-26Z__5eed421__p3-j5-ouranos-merge-fixed/`) after also fixing
  a row-cap defect the merge exposed. GAP-001 is now closed for everything P3 was ever going to fix
  — the only remaining open item is Root cause 3's promotion half (a′), carried to P4.
- **Q9 passing does not clear the DATA floor.** Read this entry's closure narrowly: DATA is still
  **2/5 (40%) against a 50% floor** in the same run that proves Q9 green. The remaining three DATA
  failures (Q6/Q7/Q8) are **not** GAP-001 root causes and were never in P3's scope — see **GAP-003**.

**References:** `ingestion/seedgen/canonical_edge.py` (`resolve_canonical_edges`, `SPINE_PRIORITY`,
`_pick_winner`); `ingestion/seedgen/relationships_gen.py` (`_filter_and_dedup`, the pre-dedup
constraint); `ingestion/extraction/conflict_detector.py` (`detect_conflicts`, the ≥2-distinct-sources
gate); `ingestion/audit/drop_accounting.py` (A2, aggregate-only today);
`ingestion/extraction/output/relationships_candidates_cleaned.json` (`Sky`/`Earth` → `Cronus`,
`Chaos` → `Erebus`/`Night` rows, and the `is_contested` field the fix keys on);
`ingestion/corpus/hesiod_theogony_evelynwhite1914.txt` lines ~16–30 (`[104]`–`[163]`);
`evaluation/gold-questions.json` (Q9); `docs/DEVIATIONS.md` #DEV-069 (original discovery), #DEV-088
(this fix); `docs/adr/adr-020-joint-parentage-multi-edge.md`; `docs/TODO-phase2-stage-p3.md` Track J4.

---

## GAP-002 — 367 entities are referenced by candidate relationships but absent from the confirmed set

**Status:** OPEN, un-triaged. Discovered 2026-07-23 by audit check A2 (DEV-074), re-confirmed
unchanged at DEV-076 and DEV-083, and **re-verified live 2026-07-27** (`python -m audit
--candidates`: `367 distinct unknown name(s)`). DEV-074 filed it as "a new, large triage backlog for
Track J"; Track J closed for P3 (J4a/J4b/J5 all landed) without touching it, and no TODO file ever
listed it. Given a home 2026-07-27 as Stage **P3b** `[DEVIATED - see DEVIATIONS.md #DEV-093]`.

### Symptom

`ingestion/seedgen/relationships_gen.py` drops any candidate relationship row whose `from_name` or
`to_name` does not resolve to a confirmed entity. A2 (`drop_accounting.py`) accounts for that bucket
and, in its unknown-name drilldown, names the missing entities. The drop is silent at seed time —
nothing in `V11` records that the row existed.

### Evidence (live, 2026-07-27, `python -m audit --candidates`)

```
A2: 6902 raw -> 3243 seeded (unknown_name=1246, exact_dup=1448, contested_collapse=965, residual=0)
    367 distinct unknown name(s)
```

Top of the ranked drilldown, by number of candidate rows referencing the name:

| references | name | note |
|---:|---|---|
| 133 | `<UNKNOWN>` | **not** a missing entity — an unresolved extraction sentinel; A2's own `suggestedFix` says to investigate the extraction pass, not Track J |
| 110 | `Nereus` | major, unambiguous sea god |
| 71 | `Arges` | Cyclops |
| 64 | `Doris` | Oceanid, Nereus's consort |
| 26 | `Alcinous` | Phaeacian king (Odyssey) |
| 23 | `Electra` | |
| 17 | `Styx` / `Phineus` | `Phineus` is directly load-bearing for gold **Q8** (GAP-003) |
| 16 | `Ceto` | |
| 15 | `Thaumas` | |
| 14 | `Steropes` / `Eurytus` | |
| 13 | `Thoas`, `Pegasus`, `Eurynome`, `Ascalaphus` | |

366 real names (excluding the sentinel) across **1,253** dropped rows. DEV-074 confirmed by direct
lookup that these are **not** typos or spelling variants — zero fuzzy overlap with the confirmed set,
so audit check A1 will never surface them and the DEV-042 `Io` fix pattern does not apply.

### Root cause

The confirmed entity set (`entities_candidates_confirmed_v1.json`, 1,981 rows) was built by a
review pass over *extracted entity candidates*, independently of the *relationship* candidates. Any
figure the entity extraction pass missed — or that a reviewer did not confirm — silently invalidates
every relationship row mentioning it. Nothing reconciles the two candidate files against each other;
A2 is the first check that ever compared them, which is why this sat undetected from Stage 4 to P3.

### Scope note — this is a triage backlog, not a bulk-add

The 367 are **leads**, not a work list. Three buckets, and only the first is a clear add:
1. Genuine, unambiguous figures that belong in the graph (`Nereus`, `Doris`, `Ceto`, `Thaumas`,
   `Styx`, `Arges`, `Steropes`) — add to the confirmed set, regenerate `V10`/`V11`.
2. Namesake collisions and conflations of the class DEV-078…DEV-082 spent all of Track J untangling
   (`Electra`, `Eurytus`, `Phineus`, `Thoas` are all multi-person names in this corpus) — adding a
   bare name here would *create* the exact defect Track J just removed.
3. Extraction noise and the `<UNKNOWN>` sentinel — no entity to add; a signal about the extraction
   pass instead.

Adding bucket 1 grows the graph and can surface new A3 cycles, so it goes through the standard Track
I fix loop like any other data change.

### Decision needed

- **(a)** *(Recommended, scoped as P3b)* Work only the subset that unblocks GAP-003 — the names on
  the Perseus/Danae/Gorgon lines and anything else gold-question-load-bearing — plus bucket 1's
  unambiguous top names. Carry the long tail to P4 alongside the other review-throughput backlogs.
- **(b)** Work all 367 as one batch. Rejected: it is the same undifferentiated-bulk-triage shape that
  made DEV-084's 48-pair pass slow, and buckets 2/3 need per-name source verification anyway.
- **(c)** Waive as permanent long-tail, like A1's 39 pairs. Rejected: unlike A1's residue, these are
  **not** duplicates of rows already present — each one is a real, absent piece of the graph, and at
  least one (`Phineus`) blocks a gold question today.

**References:** `ingestion/audit/drop_accounting.py` (A2, unknown-name drilldown);
`ingestion/seedgen/relationships_gen.py` (`_filter_and_dedup`);
`ingestion/extraction/output/entities_candidates_confirmed_v1.json`;
`docs/DEVIATIONS.md` #DEV-074 (discovery), #DEV-076/#DEV-083 (re-confirmed unchanged), #DEV-093
(homed); `docs/TODO2.md` Stage P3b.

---

## GAP-003 — DATA category floor breach: Q6, Q7, Q8 all stable-fail

**Status:** OPEN. Triaged in Stage P1 Track H3 (`docs/TODO-phase2-stage-p1.md`) as three data-gaps
routed "**→ P3**"; P3 landed and committed (`35fb379`) without any of the three ever appearing in
`TODO-phase2-stage-p3.md` or `TODO2.md`. Given a home 2026-07-27 as Stage **P3b**
`[DEVIATED - see DEVIATIONS.md #DEV-093]`. **This is the project's only failing evaluation gate.**

### Symptom

`evaluation/results/2026-07-26T17-49-26Z__5eed421__p3-j5-ouranos-merge-fixed/report.md` — the same
run in which overall eval first reached the 75% target and GAP-001's Q9 went green:

```
Overall (pessimistic / worst-run): 12/16 = 75% (target 75%) — PASS
  FACT     5/5 (100%) — floor n/a
  DATA     2/5  (40%) — floor 50% BREACH
  MIXED    1/2  (50%) — floor n/a
  CONFLICT 4/4 (100%) — floor 50% PASS
```

Q9 and Q10 pass. **Q6 2/3, Q7 2/3, Q8 0/3 — all `stable-fail`.** Three unrelated root causes.

### Root cause 1 (Q6) — `Hades` and `Hestia` are typed `other_god`, not `olympian`

Gold Q6 "Which Olympians are children of Cronus?" requires
`["Zeus","Hera","Poseidon","Demeter","Hestia","Hades"]`. The generated SQL is **correct**:

```sql
WHERE r.relation = 'parent_of' AND parent.name ILIKE 'Cronus' AND child.type = 'olympian'
```

and the answer is correct *for the data*: "Zeus, Hera, Poseidon, and Demeter". Verified in
`entities_candidates_confirmed_v1.json`: `Zeus`/`Hera`/`Poseidon`/`Demeter` are `type='olympian'`;
`Hades` and `Hestia` are `type='other_god'`. Route ✓, author ✓, content ✗ — a typing decision, not a
retrieval or generation defect, and the smallest of the three fixes.

Note this is a genuine editorial question, not just a mistake: whether Hades and Hestia count as
Olympians is contested in the tradition itself. The fix must therefore be a recorded decision (retype
to `olympian`, or keep `other_god` and use `subtype` per DEV-040), not a silent edit — and if the
decision goes the other way, Q6's keyword list is what changes, as a logged eval-bug per the
DEV-048/DEV-050 precedent.

### Root cause 2 (Q7, Q8) — the hero Perseus has no extracted relationships at all

`relationships_candidates_cleaned.json` contains **zero** rows with `Perseus` as either `from_name`
or `to_name` (verified live 2026-07-27, 6,902 rows). Not dropped — never extracted. The only
Perseus-adjacent rows are `Nestor`/`Anaxibia` → *"Perseus son of Nestor"*, a different figure. This
is the "fourth, separate gap" flagged as untracked under GAP-001 Root cause 3; it lives here now.

Consequences, both live-verified:
- **Q7** ("Which heroes are children of Zeus?", requires `["Heracles","Perseus"]`) — the SQL is
  correct and now returns `Heracles`, `Castor`, `Pollux`, `Arcas`, `Iasion`, `Zethus`, `Ajax`,
  `Arcesilaus`. `Perseus` is absent because no edge exists.
- **Q8** ("List all monsters Perseus encountered.", `expected_route: SQL`) — SQL over an entity with
  no relationships returns nothing, so the handler falls back to RAG. Route ✗, author ✗, content ✗ =
  **0/3**, the only zero in the set. The RAG answer is factually good (Medusa, the Gorgon, the sea
  monster, Phineus) — the failure is structural, not a retrieval failure.

> **Stale triage correction.** P1's H3 note reads "Q7 → data-gap (Zeus→Heracles/Perseus edges
> missing)". The `Heracles` half is **no longer true**: `Zeus parent_of Heracles` is present in the
> live `V11` (104 `Zeus parent_of` rows total), restored as a side effect of ADR-020's joint-parentage
> landing (DEV-090) — before that, the contested collapse kept only `Alcmena`. Only the `Perseus`
> half survives, which collapses Q7's root cause into Q8's.

This overlaps GAP-002: `Phineus` — whom Perseus turns to stone, and a plausible Q8 answer — is one of
GAP-002's 367 missing entities (17 references). Fix the two together.

### Root cause 3 (Q8) — the `Cetus` keyword is unattested in the corpus

Independent of the data gap, Q8 requires `["Medusa","Gorgon","Cetus"]`. Grepped live over
`ingestion/corpus/`: **`Cetus` never appears as a word.** Its only occurrences are inside
`Anicetus` (Apollodorus) and `Lycetus` (Ovid) — two unrelated men. Frazer and More render the
Andromeda sea monster descriptively ("a sea monster"), never by that name.

So Q8 cannot score its content point even after root cause 2 is fixed. This is precisely the
brittle-keyword class DEV-048 (`Eris` → `Strife`) and DEV-050 established, and it must be handled the
same way: a **logged eval-bug fix**, live-verified against the corpus, never silent tuning. Note that
`Cetus` is also absent from the confirmed entity set, so no SQL answer could produce it either.

### Decision needed

- **Q6** — decide the Hades/Hestia typing and record it. Regenerate `V10`; no schema change.
- **Q7/Q8** — a bounded, source-verified extraction pass for the Perseus line (Zeus + Danae →
  Perseus; Perseus → Medusa/Gorgon/sea monster/Phineus), reusing the existing
  `instructor`/checkpoint tooling and `ref_ranges.py`. Coordinate with GAP-002 bucket 1 so `Phineus`
  and friends land once. **Do not hand-write rows without source attribution** — the constraint
  DEV-047 cited when it declined to patch exactly these questions in Stage 5.
- **Q8's `Cetus`** — replace with a corpus-attested keyword after the data fix lands, live-verified
  across 3 runs, logged as an eval-bug (DEV-048/DEV-050 precedent). Sequence it **after** root cause
  2, so the keyword is chosen against the real post-fix answer rather than against a RAG fallback.

Expected outcome: Q6 and Q7 recoverable to 3/3, Q8 to 3/3 only if all of root causes 2 and 3 land.
DATA reaches the 50% floor at 3/5 — so **Q6 plus either Q7 or Q8 is sufficient** to clear the gate.

**References:** `evaluation/gold-questions.json` (Q6, Q7, Q8);
`evaluation/results/2026-07-26T17-49-26Z__5eed421__p3-j5-ouranos-merge-fixed/`;
`ingestion/extraction/output/entities_candidates_confirmed_v1.json` (`Hades`/`Hestia` typing);
`ingestion/extraction/output/relationships_candidates_cleaned.json` (no `Perseus` rows);
`core-api/src/main/resources/db/migration/V11__seed_relationships.sql` (`Zeus parent_of Heracles`
present); `docs/TODO-phase2-stage-p1.md` H3 (the original triage); `docs/DEVIATIONS.md` #DEV-047
(first sighting, Stage 5), #DEV-048/#DEV-050 (the keyword-fix precedent), #DEV-090 (fixed Q7's
`Heracles` half), #DEV-093 (homed); `docs/TODO2.md` Stage P3b; **GAP-002** (shares root cause 2).
