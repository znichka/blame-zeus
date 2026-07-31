# Data Gaps

Documented, deliberately-unfixed gaps in the relational data model or extracted corpus data —
things that are **known and understood**, not silent failures. Each entry records the symptom, the
root cause(s), why it wasn't fixed in the stage that found it, and the decision still needed.
Referenced from `docs/TODO-phase2-stage-p3.md` (Stage P3, Track J4) as the landing place for any
gap deferred to Phase 5b.

| Gap | Summary | Status | Home |
|---|---|---|---|
| **GAP-001** | Q9 cannot reach `Ouranos`/`Chaos` | Closed for everything P3 owned; root cause 3's promotion half (a′) open | P4 (a′), P5b (J4b, waived) |
| **GAP-002** | 367 entities referenced by candidate relationships but absent from the confirmed set | **Partially resolved** — 5 of 7 original bucket-1 landed (DEV-096); `Arges`/`Steropes` corruption triaged and `Ares` recovered (DEV-098); A7 built and its 6 findings closed (DEV-099/DEV-100); **P4 Track H landed 12 more bucket-1 names + 3 translation-spelling aliases (DEV-108)**, unknown-name count 362→347; bucket 2 (namesake collisions) grew by 3 confirmed cases; long tail explicitly deferred with buckets/reasons | Stage P3b (partial), **P4 (DEV-108, this pass)**, P5 (residual long tail) |
| **GAP-003** | DATA floor breach — Q6/Q7/Q8 all stable-fail | **Resolved** — all 3 root causes landed (DEV-094, DEV-095); DATA 100%, overall 94% | Stage P3b |
| **GAP-004** | `Saturn` is a separate `other_god` entity instead of an alias of the `titan` `Cronus` | **RESOLVED 2026-07-29 (DEV-121)** — merged with GAP-006 as one entity-merge pass. `Saturn` is now an `entity_aliases` row → `Cronus` (V20), alongside V14's `Jove`/`Jupiter`/`Juno` for the same translator; its 10 candidate rows were rewritten, so Ovid's `Zeus <- Saturn` / `Hera <- Saturn` now corroborate the existing parentage instead of reading as spurious second parents, and their A6 waivers are gone. Merging it also exposed a namesake collision the gap never mentioned — see the entry below | Closed |
| **GAP-006** | `Ajax` is fragmented across **15 entities** for what are really two people, and A1 cannot see it | **Open** — found 2026-07-29 while verifying DEV-119's findings. Eight surface forms for Ajax the Greater (`Ajax`, `Ajax the Great`, `Great Ajax`, `Ajax son of Telamon`, `Ajax (Telamon's son)`, `Aias (son of Telamon)`, `Aias (Telamonian)`, `Telamonian Aias`/`Telamonian Ajax`) and six for the Lesser (`Ajax the Lesser`, `Ajax the Locrian`, `Ajax (Oilean)`, `Ajax son of Oileus`, `Aias (son of Oïleus)`, `Aias the less`) — proven co-referent, not namesakes, by their own edges: **`Telamon parent_of` six of them and `Oileus`/`Oïleus parent_of` four**. The father is duplicated too (`Oileus` vs `Oïleus`). Three compounding consequences, all verified: (a) evidence is split — bare `Ajax` holds 22 edges while ~15 more scatter across the other 14, which plausibly explains DEV-110's otherwise-odd finding that `Ajax` had *no* promotable `marriage`/`epithet` candidates; (b) it defeats **A1**, which flags **zero** of these pairs — its 88-point fuzzy threshold and transliteration pass cannot span `Great Ajax`↔`Telamonian Aias`; (c) it defeats **A11**, which cannot catch the reversed `Ajax the Lesser parent_of Oïleus` because the fragmented entity name never appears in the corpus text in the patronymic formula. Distinct from the documented, *intentional* `Name (descriptor)` convention (DEV-079/080/082) — this is that convention applied inconsistently in five competing styles, not a deliberate namesake split. **RESOLVED 2026-07-29 (DEV-121)** — see the entry below; it was **16** entities, not 15 | Closed |
| **GAP-007** | `Zeus parent_of Ajax` is **seeded live** — ADR-020's co-mention rule reads the Homeric vocative formula *"Aias, sprung from Zeus, thou son of Telamon"* (Iliad 7.233) as one passage naming two co-parents | **Open** — found 2026-07-29 while verifying the GAP-004/GAP-006 merge (DEV-121). Not an extraction error: the text says it, and rules 1-3 of the discriminator cannot exclude it by construction (never flagged contested; `Telamon` *is* the winner and `Zeus` is in the pair). It is what rule 4's deny-list exists for, and that list still holds only `Io`. The `relationships` counterpart of the Homeric-formula misreads DEV-112 rejected behind the `variant_claims` review gate — but this table is seeded, not review-gated, so it reaches users. `Ajax` shows up in gold Q7's "children of Zeus" answer today | **RESOLVED 2026-07-29 (DEV-122)** — deny-list entry added, and the sweep it asked for was **run and bounded, not deferred**: only **3** seeded divine co-parents rest solely on the formula-bearing sources (Homer + Homeric Hymns; the formulae are absent from Apollodorus/Hesiod/Ovid — measured, 0 hits), of which `Ajax <- Zeus` is the one false positive and `Molione <- Poseidon` / `Pandia <- Zeus` verify as genuine. The five `variant_claims` counterparts were rejected to `trust_tier=2` in the same pass. Live: `Ajax` now has Telamon only, from four sources, and is gone from Q7's answer | Closed |
| **GAP-008** | The **misattributed-passage** shape is unswept in the *seeded* `relationships` table — `Zeus parent_of Ate` cites Iliad 9.496-9.528, where the "daughters of great Zeus" are the **Prayers** (Litai), not Ate | **Open** — found 2026-07-29 by DEV-122's GAP-007 sweep, which checked every single-parent divine edge as well as the co-parent ones. The claim is true and Homer *does* state it — *"Eldest daughter of Zeus is Ate that blindeth all"* — but at **19.90**, not at the cited ref. Same shape DEV-119 catalogued as bucket (4) among *dropped* parents (18 instances) and DEV-121 hit twice among Ajax's `killed_by` rows; nobody has ever swept the **seeded** edges for it, and seeded rows are not review-gated. Left unfixed deliberately: the only two honest fixes are dropping a true claim or moving the ref, and DEV-121 established that moving a ref is inventing provenance — so it needs a decision, not a silent edit | P5 (extraction-quality) |
| **GAP-005** | Extraction reads in-narrative **deception** as fact | **Open** — a NEW error shape found during A6 triage (DEV-119), distinct from every shape P4 catalogued: a character stating a *false* parentage while disguised. Aphrodite tells Anchises *"Otreus … is my father"* directly after *"know that I am no goddess"*; Hermes, disguised as a Myrmidon, names Polyctor. The cited passage genuinely says what was extracted — it is the speaker who is lying — so no passage-verification check can catch it, unlike the misattributed-passage and reversed-direction shapes. Both known instances are waived; unknown how many more exist | P5 (extraction-quality) |
| **GAP-009** | Fuzzy-match false positives fold a spelling-distinct name onto an unrelated confirmed entity, e.g. the text's own "Atas" resolving to the Titan `Atlas` | **Open** — found 2026-07-31 during Stage P5 Track C review (DEV-136/137/138), a byproduct of per-row `variant_claims` adjudication, not a dedicated sweep. Narrow: only a handful of confirmed instances so far, all traced to `entity_resolver.py`'s rapidfuzz stage or a legitimate-elsewhere `entity_aliases` row applied out of context | P5 (extraction-quality) |
| **GAP-010** | **Exact-name namesake collisions** — the corpus genuinely reuses one name for two-plus unrelated figures, and extraction/resolution merges them into one `entities` row, e.g. Priam's obscure son "Idomeneus" merged into the Cretan king `Idomeneus` (3-source figure) | **Open** — found 2026-07-31 during the same Track C review, at real volume: **≥82 confirmed instances across 7 passages** (DEV-136/137/138), roughly 20-30% of all tier-3 rows reviewed so far. Distinct from GAP-009: no fuzzy step is involved, the strings are identical, so it cannot be tuned away — three instances already reached *seeded* `relationships` and one a *promoted* `variant_claims` row | P5 (extraction-quality) |

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

**Status:** PARTIALLY RESOLVED. 5 of the 7 bucket-1 names landed 2026-07-27 (**DEV-096**):
`Nereus`, `Doris`, `Ceto`, `Styx`, `Thaumas` — unknown-name count 367 → 362. **`Arges` and
`Steropes` were investigated and deliberately NOT added** — they turned out to be majority
extraction-corruption of `Ares` and `Sterope`, a new and larger finding, detailed below. Originally
discovered 2026-07-23 by audit check A2 (DEV-074), re-confirmed unchanged at DEV-076 and DEV-083.
DEV-074 filed it as "a new, large triage backlog for Track J"; Track J closed for P3 (J4a/J4b/J5 all
landed) without touching it, and no TODO file ever listed it. Given a home 2026-07-27 as Stage
**P3b** `[DEVIATED - see DEVIATIONS.md #DEV-093]`.

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
| 110 | `Nereus` | ✅ **added (DEV-096)** — major, unambiguous sea god |
| 71 | `Arges` | ✅ **triaged (DEV-098)** — 4 of 71 rows are the genuine Cyclops (now added); the other 67 were `Ares`, which had **zero** rows of its own. 37 renamed, 5 reversed, 25 dropped as unsupported by the cited text |
| 64 | `Doris` | ✅ **added (DEV-096)** — Oceanid, Nereus's consort |
| 26 | `Alcinous` | Phaeacian king (Odyssey) |
| 23 | `Electra` | |
| 17 | `Styx` / `Phineus` | `Styx` ✅ **added (DEV-096)**. `Phineus` is directly load-bearing for gold **Q8** — but DEV-095 found he's a mortal, not a monster, and Q8 was resolved without him; he remains a genuine GAP-002 name in his own right |
| 16 | `Ceto` | ✅ **added (DEV-096)** |
| 15 | `Thaumas` | ✅ **added (DEV-096)** |
| 14 | `Steropes` / `Eurytus` | `Steropes` ✅ **triaged (DEV-098)** — 4 of 14 rows are the genuine Cyclops (now added); the other 10 split across **five distinct women named `Sterope`**. `Eurytus` still open |
| 13 | `Thoas`, `Pegasus`, `Eurynome`, `Ascalaphus` | |

366 real names (excluding the sentinel) across **1,253** dropped rows. DEV-074 confirmed by direct
lookup that these are **not** typos or spelling variants of any *confirmed* entity — zero fuzzy
overlap with the confirmed set, so audit check A1 will never surface them and the DEV-042 `Io` fix
pattern does not apply. **DEV-096 found a related but distinct failure mode** (below): two of these
366 names are themselves corruptions of an *existing* confirmed entity's name (`Ares`) or of another
missing name (`Sterope`) — not spelling variants *within* the confirmed set, but corruption *inside
the candidate data*, which is why A1 (which only ever compares confirmed-set names to each other)
was never going to catch it either.

### New finding (DEV-096) — `Arges` and `Steropes` are majority extraction corruption, not the Cyclopes

Before adding `Arges`/`Steropes` as planned, their candidate rows were broken down by `passage_ref`
— a check this entry's original bucket-1 framing never did, since a high reference count was read as
evidence of a real missing entity rather than checked against the actual cited text.

**`Arges` (71 candidate rows):** only **2** (`Ouranos parent_of Arges`, `Earth parent_of Arges`, both
`apollodorus-bibliotheca 1.1.1-1.1.7`) are genuinely the Cyclops from Hesiod/Apollodorus's cosmogony.
The other **69** are scattered across Homer's *Iliad*, Ovid's *Metamorphoses*, and unrelated
Apollodorus books (e.g. `2.5.7-2.5.8`, `2.7.7`, `3.4.2-3.4.3`, `3.9.2-3.10.1`, `12.153-12.194`,
`24.247-24.280`), and are **extraction corruption of `Ares`** — already a confirmed `olympian`
entity. Spot-verified directly: a candidate row reads `"Arges master_of Ajax son of Telamon"` /
`"Arges master_of Ajax son of Oileus"` citing `homer-iliad 8.78-8.111`; the actual text there
(`[78]`) reads "nor yet the Aiantes twain, squires of **Ares**."

**`Steropes` (14 candidate rows):** only **2** (`1.1.1-1.1.7`) are the genuine Cyclops. The rest
(`1.7.4-1.7.8`, `1.7.9-1.8.1`, `2.7.2-2.7.3`, `3.12.7-3.13.4`, `3.9.2-3.10.1`) trace to Apollodorus's
Aetolian royal genealogy, where the actual text names a daughter **`Sterope`** — "Pleuron wedded
Xanthippe... and begat... daughters, **Sterope** and Stratonice and Laophonte" (`[1.7.7]`) — one
letter different from the Cyclops's name, and the citation spread (three unrelated book-3 passages
in addition to book 1) suggests this may itself be 2+ distinct people sharing the name `Sterope`,
not one.

**Why this matters more than a normal missing-entity gap:** adding `Arges`/`Steropes` as single
entities without this check would have silently created ~69 and ~12 nonsensical relationship rows
(a Cyclops "mastering" the sons of Telamon and Oileus, fathering a scattering of Aetolian nobles) —
a worse defect than the one Track D set out to fix. And unlike a normal missing entity, this isn't
caught by any existing audit check: A1 (fuzzy-dup) only compares *confirmed* entity names to each
other, and `Arges`/`Ares`, `Steropes`/`Sterope` never coexist there — the corruption lives entirely
inside the *candidate* extraction data. **This is a new failure-mode lead, not yet DEV-numbered as
its own investigation**, and is plausibly recurring — if the extraction model confused `Ares` with
`Arges` and `Sterope` with `Steropes`, other near-miss corruptions of major names may exist elsewhere
in the 6,905-row candidate set undetected.

### Resolution (DEV-098, 2026-07-27) — corruption was total, not partial; `Ares` recovered

**RESOLVED for `Arges`/`Steropes`.** All 85 rows were triaged against the passages they cite (see
`DEVIATIONS.md` DEV-098). The finding above was correct in kind but **understated in degree**:

- The string `Arges` occurs in **exactly two places in all six corpus texts** (Apollodorus `[1.1.2]`,
  *Theogony* `[139]` — both the Cyclopes list). `Ares` occurs 153× in the *Iliad* alone; Ovid's More
  translation uses `Mars`/`Gradivus`. The extractor emitted **71 `Arges` rows and 0 `Ares` rows** —
  and the same holds in `relationships_candidates_raw.json` (77 vs 0), so this is the extraction
  model, not a cleaning bug.
- Consequence: **`Ares`, a confirmed `olympian` since V10, had zero relationships in the seeded
  graph.** Not "corrupted data for an existing Olympian" — *total erasure* of one.
- Genuine-Cyclops rows were **4, not 2**, for each of `Arges` and `Steropes` (the finding above
  missed the parallel *Theogony* `104-146` pair).
- `Steropes` was a **five-way split**, not a rename: five distinct women named `Sterope` (daughters
  of Pleuron, Porthaon, Cepheus, Acastus, and the Pleiad who married Oenomaus).
- Outcome: 37 rows renamed to `Ares`, 5 reversed and renamed, 25 dropped as unsupported by their own
  cited text (formulaic epithets like "scion of Ares", metonymy like "all them hath Ares slain", and
  refs containing no such statement), 2 correctly-referenced parentage rows added, 8 new entities
  (`Arges`, `Brontes`, `Steropes` + the five `Sterope`s). **`Ares`: 0 → 33 seeded relationships.**

**The failure mode now has a detector (DEV-099).** Audit check **A7**
(`ingestion/audit/name_coverage.py`) implements the rule proposed here — *confirmed entity named
often by the corpus but referenced by zero candidate relationship rows* — plus corruption-partner
identification, so it names the culprit and not just the victim. Validated against `fbf47bf`'s
pre-fix data, its top hit is `208 mentions / 0 rows  Ares <- likely 'Arges' (71 rows, 88.9)`, 8×
ahead of the next entry. (208, not the 153 quoted above — that figure was the *Iliad* alone.) A7 is
part of the standing pre-seedgen gate, so a future extraction run that reintroduces this class fails
the gate instead of seeding silently.

**A7's own findings: worked and closed (DEV-100).** The first sweep produced **6 findings**, and
they resolved into **three** fix shapes — notably, two needed *removal*, the opposite of what a
coverage gap invites:

| finding | mentions | verdict |
|---|---:|---|
| `Argeiphontes` | 26 | **Not an entity** — a standing Homeric **epithet of `Hermes`** ("Hermes, the messenger, Argeiphontes"). The extraction's own `variant_claims` candidates already carried it as `claim_type='epithet'`. Removed; now an alias. A1 scores the pair **33.3** and could never reach it. |
| `Acusilaus` | 10 | **Not an entity** — an **ancient mythographer Apollodorus cites** ("so says Acusilaus"). Removed outright, no alias. |
| `Diomed` | 10 | **Not an entity** — More's metrical contraction of **`Diomedes`**, Ovid-only; book 13 assigns it the Iliadic Diomedes' own deeds. Removed; now an alias. A1 misses it at **85.7**, just under its 88 threshold. |
| `Thisbe` | 10 | **Real, rows added** — the Ovidian heroine; `Pyramus` was *also* at zero rows. `Pyramus loves Thisbe` + `Thisbe loves Pyramus` @ `4.55-4.80`. |
| `Charybdis` | 17 | **True positive, nothing to extract — waived.** A sea hazard in every mention; no parentage/marriage/death anywhere in the six sources, and no `encountered` relation exists. |
| `Demodocus` | 11 | **True positive, nothing to extract — waived.** The Phaeacian minstrel; no kinship stated, and `servant_of` would overstate a bard the king summons as an honoured performer. |

A7 now reports **2 findings, both waived**. The two waivers are the honest outcome, not an evasion:
inventing a relation type to drive the count to zero would let an audit check dictate the data
model, and fabricating a parentage is the DEV-047/DEV-095 line this project does not cross.

### Root cause

The confirmed entity set (`entities_candidates_confirmed_v1.json`, 1,981 rows) was built by a
review pass over *extracted entity candidates*, independently of the *relationship* candidates. Any
figure the entity extraction pass missed — or that a reviewer did not confirm — silently invalidates
every relationship row mentioning it. Nothing reconciles the two candidate files against each other;
A2 is the first check that ever compared them, which is why this sat undetected from Stage 4 to P3.

### Scope note — this is a triage backlog, not a bulk-add

The 367 (now 347) are **leads**, not a work list. Four buckets now, not three:
1. Genuine, unambiguous figures that belong in the graph — **`Nereus`, `Doris`, `Ceto`, `Thaumas`,
   `Styx` added 2026-07-27 (DEV-096)**; **`Alcinous`, `Arete`, `Pegasus`, `Amphitrite`, `Chiron`,
   `Chrysaor`, `Argus Panoptes`, `Nessus`, `Rhadamanthys`, `Epaphus`, `Tisiphone`, `Hippolyte` added
   2026-07-28 (DEV-108)**, plus 3 translation-spelling aliases (`Aesculapius`→`Asclepius`,
   `Phorcus`→`Phorcys`, `Helios`→`Helius`) resolved into existing entities rather than added new.
2. Namesake collisions and conflations of the class DEV-078…DEV-082 spent all of Track J untangling
   (`Electra`, `Eurytus`, `Phineus`, `Thoas` are all multi-person names in this corpus) — adding a
   bare name here would *create* the exact defect Track J just removed. **Still open — grew by 3
   confirmed cases 2026-07-28 (DEV-108): `Oenomaus`, `Hippolytus`, `Ascalaphus`.** `Coronis` and
   `Eurynome` are flagged as *possible* further cases, investigated but left undecided rather than
   guessed either way. **Grew by 2 more 2026-07-29 (DEV-122), and these two are already-confirmed
   entities rather than unknown names — a sub-class this bucket had not held before:**
   - **`Clitus` conflates three men** — Apollodorus 2.1.5's son of Egyptus and Tyria who married
     Clite; Iliad 15.442's *"Cleitus, the glorious son of Peisenor, comrade of Polydamas"*; and
     Odyssey 15.238's Cleitus son of Mantius, carried off by Dawn. The contested collapse keeps the
     spine source's Egyptus+Tyria couple and drops Peisenor and Mantius as *rivals* — but they are
     not rivals, they are two other men's true fathers.
   - **`Pisenor` conflates at least two** — the Odyssey's Peisenor, father of Ops and grandfather of
     Eurycleia, and the Iliad's Peisenor, father of Cleitus. (A third, the Odyssey herald Peisenor
     at 2.35, has no extracted rows.) DEV-122 corrected the direction of both edges into this entity,
     which made the conflation visible: it now reads as one man fathering two unrelated sons instead
     of one man having two unrelated fathers.

   **Neither is fixable by a spelling alias, and that is the transferable lesson.** The obvious
   repair for both — `Peisenor`→`Pisenor` and `Cleitus`→`Clitus`, translation-spelling aliases in the
   DEV-108 style — was drafted and then **discarded before being written**, because the corpus
   spelling denotes *several people*: the alias would assert that all three Clituses are one. This
   bounds DEV-121's finding (4) proposal for a diacritic-folding pre-pass on A1: folding and aliasing
   only help where the surface form denotes exactly one figure, so a folding pre-pass needs a
   namesake guard, not just a lower threshold.
3. Extraction noise and the `<UNKNOWN>` sentinel — no entity to add; a signal about the extraction
   pass instead. **Still open** (133 rows), plus a newly-named **place-name sub-class** with no
   entity-type home at all in the current schema (DEV-108).
4. *(New, DEV-096)* **Extraction corruption of an existing name** — `Arges` (→ **entirely** `Ares`)
   and `Steropes` (→ mostly five distinct `Sterope`s) were originally filed in bucket 1 but turned
   out to belong here instead. **These two names RESOLVED 2026-07-27 (DEV-098)**, and the *failure
   mode* now has a detector — **audit check A7** (DEV-099), which reproduces the missed `Ares` lead
   on pre-fix data and found 6 more entities of the same shape (see Resolution above).

Adding bucket 1 grows the graph and can surface new A3 cycles, so it goes through the standard Track
I fix loop like any other data change — confirmed clean for the 5 names added (A3 unchanged at 1
waived cycle, A5 clean, no new A1 fuzzy-dup pairs).

### Decision needed

- **(a)** *(Recommended, scoped as P3b)* Work only the subset that unblocks GAP-003 — the names on
  the Perseus/Danae/Gorgon lines and anything else gold-question-load-bearing — plus bucket 1's
  unambiguous top names. Carry the long tail to P4 alongside the other review-throughput backlogs.
  **Done 2026-07-27 (DEV-095, DEV-096)** for the load-bearing names and 5 of 7 bucket-1 names.
- **(b)** Work all 367 as one batch. Rejected: it is the same undifferentiated-bulk-triage shape that
  made DEV-084's 48-pair pass slow, and buckets 2/3 need per-name source verification anyway.
- **(c)** Waive as permanent long-tail, like A1's 39 pairs. Rejected: unlike A1's residue, these are
  **not** duplicates of rows already present — each one is a real, absent piece of the graph (or, per
  bucket 4, actively wrong data about an existing entity).
- **(d)** *(DEV-096)* Investigate the `Ares`/`Arges` and `Sterope`/`Steropes` corruption as its own
  lead. **Done 2026-07-27 (DEV-098)** for those two names — corruption was total, `Ares` recovered
  from 0 to 33 relationships. The **generalization is still open**: whether the same near-miss
  extraction confusion recurs for other major names in the candidate set. Cheapest next step is the
  **A7** check (confirmed entity, high corpus frequency, zero candidate rows), which turned this
  from a manual hunt into a mechanical sweep. **Built 2026-07-27 (DEV-099)**; its 6 findings are the
  next data batch.

### Stage P4 Track H (DEV-108, 2026-07-28) — 12 more bucket-1 names landed, 3 translation-spelling
aliases caught, 3 more bucket-2 collisions confirmed, long tail explicitly deferred

Re-ran the drilldown live: unknown-name count **362 → 359** even before this batch touched
anything (small drift from intervening candidate-JSON edits, e.g. the Pyramus/Thisbe rows added in
DEV-100). Full ranked list captured (359 entries, `/tmp/unknown_names_full.txt` at triage time, not
committed — reproduce with `compute_drop_accounting` over the live candidate files).

**12 names added** (bucket 1, each verified against its actual candidate relationship rows before
adding — not added by reference-count alone): `Alcinous`, `Arete` (mortal, Phaeacian king/queen —
added as a pair since every row ties them together), `Pegasus`, `Amphitrite`, `Chiron`, `Chrysaor`,
`Argus Panoptes`, `Nessus`, `Rhadamanthys`, `Epaphus`, `Tisiphone`, `Hippolyte`. Unlocked **75**
previously-dropped relationship rows (V11 3295→3370, before the alias corrections below settled it
at 3365). `entities_candidates_confirmed_v1.json` +12 (net; see the self-caught error below).

**3 translation-spelling aliases, not new entities** — caught by checking each high-reference name
against the *already-confirmed* set before treating it as a gap:
- `Aesculapius` → `Asclepius` (Frazer's Apollodorus / More's Ovid use the Latinized spelling;
  Evelyn-White's Homeric Hymns translation, already confirmed, uses the Greek).
- `Phorcus` → `Phorcys` (already-confirmed sea god; same figure, translation spelling variant).
- `Helios` → `Helius` — **not caught before adding, only after**: `Helios` was added as bucket 1,
  then A1's transliteration pass (run as part of this batch's own fix-loop verification, not
  skipped) fuzzy-matched it against the already-confirmed `Helius` at 83.3 — same sun god, same
  parentage (Hyperion), same children (Circe, Aeetes), across the same sources. Reverted from the
  entities file and re-added here as an alias instead, canonical kept as `Helius` since it was the
  one already confirmed. Recorded as a positive example, not just a fix: running the **full** audit
  suite after a batch, not only the checks that seem relevant to what changed, is what caught a
  self-introduced duplicate before it reached the seeded graph.

**3 more bucket-2 (namesake collision) confirmations**, found by checking each candidate's rows for
internally-inconsistent parentage/identity before adding, the same discipline DEV-096 applied to
`Arges`/`Steropes`:
- `Oenomaus` (7 refs) — the king of Pisa (Pelops's father-in-law, killed by Myrtilus/Pelops per
  Apollodorus) is conflated with an unrelated minor Trojan warrior of the same name, killed in
  battle at `homer-iliad` 5.703 ("and smote Oenomaus, full upon the belly...").
- `Hippolytus` (12 refs) — **at least three** distinct figures conflated: the Giant killed by
  Hermes in the Gigantomachy (Apollodorus 1.5.3-1.6.2), a son of Helios and Rhode (2.1.5), and the
  famous one, Theseus's son (the rest of the rows: killed by his own horses/Poseidon/Theseus,
  parent Hippolyte, Artemis's transformation).
- `Ascalaphus` (13 refs) — **two** distinct figures: the Underworld gardener, son of Acheron and
  Orphne/Gorgyra, turned into an owl by Demeter for tattling on Persephone; and the son of Ares and
  Astyoche, an Argonaut and Orchomenian leader at Troy, killed by Deiphobus (`homer-iliad`
  13.487-13.525) — cleanly split by parentage across the candidate rows themselves.

Two more names were **investigated and left undecided rather than guessed**: `Coronis` (11 refs,
mostly consistent as the mother of Asclepius, but one row — "parent_of Orion's daughters",
`ovid-metamorphoses` 13.685-13.717 — doesn't fit and wasn't resolved) and `Eurynome` (13 refs,
mostly consistent as the Oceanid mother of the Graces, but two rows — "parent_of Asopus", "parent_of
Leucothea" — name parentage attributed elsewhere in standard mythology). Neither added; both need a
closer per-row read before either an add or a bucket-2 call, same caution DEV-096 applied before
committing to `Arges`/`Steropes`.

**Verified clean via the full fix loop, not just the JSON edit**: `seedgen --strict` →
`reseed-local.sh` (three passes — the first caught nothing new, the `Helios` fix required a second,
and `scripts/reseed-local.sh`'s `CLEAR_HISTORY_SQL` needed `'18'`/`'19'` added for a third, the
exact "Detected resolved migration not applied to database" Flyway ordering trap DEV-100 already
hit once for `'14.1'`, recurring here for the same structural reason) → `python -m audit`: **A1
41 pairs (baseline, zero touching the new entities — confirms the `Helios` fix), A3 92 cycles
(unchanged, no new cycle from the additions), A5 clean (0 findings, 42 entity_aliases), A7 still 2
waived (no new corruption found, closing H4's generalization check for this pass)**. Live DB:
entities 2003, relationships 3365, `./gradlew :core-api:test` green (189 tests, independent
Testcontainers verification of V10-V19 applying cleanly from scratch).

**Two new leads flagged for a future batch, not worked here** (explicit, not silent — H6):
1. **Hesiod's personified abstractions** (*Theogony* 211-232, children of Nyx/Eris): `Famine`,
   `Doom`, `Woe`, `Toil`, `Forgetfulness`, `Sorrows`, `Fightings`, `Battles`, `Murders`,
   `Manslaughters`, `Quarrels`, `Lying Words`, `Disputes`, `Lawlessness`, `Ruin`, `Oath`, `Age`,
   `Blame`, `Deceit`, `Friendship`, `Dreams` all appear in the unknown-name list and look like noise
   at a glance (generic English nouns), but are genuine named figures in the source text, not
   descriptive language the extractor over-fired on. Not source-verified row-by-row here; that's
   the batch's own first step.
2. **The Hecatoncheires cluster**: `Cottus` (6), `Gyes` (6), `Briareus` (2), collective
   `Hecatoncheires` (2) — the three Hundred-Handers, siblings of the Cyclopes in Hesiod's
   cosmogony, distinct from the `Arges`/`Brontes`/`Steropes` trio DEV-098 already resolved.

**Everything else is deferred, explicitly, with its bucket**: the residual ~330 names split
roughly into (a) bucket 3 noise — the `<UNKNOWN>` sentinel (133) and ~98 more heuristically-flagged
descriptive/relational phrases ("fall from chariot", "sons of Alcinous", lowercase-leading strings);
(b) a **place-name cluster** with no home in the current schema at all — `entities.type` has no
"place" value, so `Asia`, `Sparta`, `Olympus`, `Thebes`, `Athens`, `Troy`/`Ilios`/`Ilium`, `Sicilia`,
`Persia`, `India` and similar geographic names were never addable as entities under this data model,
a schema-scope limitation worth its own note rather than a triage miss; (c) **collective/group
nouns** whose individual members already exist or could be added separately but whose plural form
isn't itself a single entity (`Titans`, `Giants`, `Trojans`, `Argonauts`, `Amazons`, `Erinyes`,
`Dioscuri`, `Gorgons`, `Graiae`, `Charites`, `Horae`, `Fates`/`Moerae`); (d) ~230 remaining
individual-name candidates not yet source-verified, several visibly high-value for a next batch —
`Tiresias` (5, the blind prophet — surprising he isn't already confirmed), `Narcissus` (3),
`Calchas` (4, the Greek seer), `Alecto` (4, Tisiphone's sister Erinys, a natural companion add now
that `Tisiphone` exists), `Enceladus` (4, a Giant), `Talos` (4, the bronze automaton). None of these
are waived (option (c) in the Decision-needed list above is still rejected for the same reason it
always was) — they carry forward as P4/P5 leads with this session's own ranked list as the starting
point, not a re-derivation from scratch.

**References:** `ingestion/audit/drop_accounting.py` (A2, unknown-name drilldown);
`ingestion/seedgen/relationships_gen.py` (`_filter_and_dedup`);
`ingestion/extraction/output/entities_candidates_confirmed_v1.json`;
`ingestion/extraction/output/relationships_candidates_cleaned.json` (the `Arges`/`Steropes` rows,
triaged); `docs/DEVIATIONS.md` #DEV-074 (discovery), #DEV-076/#DEV-083 (re-confirmed unchanged),
#DEV-093 (homed), #DEV-096 (5 names landed, `Arges`/`Steropes` finding), **#DEV-098** (`Arges`/
`Steropes` triaged, `Ares` recovered), **#DEV-108** (this pass — 12 more names, 3 aliases, 3 bucket-2
confirmations); `docs/TODO2.md` Stage P3b; `docs/TODO-phase2-stage-p4.md` Track H.

---

## GAP-003 — DATA category floor breach: Q6, Q7, Q8 all stable-fail

**Status:** RESOLVED. All three root causes landed 2026-07-27 — Q6 (root cause 1, **DEV-094**), Q7
and Q8 (root causes 2 and 3, **DEV-095**). DATA reached **100% (5/5)**; overall eval reached
**15/16 (94%), the project's best result to date**
(`evaluation/results/2026-07-27T09-34-14Z__23d7b63__p3b-track-bc-perseus/`). Triaged in Stage P1
Track H3 (`docs/TODO-phase2-stage-p1.md`) as three data-gaps routed "**→ P3**"; P3 landed and
committed (`35fb379`) without any of the three ever appearing in `TODO-phase2-stage-p3.md` or
`TODO2.md`. Given a home 2026-07-27 as Stage **P3b** `[DEVIATED - see DEVIATIONS.md #DEV-093]`,
closed the same day.

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

### Root cause 1 (Q6) — `Hades` and `Hestia` are typed `other_god`, not `olympian` — **RESOLVED 2026-07-27 (DEV-094)**

Gold Q6 "Which Olympians are children of Cronus?" required
`["Zeus","Hera","Poseidon","Demeter","Hestia","Hades"]`. The generated SQL was already **correct**:

```sql
WHERE r.relation = 'parent_of' AND parent.name ILIKE 'Cronus' AND child.type = 'olympian'
```

and the answer was correct *for the data*: "Zeus, Hera, Poseidon, and Demeter". Verified in
`entities_candidates_confirmed_v1.json`: `Zeus`/`Hera`/`Poseidon`/`Demeter` are `type='olympian'`;
`Hades` and `Hestia` were both `type='other_god'`. Route ✓, author ✓, content ✗ — a typing decision,
not a retrieval or generation defect, and the smallest of the three fixes.

This was a genuine editorial question, not just a mistake: whether Hades and Hestia count as
Olympians is contested in the tradition itself, so the fix needed a recorded decision, not a silent
edit. **Resolved by checking the corpus directly** rather than assuming a bare "Twelve Olympians"
list: Hesiod's *Theogony* [869] states plainly that "**Hades trembled where he rules over the dead
below**," placed structurally apart from "**THE OLYMPIAN GODS**" section header [886]; the Homeric
Hymn to Aphrodite [7], by contrast, gives Hestia full divine standing — "**in all the temples of the
gods she has a share of honour... she is chief of the goddesses**." **Decision: retyped `Hestia`
`other_god` → `olympian`; left `Hades` `other_god`**, matching the corpus's own placement of him.
Corrected Q6's `required_keywords` to drop `Hades` (5 names, not 6) as a logged eval-bug per the
DEV-048/DEV-050 precedent, not a silent tune. `V10` regenerated, reseeded, `audit --db` unchanged.
**Eval confirms:** `evaluation/results/2026-07-27T09-13-55Z__e861a17__p3b-track-a-hestia-olympian/`
— Q6 stable-fail → stable-pass, DATA 40% → 60% (floor now met), zero stable regressions vs the last
accepted baseline. Q10's `min_row_count: 12` still holds (13 `olympian`-typed entities now).

### Root cause 2 (Q7, Q8) — the hero Perseus has no extracted relationships at all — **RESOLVED 2026-07-27 (DEV-095)**

`relationships_candidates_cleaned.json` contained **zero** rows with `Perseus` as either `from_name`
or `to_name` (verified live 2026-07-27, 6,902 rows, before the fix). Not dropped — never extracted.
The only Perseus-adjacent rows were `Nestor`/`Anaxibia` → *"Perseus son of Nestor"*, a different
figure. This was the "fourth, separate gap" flagged as untracked under GAP-001 Root cause 3; it lived
here, and is now closed.

Consequences, both live-verified before the fix:
- **Q7** ("Which heroes are children of Zeus?", requires `["Heracles","Perseus"]`) — the SQL was
  correct and returned `Heracles`, `Castor`, `Pollux`, `Arcas`, `Iasion`, `Zethus`, `Ajax`,
  `Arcesilaus`. `Perseus` was absent because no edge existed.
- **Q8** ("List all monsters Perseus encountered.", `expected_route: SQL`) — SQL over an entity with
  no relationships returned nothing, so the handler fell back to RAG. Route ✗, author ✗, content ✗ =
  **0/3**, the only zero in the set.

> **Stale triage correction, still true.** P1's H3 note read "Q7 → data-gap (Zeus→Heracles/Perseus
> edges missing)". The `Heracles` half was **already false by the time this was triaged**:
> `Zeus parent_of Heracles` had been restored as a side effect of ADR-020's joint-parentage landing
> (DEV-090). Only the `Perseus` half was real, which collapsed Q7's root cause into Q8's.

**Resolved** by reading Apollodorus `[2.4.1]`–`[2.4.4]` directly (short enough to hand-verify against
the source, rather than a full extraction pipeline re-run): added `Zeus parent_of Perseus` and
`Danae parent_of Perseus` [2.4.1], and `Medusa killed_by Perseus` [2.4.2], to
`relationships_candidates_cleaned.json`. **Did not** add `Phineus` — reading the passage in full
shows he's a mortal prince (Cepheus's brother) whom Perseus turns to stone, not a monster, so he was
never actually load-bearing for Q8; this corrects the assumption two paragraphs below. Also did
**not** invent a name for the sea monster, which this translation never names — fabricating one
would violate the app's own source-accuracy guarantee. Live-verified after the fix: Q7 now returns
"...Perseus [7]..." cited to `2.4.1`; Q8's route flipped back to **SQL** and returns "Perseus
encountered Medusa [1]..." cited to `2.4.2`.

### Root cause 3 (Q8) — the `Cetus` keyword is unattested in the corpus — **RESOLVED 2026-07-27 (DEV-095)**

Independent of root cause 2, Q8 required `["Medusa","Gorgon","Cetus"]`. Grepped live over
`ingestion/corpus/`: **`Cetus` never appears as a word.** Its only occurrences are inside
`Anicetus` (Apollodorus) and `Lycetus` (Ovid) — two unrelated men. Frazer and More render the
Andromeda sea monster descriptively ("a sea monster"), never by that name. `Gorgon` was also checked
against the real post-fix answer and does not appear either — the generated SQL never selects
`entities.subtype` (where `Medusa`'s `Gorgon` subtype lives), so nothing surfaces it.

This was the brittle-keyword class DEV-048 (`Eris` → `Strife`) and DEV-050 established. **Resolved**
by reducing `required_keywords` to `["Medusa"]` — the one piece of content the live, source-grounded
answer reliably and correctly produces, live-verified across 3 runs. A logged eval-bug fix per the
DEV-048/DEV-050 precedent, not a silent tune; chosen against the real answer, not guessed in advance.

### Decision record

- **Q6** — retyped `Hestia` `other_god` → `olympian`, kept `Hades` `other_god`, dropped `Hades` from
  Q6's keywords. **Done 2026-07-27 (DEV-094).**
- **Q7/Q8** — added 3 source-verified rows from Apollodorus `[2.4.1]`–`[2.4.2]`; deliberately excluded
  `Phineus` (not a monster) and an unnamed sea monster (would require fabricating a name).
  **Done 2026-07-27 (DEV-095).**
- **Q8's keywords** — reduced to `["Medusa"]`, live-verified. **Done 2026-07-27 (DEV-095).**

**Outcome:** Q6/Q7/Q8 all recovered to 3/3. DATA reached **100% (5/5)**; overall eval reached
**15/16 (94%)**, `compare.py` confirms zero stable regressions at every step
(`evaluation/results/2026-07-27T09-13-55Z__e861a17__p3b-track-a-hestia-olympian/` then
`evaluation/results/2026-07-27T09-34-14Z__23d7b63__p3b-track-bc-perseus/`). The only remaining
failure across the full gold set is **Q11** (MIXED, the pre-existing DEV-054 gap, homed to P5b),
untouched by this work. This closes GAP-003 entirely; **GAP-002 remains open** — Track D's broader
367-name backlog was not worked here (`Phineus`, despite appearing in the Perseus passage, is a
genuine GAP-002 name in his own right, just not one Q7/Q8 needed).

**References:** `evaluation/gold-questions.json` (Q6, Q7, Q8);
`evaluation/results/2026-07-26T17-49-26Z__5eed421__p3-j5-ouranos-merge-fixed/` (pre-fix baseline),
`evaluation/results/2026-07-27T09-13-55Z__e861a17__p3b-track-a-hestia-olympian/` (Q6 fixed),
`evaluation/results/2026-07-27T09-34-14Z__23d7b63__p3b-track-bc-perseus/` (Q7/Q8 fixed);
`ingestion/extraction/output/entities_candidates_confirmed_v1.json` (`Hades`/`Hestia` typing);
`ingestion/extraction/output/relationships_candidates_cleaned.json` (`Zeus`/`Danae parent_of Perseus`,
`Medusa killed_by Perseus`); `core-api/src/main/resources/db/migration/V11__seed_relationships.sql`;
`docs/TODO-phase2-stage-p1.md` H3 (the original triage); `docs/DEVIATIONS.md` #DEV-047 (first
sighting, Stage 5), #DEV-048/#DEV-050 (the keyword-fix precedent), #DEV-090 (fixed Q7's `Heracles`
half), #DEV-093 (homed), #DEV-094 (Q6 fixed), #DEV-095 (Q7/Q8 fixed); `docs/TODO2.md` Stage P3b;
**GAP-002** (`Phineus` overlap, still open).

---

## GAP-004 + GAP-006 — the `Saturn`→`Cronus` and `Ajax` entity merges

**Status:** BOTH RESOLVED 2026-07-29 (**DEV-121**), worked as **one pass** because both entries had
independently concluded the fix was "an A1-class entity merge, belongs with the other one". Read the
summary-table rows above for what each gap *was*; this section records how they closed and, more
usefully, the three things the merge found that neither entry predicted.

### What landed

| | before | after |
|---|---|---|
| `Ajax` entities | **16** (see below — GAP-006 said 15) | **2** |
| `Saturn` | separate `other_god` entity | `entity_aliases` row → `Cronus` |
| confirmed entities | 2003 | **1989** |
| seeded `relationships` (V11) | 3369 | **3364** |
| live `entity_aliases` | 42 | **58** |

Canonical names follow this project's own precedent (DEV-078/079/080/081/082) — the bare name stays
with the more central, more-referenced figure, the namesake takes a `Name (descriptor)` form:
**`Ajax`** = the Telamonian (49 of the 54 bare-name candidate rows are his) and
**`Ajax (son of Oileus)`** = the Locrian, matching `Cecrops (son of Erechtheus)` /
`Pandion (son of Cecrops)` / `Ilus (son of Dardanus)`.

**Every one of the 73 cluster rows was assigned by reading its cited passage, not by its surface
form.** That is what caught five bare-`Ajax` rows that are really the *Locrian* — Iliad 15.328
("Medon … son of godlike Oïleus, and brother of Aias"), the two funeral-games rows at 23.473/23.753
("swift Aias, son of Oïleus"), and Apollodorus E.6.6's shipwreck. Surface-form matching alone would
have filed all five under the Telamonian.

### The three findings the merge surfaced, which neither gap entry predicted

1. **`Ops` is a namesake collision.** Rewriting `Saturn married_to Ops` mechanically would have
   produced `Cronus married_to Ops` — where the *confirmed* `Ops` is the **male** Ops of the Odyssey,
   Eurycleia's father ("Eurycleia, daughter of Ops, son of Pisenor"), not Ovid's Roman Ops. The row
   was repointed to `Rhea`, who is who Ovid actually means. This is the DEV-096 `Arges`/`Steropes`
   lesson repeating: **check the rows, not the name**, before any bulk rewrite.
2. **`Oileus` is a namesake collision too.** `Oïleus killed_by Agamemnon` (Iliad 11.84) is Bienor's
   *charioteer*, not the Locrian king — who is alive for another twelve books. Split off as
   `Oileus (charioteer of Bienor)`.
3. **There was a sixteenth Ajax-cluster duplicate, and this pass introduced a defect by missing it.**
   `Oïleus` (with diaeresis) was *itself* a confirmed entity, not merely an unconfirmed surface form.
   The initial sweep grepped ASCII `oile` and the diaeresis defeated it — the same non-ASCII blind
   spot DEV-118 hit with `Athene`/`Athena`. It was caught by **A5** on the first post-merge audit
   (*"'Oïleus' is both an entity_aliases.alias and an existing entities.name"*), i.e. by running the
   **full** suite after the batch rather than only the checks that looked relevant — the DEV-108
   `Helios` discipline catching a self-introduced duplicate for the second time. **A1 scores the pair
   83.3, under its 88 threshold**, so A1 would never have surfaced it either.

### Direction errors fixed along the way

Six reversed edges, each verified against its own passage and fixed as a **swap, not a delete** (the
DEV-118 rule — the kinship or kill is real and cited, only the direction was wrong):
`Ajax the Lesser parent_of Oïleus` — the one GAP-006 predicted **A11 structurally cannot see**,
because the fragmented name never appears in the corpus in the patronymic formula A11 keys on — plus
five `killed_by` rows where Ajax is the *killer*: Satnius (14.440), Archelochus (14.463), Caletor
(15.419), Laodamas (15.516), and Apollodorus E.6.6, where Poseidon kills Ajax rather than the
reverse. Two further rows were dropped as unsupported by their own cited passage (the DEV-098 shape):
`Ajax killed_by Hector` @ Ovid 13.82-13.127 and `Ajax killed_by Odysseus` @ 13.280-13.312 — the
latter's claim is real in Ovid but sits at 13.386ff, and moving the ref would be inventing provenance.

### Verification

Full fix loop, not just the JSON edit: `seedgen --strict` → `reseed-local.sh` (two passes — the first
is what surfaced the `Oïleus` defect above) → `python -m audit` → `runner --runs 3` → `compare.py`.
Audit ends **PASS or WAIVED on every check except A3's 87 candidate-layer cycles** — identical to the
pre-pass gate state; A5 PASS, A11 PASS, A1 unchanged at 41 waived pairs, live `parent_of` graph still
acyclic. Eval **20/25 = 80%**, zero transport errors, `compare.py` **zero stable regressions, exit 0**
(`evaluation/results/2026-07-29T13-06-08Z__e5e8ad9__gap004-gap006-entity-merge/`). Suites: ingestion
344, `./gradlew :core-api:test` green.

**Live behaviour, confirmed rather than inferred from row counts:** `Ajax (son of Oileus)` now holds
one coherent 8-edge biography — father Oileus, brother Medon, kills Cleobulus and Satnius, drags
Cassandra, drowned by Poseidon, buried by Thetis — where the same facts were previously scattered
across six entities with the parentage pointing backwards. `GET /api/v1/conflicts/Telamonian%20Aias`
resolves through the new alias and returns the Telamonian's claims.

### New leads, recorded rather than worked

- **A11 has no non-parentage sibling.** Five of the six direction errors here were `killed_by`, which
  no audit check looks at; they were found only because a merge happened to walk those rows. A
  `killed_by` direction check is the obvious A11 companion.
- **`Ops parent_of Pisenor` is reversed** the same way (the Odyssey says Ops is the *son* of
  Pisenor). Noticed while checking `Ops`, left unfixed as outside this pass.
- **32 A6 waivers are stale for reasons predating this pass.** Measured, not assumed — A6 was re-run
  against the pre-pass candidate files, which shows 50 stale before and confirms the 6 removed here
  are exactly the ones this pass caused. The other 32 are a separate cleanup.

**References:** `docs/DEVIATIONS.md` #DEV-121; `core-api/src/main/resources/db/migration/V20__add_entity_aliases_ajax_and_saturn.sql`;
`ingestion/extraction/known_aliases.json`; `ingestion/extraction/output/entities_candidates_confirmed_v1.json`,
`relationships_candidates_cleaned.json`; `ingestion/audit/duplicate_entities.py` (A1's 88 threshold),
`ingestion/audit/integrity.py` (A5, which caught the self-introduced duplicate),
`ingestion/audit/parentage_direction.py` (A11, and its recall limit); `docs/DEVIATIONS.md` #DEV-119
(where both gaps were filed), #DEV-118 (the swap-not-delete rule), #DEV-108 (the `Helios` precedent),
#DEV-096/#DEV-098 (check the rows, not the name).

### Findings this pass did **not** fix

Written up after the fact, when the pass was checked for unrecorded findings (the DEV-115/DEV-119
discipline). Four things were found and none had been written down; the first is now **GAP-007**.

1. **`Zeus parent_of Ajax` is live in the seeded graph — see GAP-007 below.** Not a dropped rival:
   it is a seeded edge, and it is why gold **Q7** ("Which heroes are children of Zeus?") lists
   `Ajax` alongside Heracles and Perseus.
2. **GAP-006's own prediction about DEV-110 is disproved — and the real mechanism is more useful.**
   GAP-006 argued the fragmentation "plausibly explains DEV-110's otherwise-odd finding that `Ajax`
   had *no* promotable `marriage`/`epithet` candidates", since the evidence was split 22-vs-15
   across the cluster. Measured after the merge: `Ajax` still has **zero** of either
   (46 `parentage` + 17 `death` + 4 promoted `notable`, and nothing else). So splitting was never
   the cause. The epithet material was never shaped as `epithet` *claims* at all — it was extracted
   as **entity names** (`Telamonian Aias`, `Great Ajax`, `Aias the less`), which is exactly where
   this pass has now put it: as `entity_aliases` rows. The evidence wasn't lost, it was mis-typed,
   and de-fragmenting is what converts it into the right shape.
3. **8 `Telamon | parentage | child of Ajax` candidates sit at `trust_tier=3`.** Telamon is Ajax's
   *father*; this is F3's reversed-direction shape (DEV-114) in `variant_claims`. They are
   unreviewed, so nothing reaches runtime, and they were left untouched — but they are more of the
   same population, not a one-off.
4. **A1's 88 threshold misses a measurable class, not just one pair.** `Oileus`/`Oïleus` scores
   **83.3** and `Helios`/`Helius` (DEV-108) scores **83.3** — identically — with
   `Diomed`/`Diomedes` (DEV-100) at **85.7**. Three independent, real duplicates clustered in
   83-86, each caught after the fact by a *different* check (A5, A1-after-adding, A7). The pattern
   argues for a **diacritic-folding pre-pass** rather than a threshold nudge: folding takes
   `Oileus`/`Oïleus` to 100 without loosening anything else, whereas dropping the threshold to 83
   would admit the long tail A1 already waives 41 pairs of.

---

## GAP-007 — `Zeus parent_of Ajax` is seeded live, from a Homeric vocative formula ADR-020 reads as joint parentage

**Status:** **RESOLVED 2026-07-29 (DEV-122).** Found 2026-07-29 while verifying the GAP-004/GAP-006
merge (DEV-121), fixed in the next pass. The entry below is preserved as written; the resolution and
the sweep's measured result are appended at the end.

### Symptom

```
SELECT f.name FROM relationships r ... WHERE r.relation='parent_of' AND t.name='Ajax';
  Telamon  [apollodorus-bibliotheca 3.12.7-3.13.4]
  Telamon  [homer-iliad 6.1-6.50]
  Telamon  [homer-odyssey 11.538-11.581]
  Telamon  [ovid-metamorphoses 13.1-13.42]
  Zeus     [homer-iliad 7.206-7.243]     <-- live, and wrong
```

`Ajax` therefore appears in the answer to gold **Q7** ("Which heroes are children of Zeus?")
alongside Heracles and Perseus. Q7 still passes — its `required_keywords` are `Heracles`/`Perseus`
— so this has been shipping unnoticed since before DEV-095 quoted that answer.

### Root cause — this is **not** an extraction error

The two candidate rows cite Iliad `7.233` and `9.643`, and both passages say exactly this:

> "Aias, **sprung from Zeus**, thou **son of Telamon**, captain of the host…"

A Homeric vocative formula: one real parent, one divine honorific, in a single line. The extractor
recorded what the text says. What turns it into a seeded edge is **ADR-020's co-mention
discriminator**: `Telamon` and `Zeus` share a `(source_id, passage_ref)`, so they qualify as a
*co-mention pair*, and the pair contains the canonical winner (`Telamon`), so rule 2 keeps both.

**None of the first three rules can catch this**, by construction:
- **Rule 1 (contested-aware)** — the extractor never set `is_contested`; the source is not
  presenting alternatives, it is being formulaic.
- **Rule 2 (winner-anchored)** — `Telamon` *is* the winner and `Zeus` is in the pair, so anchoring
  admits it rather than excluding it.
- **Rule 3 (corroboration-ranked)** — only ranks among qualifying pairs; this is the only one.

This is exactly what **rule 4, the hand-maintained deny-list, exists for** — and that list is still
seeded with `Io` alone, as ADR-020 shipped it. So the fix is a deny-list entry, not a rule change:

```
(child='Ajax', pair={'Telamon','Zeus'}, reason='Homeric vocative formula "Aias, sprung from Zeus,
 thou son of Telamon" (Iliad 7.233, 9.643) -- one parent + one honorific, not two co-parents')
```

### Why it deserves its own gap rather than a one-line fix in DEV-121's pass

The mechanism generalises. **"X, sprung from Zeus"** and its relatives are standing Homeric
formulae, so any hero addressed that way in the same line as a real parent is a candidate for the
same false co-parent — this is the `relationships` counterpart of the Homeric-formula misreads
**DEV-112 (F2)** caught and rejected behind the `variant_claims` review gate. The same structural
argument DEV-118 made for direction errors applies here: `relationships` is **seeded, not
review-gated**, so this class reaches users where the `variant_claims` half never did.

The right next step is therefore a **sweep, not a single deny-list row**: enumerate every child
whose ADR-020 co-mention pair contains a god co-named by a formula, and deny-list the ones that
verify. Cheapest detector: for each multi-parent child in the seeded graph, re-read the co-mention
passage and check whether the divine parent appears only inside an epithet construction.

### Resolution (DEV-122, 2026-07-29) — the sweep was run, and it is small

This entry asked for "a **sweep, not a single deny-list row**". The sweep was run before the fix, and
the reason it is cheap is that **the formula class is Homeric**: `"sprung from Zeus"` and its
relatives occur **49×** in the *Iliad*, **43×** in the *Odyssey* and **1×** in the Homeric Hymns, and
**zero times** in Apollodorus, Hesiod's *Theogony*, or Ovid — measured across all six corpus files,
not assumed from genre. So only edges resting on Homer/Hymns can carry it. Narrowing the seeded graph
that way:

| slice | count |
|---|---|
| children with ≥2 seeded parents | 534 |
| …where one parent is a major god | 98 |
| …where the divine parent is attested **only** by Homer/Hymns | **3** |
| single-parent children whose only parent is a god, attested only by Homer/Hymns | **3** |

All six were read against their cited passage:

- **`Ajax <- Zeus` — false, fixed.** The vocative formula, live in the corpus at **three** refs
  (7.233, 9.643, **11.456**), not the two GAP-007 named. The deny-list is keyed on child + parent
  pair rather than passage, so one entry covers all three.
- **`Molione <- Poseidon` — genuine, kept.** Iliad 11.737 states it outright and non-formulaically:
  *"the two Moliones, of the blood of Actor, but that **their father, the wide-ruling Shaker of
  Earth**, saved them"* — a real dual mortal/divine parentage alongside `Actor`.
- **`Pandia <- Zeus` — genuine, kept.** Homeric Hymn 32.14: *"the Son of Cronos was joined with her
  in love; and she conceived and bare a daughter Pandia."*
- **`Naiads <- Zeus`, `Nymphs of the fountain <- Zeus` — genuine, kept.** *"Naiad Nymphs, daughters
  of Zeus"* / *"Nymphs of the fountain, daughters of Zeus"*, a genealogical claim Homer repeats, not
  an honorific attached to a mortal.
- **`Ate <- Zeus` — a *different* defect, now GAP-008.** Not the formula: the cited passage
  (9.496-9.528) states a parentage of the **Prayers**, not of Ate. Recorded, not fixed.

**Also fixed on the `variant_claims` side, so both halves of the class agree:** `Ajax` carried five
unreviewed formula rows (`child of Zeus` ×2, `sprung from Zeus` ×2, `son of Telamon, sprung from
Zeus`) at `trust_tier=3`. All five were verified against the same three passages and rejected to
`trust_tier=2`, extending DEV-112/F2's identical verdict on `Patroclus | parentage | sprung from
Zeus`. Nothing seeded changed — they were never promoted — but leaving them would have left the same
claim approved-shaped on one side and denied on the other.

**References:** `docs/adr/adr-020-joint-parentage-multi-edge.md` (the four-part rule and the
deny-list); `ingestion/seedgen/canonical_edge.py` (`build_comention_pairs`, `load_deny_list`);
`ingestion/extraction/parentage_deny_list.json` (the new entry);
`ingestion/corpus/homer_iliad_murray1924.txt` `[233]`, `[643]`, `[465]`;
`evaluation/gold-questions.json` (Q7); `docs/DEVIATIONS.md` #DEV-121 (found here), **#DEV-122**
(fixed here), #DEV-112 (the `variant_claims` half of the same formula class), #DEV-118
(seeded-vs-review-gated argument).

---

## GAP-008 — the misattributed-passage shape has never been swept in the *seeded* `relationships` table

**Status:** **Open** — found 2026-07-29 (DEV-122) as a by-product of GAP-007's sweep, which read
every single-parent divine edge as well as the co-parent ones. One confirmed instance; the class is
unmeasured.

### The instance

```
Zeus parent_of Ate   [homer-iliad, 9.496-9.528]   <-- live, and cites the wrong passage
```

The cited passage is the Litai simile in Achilles' embassy scene. What it actually says is:

> "For **Prayers are the daughters of great Zeus**, halting and wrinkled... Now whoso revereth the
> daughters of Zeus... then they go their way and make prayer to Zeus, son of Cronos, **that Ate may
> follow after**"

Ate is named in the passage, and a parentage is stated in the passage — but they are not the same
claim. The daughters are the **Prayers**; Ate is what the Prayers ask Zeus to send. The extractor
merged the two.

**The claim itself is true**, which is what makes this awkward rather than a simple delete. Homer
does say it, at **19.90**: *"Eldest daughter of Zeus is Ate that blindeth all — a power fraught with
bane."* So the row is right about the fact and wrong about the provenance.

### Why it is left unfixed rather than patched

Both available fixes cost something this project has explicitly refused before:

- **Drop the row** (the DEV-098/DEV-121 treatment for "unsupported by its own cited passage") throws
  away a genuine, corpus-attested parentage.
- **Move the ref to 19.90** is what DEV-121 called inventing provenance, when it dropped
  `Ajax killed_by Odysseus` rather than repoint it from 13.280-13.312 to the real 13.386ff.

A third option — re-extract that passage — is out of scope for a data pass. This needs a decision on
which cost to pay, and the decision should be made once for the whole class, not once for Ate.

### Why it is its own gap

The shape is **known**: DEV-119 catalogued it as bucket (4) of the A6 triage, with **18** instances
among *dropped* parents (`Achilles <- Zeus` citing an Idomeneus battle scene, `Diomedes <- Xuthus`
citing an Athamas/Ino passage, `Zeus <- Styx`/`Zeus <- Pallas` citing the Theogony's Oceanid roster),
and DEV-121 hit it twice more among Ajax's `killed_by` rows. Every one of those was found in
candidate rows that were **dropped or review-gated**. Nobody has swept the rows that are **seeded**,
and that is the same seeded-vs-review-gated asymmetry GAP-007 turned on and DEV-118 argued in
general: `variant_claims` has a human gate, `relationships` does not, so a defect of identical shape
reaches users on one side and not the other.

### The proposed detector was built, measured, and does not work — 2026-07-29 (DEV-123)

This entry originally proposed: *"for each seeded `parent_of` edge, check that the cited passage
contains the child's name and the parent's name inside one kinship construction… A11's `_KINSHIP`
regex is most of the machinery already."* That was implemented as A13 and run against the full
corpus. **It flags 82% of 5,259 citations** (4,355), and the flagged rows are overwhelmingly
correct data phrased in ways no regex recognises. Two rounds of vocabulary widening — adding
`begat`/`bare`/`had by`/`sire of`/possessives, and fixing a real recall bug in A11 along the way —
moved it only from 87% to 82%, because the residue is structural, not lexical:

| failure mode | worked example |
|---|---|
| **Enumeration** | Apollodorus 3.12.5 lists ~40 sons of Priam after one verb — **252 characters** from "Priam had sons" to "Echephron". Any word budget wide enough destroys precision everywhere else. |
| **Relative clause** | Hymn 31: "Helios **whom** mild-eyed Euryphaessa … **bare** to the Son of Earth" — inverted order, pair separated. |
| **Coordination** | Apollodorus 1.9.1: "Aeetes, son of the Sun …, **and brother of** Circe and Pasiphae" states `Sun parent_of Pasiphae` only by inference across two clauses. |
| **Periphrasis** | Iliad 19 calls Patroclus "the valiant **son of Menoetius**" — the kinship is stated about someone the clause does not name. |

Closing these needs a parser or an LLM pass, and an LLM pass would reintroduce exactly the
extraction step whose errors the check exists to catch. **So GAP-008 stays open, and the
construction-matching approach is now a recorded dead end rather than an untried idea.**

**What did ship** is the decidable part of the same scope: A13 verifies that every edge's
`passage_ref` **resolves to a real segment**. That caught all four hand-added rows whose citations
pointed at nothing (DEV-095's Perseus pair @ `2.4.1`, DEV-100's Thisbe pair @ `4.55-4.80`), which
were corrected and now PASS. It does not address the Ate row, which cites a passage that exists.

**References:** `core-api/src/main/resources/db/migration/V11__seed_relationships.sql`
(`Zeus parent_of Ate`); `ingestion/corpus/homer_iliad_murray1924.txt` `[502]` (the Litai passage) and
`[90]` (where the claim is actually made); `ingestion/audit/parentage_direction.py` (A11, the natural
host); `docs/DEVIATIONS.md` #DEV-119 (the 18 dropped-parent instances), #DEV-121 (the two `killed_by`
instances and the do-not-move-a-ref rule), **#DEV-122** (found here).

---

## GAP-009 — Fuzzy-match false positives fold a spelling-distinct name onto an unrelated confirmed entity

**Status:** **Open** — found 2026-07-31 during Stage P5 Track C's `variant_claims` review
(DEV-136/137/138), a byproduct of per-row adjudication rather than a dedicated sweep. Only a
handful of confirmed instances so far — this gap is deliberately kept separate from GAP-010 (below)
because the mechanism and the fix are different, even though both surface as "wrong parentage" to a
reviewer.

### The mechanism

`ingestion/extraction/entity_resolver.py`'s `EntityResolver` dedupes a newly-extracted name against
the running candidate/confirmed set in three steps: exact match, `known_aliases.json` lookup, then a
rapidfuzz fuzzy match at threshold 88. The fuzzy step (and, separately, a legitimate
`entity_aliases`/`known_aliases.json` row applied outside the context it was curated for) can attach
a name from the source text to the **wrong** already-established entity, even though the text's own
spelling is genuinely different from that entity's name.

### Confirmed instances

| text's actual spelling | resolved to | should have been |
|---|---|---|
| "Mestor, **Atas**, Doryclus" (Apollodorus 3.12.5, one of Priam's ~50 sons) | the Titan `Atlas` (Iapetus's son, father of Calypso/the Pleiades, many sources) | a distinct, unrelated, very obscure son of Priam — not confirmed as a separate entity |
| "**Philaemon**" (Apollodorus 3.12.5, another son of Priam) | `Philammon` (Apollo's son, father of the musician Thamyris, apollodorus) | same as above |
| "**Aeacus**" (Apollodorus 3.12.5 names Priam's first son by Arisbe as "Aesacus," who mourns Asterope and turns into a bird) | `Aeacus` the underworld judge (Zeus and Aegina's son, father of Peleus, 3+ sources) | "Aesacus" is not currently a confirmed entity at all — the two names are one letter apart and the resolver treats them as the same |
| "**Pluto**" (Hesiod *Theogony* 346-403, one of 3,000 Oceanid daughters — "soft eyed Pluto") | `Hades`, via the general `entity_aliases` row `Pluto`/`Dis`→Hades (correct in most contexts, since Pluto is a genuine Hades epithet) | a distinct, unrelated, unconfirmed Oceanid nymph |

The `Pluto`→Hades case is structurally different from the other three: it is not a fuzzy-threshold
problem at all, but a *correct* alias applied in a context where it does not hold. Tightening
`rapidfuzz`'s threshold would not touch it — only a context check (does the surrounding sentence
actually support this being Hades?) could, which is closer to GAP-010's territory than a
`entity_resolver.py` tuning fix.

### Why it is its own gap, distinct from GAP-010

Both gaps produce the same symptom for a Track C reviewer — a `variant_claims` candidate whose
subject is really a different person than the established entity of that name — but the fix differs
completely:

- **GAP-009** (this entry) is a **near-miss** problem: the corpus text spells the name differently
  from the entity it got attached to (`Atas`≠`Atlas`, `Aeacus`≠`Aesacus`). In principle this is
  addressable by raising `entity_resolver.py`'s fuzzy threshold, adding a blocklist for known
  problem pairs, or requiring the fuzzy match to also check for existing incompatible relationships
  before merging.
- **GAP-010** is an **exact-match** problem: the string in the corpus is byte-identical to an
  unrelated entity's name, because the ancient corpus itself reuses the name for two different
  people. No threshold tuning can fix this — the two GAP-009 examples above where the surface form
  *is* identical (`Pluto`, and any future exact-string collision) actually belong to GAP-010's
  territory once the alias/fuzzy step is not the proximate cause.

### What a fix needs to decide

1. Whether to raise the rapidfuzz threshold above 88, and by how much, without losing the recall
   that threshold was originally tuned for (re-check against `entity_resolver.py`'s own test
   fixtures and the corpus-wide dedup rate before changing it).
2. Whether `entity_aliases` rows like `Pluto`→Hades should carry a scope restriction (e.g. only
   apply when no unresolved candidate name already exists under a different confirmed entity in the
   same passage) — this would need a schema or lookup-order change, not just a threshold change.
3. A confirmed count: this gap has not been swept systematically, only found incidentally during
   Track C row review. A dedicated pass (grep the fuzzy-merge log `EntityResolver.fuzzy_merges`
   already emits at extraction time, per `run_extraction.py`'s `write_output`) would give a real
   denominator before deciding whether a code fix is worth it.

**References:** `ingestion/extraction/entity_resolver.py` (`EntityResolver`, rapidfuzz threshold);
`ingestion/extraction/known_aliases.json`; `docs/DEVIATIONS.md` #DEV-136/#DEV-137/#DEV-138 (where
each instance was found and rejected in `variant_claims` review).

---

## GAP-010 — Exact-name namesake collisions: the corpus reuses one name for unrelated figures, and extraction merges them into one entity

**Status:** **Open** — found 2026-07-31 during Stage P5 Track C's `variant_claims` review
(DEV-136/137/138). **≥82 confirmed instances across the first 7 passages reviewed**, roughly 20-30%
of all tier-3 rows adjudicated so far — by far the largest single cause of rejection in every batch.
Unlike GAP-009, this is not a near-miss: the colliding names are byte-identical strings, so no
fuzzy-threshold change can address it.

### The mechanism

Greek myth is full of legitimate namesakes — many different "Ajax"es, "Iphis"es, minor catalogue
figures sharing a name with a major god or hero purely by coincidence of an English translation's
word choice. `entities.name` is not unique-by-construction in the *source material*, but the
extraction/resolution pipeline treats a matching string as the same person by default (this is
*correct* the overwhelming majority of the time — it is what lets "Zeus" resolve consistently across
all six sources — and only fails on the minority of names that really do denote two different
people). Nothing downstream currently checks whether a newly-attached fact is *compatible* with what
that entity is already established to be.

### Confirmed instances (a representative sample, not the full 82+)

| shared name | identity #1 (already established) | identity #2 (the collision) | found in |
|---|---|---|---|
| `Idomeneus` | the Cretan king, Deucalion's son (3 sources) | one of Priam's ~50 obscure sons | `apollodorus-bibliotheca 3.12.5` |
| `Lycaon` | the Arcadian king turned to a wolf by Zeus (35+ existing rows) | another of Priam's sons | `apollodorus-bibliotheca 3.12.5` |
| `Urania` | the Muse, Zeus and Mnemosyne's daughter (2 sources) | a minor Oceanid nymph | `hesiod-theogony 346-403` |
| `Europa` | Agenor's daughter, the abduction story (2 sources) | a minor Oceanid nymph | `hesiod-theogony 346-403` |
| `Rhode` | Poseidon and Amphitrite's daughter, the Sun's wife (apollodorus) | a minor Oceanid nymph ("Rhodea") | `hesiod-theogony 346-403` |
| `Agave` / `Autonoe` | Cadmus and Harmonia's daughters, Theban royalty (multiple sources) | minor Nereid-catalogue nymphs — **and `entities.subtype='nereid'` is set on both, meaning this specific collision happened at original entity extraction, not later review** | `apollodorus-bibliotheca 1.2.1-1.2.7`, `2.1.5`, `hesiod-theogony 233-269` |
| `Amphictyon` | a legendary early king of Athens (own `killed_by`/`killed` facts) | Amphitryon, Heracles' stepfather and Alcmena's husband — the text's own word is "Amphitryon," not "Amphictyon" | `apollodorus-bibliotheca 2.4.5` |
| `Lynceus` | Aphareus's son, the sharp-eyed Argonaut killed by Pollux (3 sources) | Egyptus's son, Hypermnestra's husband and Abas's father — **this passage's own central plot thread** | `apollodorus-bibliotheca 2.1.5` |
| `Cronus` | the Titan, Zeus's father (many sources) | "Coronus," a mortal, in the source text | `apollodorus-bibliotheca 3.10.8-3.11.1` |
| `Perses`/`Perseus` | conflated across a **promoted** (`trust_tier=1`, live) `variant_claims` row | — | `apollodorus-bibliotheca 2.4.5` |

### Why this is more serious than a candidate-review nuisance

Three instances have already reached data with **no review gate at all**, or past the gate that
exists:

1. `relationships` (mechanical, no human gate — CLAUDE.md's Data Model section) already has
   `Cronus parent_of Leonteus`, which should read `Coronus parent_of Leonteus`.
2. `relationships` already conflates Amphitryon and Amphictyon across several rows tied to
   `apollodorus-bibliotheca` `2.4.5`/`2.4.6`/`2.4.7-2.4.8`/`1.8.2`.
3. A `variant_claims` row conflating Perses/Perseus is already **promoted** (`trust_tier=1`) — i.e.
   it passed ADR-004's human review gate at some point before Stage P5 and is live today.

None of the three are fixed by this entry. Each needs its own dedicated look (a `relationships` fix
is a mechanical no-gate edit like any other; the promoted `variant_claims` row needs a demotion
decision through the normal keyed workflow, not a silent edit) — recorded here so a future session
can pick either up without re-deriving the finding.

### What a fix needs to decide

This is real per-entity work, not something a detector alone can close — a detector can only narrow
where to look, the way the review batches were already narrowing it by hand:

1. **Detection**: a lightweight check (candidate for the audit package's next budgeted slot, or a
   `claim_evidence.py` helper feeding `review_passage`'s bucket output) that flags a candidate row
   whose subject already has an established relationship *incompatible* with what the current
   passage claims — e.g. two different confirmed parents from unrelated myth-cycles with no shared
   source. This does not fix data; it turns the manual DB cross-reference Track C reviewers have
   been doing by hand into a reusable signal.
2. **Splitting**: for each confirmed collision, decide whether to split the entity using the
   existing `Name (descriptor)` convention (already used elsewhere, e.g. `Cleopatra (daughter of
   Tros)`, and the precedent for the reverse problem — over-fragmentation — in GAP-006's Ajax merge).
   Splitting requires re-deriving which already-seeded/promoted rows belong to which identity, which
   is exactly the kind of per-row judgment DEV-121's Ajax merge did, at whatever scale the confirmed
   collision list reaches.
3. **Budget**: at ≥82 confirmed instances from only 7 of 1,059 passages, the true count across the
   full Track C backlog is plausibly in the hundreds — this needs a scoping decision (fix the top-N
   by prominence first, like the D-track's own bounding exercise, rather than open-ended splitting)
   before work starts, per this stage's own "size the budget from the exit criteria" discipline
   (`docs/TODO-phase2-stage-p5.md` Track D).

**References:** `docs/DEVIATIONS.md` #DEV-136/#DEV-137/#DEV-138 (where each instance was found);
`docs/DATA-GAPS.md` GAP-006 (the Ajax over-fragmentation precedent, the inverse problem, and the
`Name (descriptor)` splitting convention); `ingestion/extraction/entity_resolver.py` (where a
collision could in principle be flagged, though the current resolver has no compatibility check of
any kind); `core-api/src/main/resources/db/migration/V11__seed_relationships.sql` (`Cronus
parent_of Leonteus`, the confirmed seeded instance).
