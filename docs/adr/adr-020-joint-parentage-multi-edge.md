# ADR-020: Joint Parentage — Genuine Co-Parent Couples Keep Multiple `parent_of` Edges

| Field        | Value       |
|--------------|-------------|
| **Date**     | 2026-07-23 (amended 2026-07-26) |
| **Status**   | Accepted (amended 2026-07-26; **implemented and landed 2026-07-26 — see DEV-090** / `docs/DATA-GAPS.md` GAP-001. DEV-088 recorded the pre-implementation amendment; DEV-090 is the actual landing, including a Deimachus entity split done as J4a-8 and a token-budget regression found and fixed in the same pass. Not yet committed to git.) |
| **Amends**   | ADR-007 §6 (single-canonical-edge rule — narrows it with a co-parent carve-out) |
| **Amended by** | —         |
| **Supersedes** | —         |

---

## Context

ADR-007 §6 set the policy that `relationships` holds **one canonical edge per fact**, with any
contradiction recorded in `variant_claims`. The stated reason was traversal cleanliness: two
contradictory `parent_of` edges for one child would branch every `WITH RECURSIVE` lineage walk and
force every DATA query to disambiguate.

That rule conflated two structurally-identical but semantically-different situations, and the
resolver (`ingestion/seedgen/canonical_edge.py::resolve_canonical_edges`) cannot tell them apart:

- **Contested parentage** — rival claims about who the one parent is, either across sources or
  enumerated within one (Io's father is "Inachus, or Iasus, or of Piren" — all three from a single
  Apollodorus passage). Correct behaviour: keep one canonical edge, record the disagreement in
  `variant_claims`.
- **Joint parentage** — one source names *two genuine co-parents*, a mother **and** a father, of
  the same child (Apollodorus 1.1.1-1.1.7: Sky **and** Earth jointly parent Cronus). Both edges are
  true; neither is a "contradiction."

Both appear to the resolver as "a child with ≥2 distinct candidate parents," so it labels both
*contested* and collapses to a single edge via spine priority + alphabetical tie-break. For joint
parentage this **silently drops a real parent** — and because co-parents are usually named by a
single source, the dropped edge is *not* captured in `variant_claims` either. It is fully lost.

This is not a one-off. Replaying the real seedgen pipeline (relation aliases → `_filter_and_dedup` →
`resolve_canonical_edges`) over `relationships_candidates_cleaned.json` measures **472 children**
regaining a dropped co-parent under the discriminator this ADR adopts (487 under the naive count rule
first drafted here) — the entire Titan/Cyclops generation and far beyond.

> **Amendment 2026-07-26 — the original "665" figure was wrong.** It was counted over the *raw*
> candidate rows, before the entity filter that `seedgen` actually applies
> (`relationships_gen._filter_and_dedup` drops any row whose `from_name`/`to_name` is not in the
> confirmed entity set). The post-filter figures above are what would really land in V11.
>
> **Correction 2026-07-26 (second pass) — "442" is superseded by 472.** The 442 recorded earlier the
> same day came from a simulation whose co-mention semantics were never written down. Re-simulated
> under the now-explicit definition in *Decision* below — every unordered pair of unflagged parents
> sharing one `(source_id, passage_ref)`, formed pre-dedup, Io deny-listed — the figure is **472**,
> and that run reproduces the baseline (2,492 canonical edges / 1,145 children with a parent / 0 with
> two / 641 contested children / 1,084 dropped values / 608 same-source) and all ten worked outcomes
> below exactly. Four other readings of the rule were tried and none returns 442 (460 / 465 / 467 /
> 480), so the earlier figure is treated as measured under a variant that no longer matches the
> written rule. **The implementer must re-measure once `canonical_edge.py` is changed** and record the
> figure the real code produces; every count in this ADR is a simulation, not a landed result.
>
> **Landed 2026-07-26 (DEV-090) — re-measured against the real code, not this simulation.** Every
> headline figure above matched exactly: **472 children** regain a co-parent, max 2 parents per
> child holds with no exceptions, and **612** distinct rival parents remain dropped (GAP-001 Root
> cause 3's own figure, also confirmed exactly). The predicted `Salmoneus`/`Enarete` A3 cycle (1→2)
> was found in simulation before the first reseed and fixed in the same landing pass as a genuine
> entity conflation (`Deimachus` names two different people — see DEV-090), not a reversed edge, so
> the live post-reseed A3 count never actually reached 2. One consequence this ADR did not
> anticipate: legitimate branching pushed a real `WITH RECURSIVE` lineage query's row count high
> enough to blow an LLM per-request token limit in `MixedQueryHandler` (a pre-existing gap — only
> the debug-capture view was ever row-capped, not the actual prompt input) — found via a real gold-
> question regression during landing eval and fixed at that layer (see DEV-090), not by constraining
> the branching itself.

The loss is total, not partial: the live graph currently holds **2,492 canonical edges over 1,145
children with a parent, and 0 children with two**. It is why lineage queries (gold Q9, "trace Zeus's
lineage back to Chaos") dead-end at Cronus, and why the SQL-queryable family tree is missing one
parent for a large fraction of entities.

## Decision

Narrow ADR-007 §6 with a **co-parent carve-out**. Genuine co-parent couples keep **both**
`parent_of` edges; only genuine contests still collapse to one. Couples are the **only** case that
keeps multiple `parent_of` edges. `married_to` / `killed_by` resolution is unchanged (single canonical
edge). No schema/DDL change: `relationships` (V4) already permits multiple `parent_of` rows into one
child — single-canonical was enforced only in the resolver.

> **Amended 2026-07-26.** As originally accepted, the discriminator was a bare **co-mention count**
> ("within one `(source_id, passage_ref)`, exactly 2 co-named parents ⇒ couple; 3+ ⇒ alternatives").
> Simulating that rule against the live candidate data showed it does not hold up — it produces
> children with up to **6** parents, injects false edges, introduces **6** `parent_of` cycles, and
> fails on its own Io example. It is replaced by the four-part rule below. See *Alternatives
> considered* for the measured failures.

**Co-mention pair — definition.** Two *distinct* parents of the same child whose candidate rows share
one `(source_id, passage_ref)`. Where a passage co-names three or more parents, **every unordered
pair** among them is a candidate pair: the superseded rule's "3+ ⇒ alternatives" clause does **not**
carry over, because rules 1–4 below now do that discriminating. (This is exactly what rescues
`Hellen` — three co-named parents, one of them flagged, leaving the pair Deucalion + Pyrrha.) Pairs
are formed on the entity-filtered but **pre-dedup** rows; see the implementation constraint below.

The discriminator applied in `resolve_canonical_edges()` for contested `parent_of` groups has four
parts, all four required:

1. **Contested-aware.** Rows carrying the extractor's `is_contested = true` flag are excluded from
   couple candidacy — that flag is the source's *own* signal that it is naming mutually-exclusive
   alternatives. This field already exists on every candidate row and was previously unused by the
   resolver. The flag is evaluated **per row, not per parent**: a parent flagged in one passage can
   still form a couple from an unflagged row elsewhere (Apollodorus flags both `Hera` and `Zeus` for
   Hephaestus in `1.3.1-1.3.5`, yet each is unflagged in other sources).
2. **Winner-anchored.** The canonical winner is still chosen exactly as today, by the unmodified
   `_pick_winner` (first spine source in `SPINE_PRIORITY` order that backs any value, alphabetically
   among the values that source backs; if the group cites no spine source at all, the value with the
   most distinct corroborating sources, tie-broken alphabetically). A couple is kept **only if the
   co-mention pair contains that winner**. This caps any child at 2 parents and prevents an unrelated
   pair from injecting a parent the canonical resolution never selected.
3. **Corroboration-ranked.** Where several candidate pairs contain the winner, keep the pair attested
   by the **most distinct sources**, then by spine rank, then alphabetically.
4. **Deny-listed.** A small hand-maintained not-a-couple list (child + parent pair + written reason)
   suppresses known false pairs that survive rules 1–3. Seeded with **Io**. This follows the project's
   existing review-gated data convention (ADR-004) rather than encoding one-off exceptions in code.

**Corollary — rules 1 × 2 interact.** `_pick_winner` is deliberately unchanged and therefore does
**not** consult `is_contested`, so the canonical winner can be a parent named only in flagged rows.
When that happens rule 1 strips the winner out of every candidate pair and rule 2 then makes a couple
structurally impossible, collapsing the child to the lone winner — *even where other, unflagged
parents were co-named*. This is intended: a source that flags its own parentage claim as one of
several alternatives should not also anchor a couple. It is what produces the `Helen` row in the
table below (winner `Leda` is flagged in her only passage), not an absence of unflagged candidates.

Everything else collapses as before: **different sources naming different single parents** is a
cross-source contest → one canonical edge, disagreement in `variant_claims` (ADR-007 §6 unchanged);
and **any group with no qualifying winner-anchored pair** → one canonical edge. Note that a bare count
of co-named parents no longer decides anything: three unflagged parents co-named in one passage *do*
yield candidate pairs, and rules 2–4 pick among them or reject them all.

**Implementation constraint (measured).** Pairs must be formed on the entity-filtered but
**pre-dedup** rows. `relationships_gen._filter_and_dedup` keys on
`(from_name, relation, to_name, source_id)` and keeps only the **first** row per key, discarding every
later passage of that source along with its `passage_ref`. So a co-mention survives dedup only if the
passage that names both parents happens to be the first one retained for *each* of them; where it is
not, the pair vanishes — measured for **34 children** (Agamemnon, Ajax, Antiope, Auge, …). Widening
the dedup key instead is **not** the fix — that would change V11's row count and the A2 drop
accounting for unrelated reasons.

Worked outcomes (all verified by simulation against the live candidate data):

| Child | Candidate parents | Result |
|-------|-------------------|--------|
| Cronus | four rows, none flagged: Sky **&** Earth (Apollodorus `1.1.1-1.1.7`) **and** Earth **& Heaven** (Theogony `104-146`) | winner **Earth**; two pairs contain it, tied at 1 source each, so spine rank decides → **Sky + Earth kept**. The losing pair is the *same couple under the `Heaven` duplicate* — a reminder that the `Sky`/`Heaven`/`Uranus` split (see *Scope*) reaches into this ADR's own headline case, and that merging them would make this pair 2-source-attested rather than a tie-break. |
| Aphrodite | Zeus **&** Dione (Apollodorus, 1 passage), neither flagged | couple → **both kept**; Hesiod's foam-birth stays a cross-source conflict in `variant_claims` |
| Hellen | Deucalion, Pyrrha (unflagged) + Zeus (`is_contested=true`), one passage — 3 | rule 1 sets the rival aside → couple **Deucalion + Pyrrha** kept. *The bare count rule collapsed this to Deucalion alone, still dropping a true parent.* |
| Endymion | Aethlius, Calyce (unflagged) + Zeus (flagged) — 3 | couple **Aethlius + Calyce** kept (same shape as Hellen) |
| Heracles | four candidates — Alcmena, Zeus, Amphictyon and **Antiochus** (Apollodorus `2.8.3-2.8.4`, never co-named, so it forms no pair) | winner **Alcmena** (Apollodorus backs Alcmena/Antiochus/Zeus; alphabetical). Alcmena + Zeus are co-named in **6** distinct sources — Apollodorus `2.4.7-2.4.8`, Theogony, Hymns, Iliad, Odyssey, Ovid — against Alcmena + Amphictyon in **1** (Odyssey `11.225-11.270`), so rule 3 → **Alcmena + Zeus**. Note that Odyssey passage co-names three unflagged parents, and both of its 2-subsets compete normally. |
| Helen | Nemesis, Leda, Zeus all flagged in Apollodorus `3.10.4-3.10.7`; **plus** unflagged `Tyndareus` (`3.10.8-3.11.1`, `E.2.15-E.3.5`) and unflagged Zeus (`E.1.17-E.1.23`, Il. ×2, Od. ×2) | winner is **Leda**, whose only rows are flagged, so the rules 1×2 corollary bars any pair → **collapse to one** (Leda); rival versions belong in `variant_claims`. *Unflagged candidates do exist here — it is the flagged winner, not their absence, that prevents a couple.* |
| Hephaestus | Apollodorus `1.3.1-1.3.5` flags **both** Hera and Zeus; Hera unflagged in Hesiod/Hymns/Iliad/Ovid, Zeus unflagged in Theogony `558-612` — but never co-named unflagged in one passage | no qualifying pair → **Hera only** (spine + alphabetical), which happens to match the parthenogenesis version Apollodorus asserts |
| Io | Iasus, Inachus, Piren (Apollodorus, 1 passage) — 3 in the raw candidates | **collapse to one** via the deny-list. **Not** via the count: `Piren` is absent from the confirmed entity set, so the entity filter reduces Io to *exactly 2* before the resolver ever sees it, and the count rule would have mis-coupled it. |
| Achilles | Peleus + Thetis | couple → **both kept** |
| Zeus | Cronus + Rhea (spine); Pallas/Styx and Athena/Cronus from mis-attributed passages | rule 2 anchors on the canonical winner Cronus → **Cronus + Rhea**; the spurious pairs cannot enter |

## Alternatives considered

- **A bare co-mention count (exactly 2 ⇒ couple, 3+ ⇒ alternatives).** This was the rule as
  originally accepted; **rejected on measurement 2026-07-26**. Simulated against the live candidate
  data it: gives children up to **6** parents (`antiphus`: Hecuba, Heracles, Laothoe, Myrmidon,
  Pisidice, Priam — every 2-pair across every passage kept); injects false parents the canonical
  resolution never chose (`Athena parent_of Zeus` from Iliad 5.864, an extraction error); introduces
  **6 new `parent_of` cycles**; still drops a true parent on couple-plus-rival groups (Hellen,
  Endymion); and mis-couples **Io**, its own worked example, because the entity filter removes `Piren`
  before the count is taken. Counting is retained only as one input to the winner-anchored rule.
- **`married_to` link between the two parents ⇒ couple.** Rejected: semantically wrong. Most Greek
  co-parents were never married (Zeus + countless mortals/nymphs) — marriage does not track
  co-parenthood.
- **Sexed relation labels (`father_of` / `mother_of`) as the role signal.** Rejected: not in the
  data. Only 7 `father_of` + 2 `mother_of` rows exist against ~4,475 generic `parent_of`. (The
  adopted rule's role-like signal is the extractor's `is_contested` flag, which *is* densely present:
  177 flagged `parent_of` rows, and it fires precisely where a source enumerates rival parents.)
- **A new `entities.sex` column; couple = opposite-sex parents.** Rejected for now: the most
  semantically pure rule, but requires curating gender for many entities up front and fails wherever
  a parent's sex is uncurated/NULL. The adopted four-part rule achieves the right outcome on the
  observed data with no new curation. (Still a possible future refinement for the residue the
  deny-list currently covers.)
- **"Same source + same passage" co-mention alone ⇒ couple.** Rejected: fails on Io, where
  Apollodorus co-names three *rival* fathers in one passage. Co-mention is necessary but nowhere near
  sufficient on its own.
- **Store every asserted parent as an edge (couples AND contests).** Rejected: this is exactly the
  alternative ADR-007 §6 rejected — it branches lineage on disagreements and makes DATA queries
  return rival parents. The rejection stands for *contests*; it is lifted only for genuine
  *couples*, where branching to two parents is correct genealogy.

## Consequences

**Positive**
- The real family tree is restored for **472 children** that regain a dropped co-parent (measured
  post-entity-filter); lineage traversals reach the co-parent generation instead of dead-ending.
- No contested claim is flattened by this change: contests keep the ADR-007 §6 split (canonical edge
  + `variant_claims`), and co-parents — previously lost entirely — are now kept.
- Every child ends with **at most 2** `parent_of` parents (winner-anchoring guarantees it), so the
  graph stays a clean genealogy rather than a bag of asserted parents.
- No schema/DDL change; no runtime code change.

**Negative / costs**
- `WITH RECURSIVE` lineage may now legitimately branch to two parents. This is correct behaviour and
  is already bounded by the query few-shot's `visited` id-array + `depth < 20` cap
  (`TextToSqlAgent.kt`, DEV-069); DATA answers listing parents may return two rows. Because branching
  is now genuinely binary in places, **Q9's runtime must be re-checked against the 3 s
  `statement_timeout`** during the landing eval, not assumed safe.
- **The A3 `cycle_check` DAG invariant is *not* unaffected — the original claim here was wrong.**
  Measured: the naive count rule adds **6** cycles; the adopted rule adds **1** — the restored, and
  mythologically *correct*, `Enarete parent_of Salmoneus` edge closes a chain through a pre-existing
  reversed edge (`Salmoneus → Tyro → Neleus → Deimachus → Enarete`). Restoring co-parents *exposes*
  latent direction errors rather than causing them. A3 must therefore re-run as part of landing, with
  budget for a reversed-edge fix pass at the candidate-JSON layer; a clean-or-explicitly-waived A3 is
  the gate, not an assumption.

  > **Which layer these cycle counts are measured at** — they are **post-resolver** `parent_of`
  > cycles, i.e. the graph V11 would actually seed from today's candidates. At that layer the
  > baseline is exactly **1** (`Eurymachus ↔ Polybus`, unrelated to this change), so the adopted rule
  > takes it 1 → 2. Do not compare these against the other two A3 numbers on record, which count
  > different things: **62** `parent_of` cycles exist at the *pre-collapse candidate* layer (the
  > collapse is what removes them), DEV-087 reports **96** for `python -m audit --candidates` over
  > the candidate layer, and the P3 exit criterion's "**0** live cycles" refers to the *currently
  > seeded* DB, which predates the J1/J2/J3g candidate edits and so cannot be compared either.
- A residue of false couples survives rules 1–3 wherever the extractor did not flag rival parents and
  the entity filter happens to reduce them to two (**Io** is the known instance). The deny-list is the
  mitigation; the generated review artifact (~472 pairs, one line each) is what makes the residue
  findable. This errs toward *keeping* data — the project's stated preference — and is
  review-catchable.

**Scope / follow-ups (not addressed here)**
- **This ADR restores co-parents; it does not make the *contested* half lossless.** Measured: the
  collapse discards **1,084 distinct parent values** today. This ADR recovers **472** of them; **612**
  genuine rival parents stay collapsed, and are recorded **nowhere** — `variant_claims` holds
  parentage rows for exactly two subjects (Aphrodite, Io, the hand-curated ADR-004 floor). **Two
  different blockers** produce that single symptom, and they split the residue unevenly:
  - **145 of the 612** sit in groups citing exactly one source, where
    `conflict_detector.detect_conflicts`'s **≥2-distinct-source_ids** gate never fires. These are the
    only ones a same-source qualifying condition reaches.
  - **467 of the 612** sit in groups citing two or more sources, so the gate **already passes today**
    and candidates are already emitted for them. Nothing reaches V12 because no one has promoted them
    through the ADR-004 review gate — a throughput problem, not a detection one, and untouched by any
    detector change.

  (Child-level, the same split is 338 single-source vs 303 multi-source of the 641 contested
  children. The often-quoted "608 of 641 are contested within a single source" counts children where
  *some one source* names ≥2 parents — a different predicate from the detector's, which counts
  distinct sources across the whole `(subject, claim_type)` group; 270 of those 608 clear the gate.)

  Closing this half therefore needs (a) a generated record of every dropped parent — which serves
  both buckets — and (b) a same-source qualifying condition in the detector, which addresses the 145.
  The ~467 already-detected rivals need a review-throughput answer, not code. Tracked in
  `docs/DATA-GAPS.md` GAP-001 Root cause 3 and folded into J4a's landing scope.
- Two other blockers to a full Q9 pass remain open (see `docs/DATA-GAPS.md` GAP-001): the
  **`Chaos → Earth` cosmogonic (non-parent) relation** (J4b), and the **`Sky` / `Heaven` / `Uranus`
  duplicate-entity split** — all three exist as separate confirmed entities, `Heaven` even carries
  `Earth` as its own parent, and the restored edge attaches to `Sky`; surfacing the literal "Ouranos"
  keyword needs that duplicate resolved and an `entity_aliases` row.
- Implementation lands through the Stage P3 Track I fix-loop gate (seedgen → reseed → audit → 3-run
  eval → compare), recorded as **DEV-088**. Design reference:
  `docs/TODO-phase2-stage-p3.md` Track J4a and the approved plan for this change.

## Traceability

- Narrows: **ADR-007 §6** (single canonical edge; the contradiction in `variant_claims`).
- Gap record / waiver: **`docs/DATA-GAPS.md` GAP-001** (root cause 1 = this ADR; root cause 3 = the
  unrecorded dropped rivals).
- Backlog item: **`docs/TODO-phase2-stage-p3.md` Track J4a**.
- Deviation: **`docs/DEVIATIONS.md` DEV-088** — records this 2026-07-26 amendment and the added
  lossless-drop scope; implementation still pending.
- Code touch-points when implemented: `ingestion/seedgen/canonical_edge.py`
  (`resolve_canonical_edges`, `_pick_winner`, `RelRow` gains `is_contested`);
  `ingestion/seedgen/relationships_gen.py` (pre-dedup co-mention plumbing);
  `ingestion/extraction/conflict_detector.py` (same-source parentage detection);
  tests `ingestion/tests/test_canonical_edge.py` — note its existing
  `test_gyes_shape_same_source_multi_value_ties_break_alphabetically` asserts the *old* single-winner
  behaviour for exactly the Sky/Earth case this ADR fixes, so it must be rewritten, and
  `canonical_edge.py`'s module docstring cites Gyes as the motivating contested example when Gyes is
  in fact a couple.
