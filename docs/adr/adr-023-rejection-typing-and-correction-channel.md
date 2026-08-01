# ADR-023: Typed Rejections and a Reviewer-Authored Correction Channel

| Field        | Value       |
|--------------|-------------|
| **Date**     | 2026-08-01  |
| **Status**   | Proposed    |
| **Amends**   | ADR-004 (extends the review gate from *approving what the machine found* to *recording why it was wrong and what is true instead*); see ADR-004 **Amendment 2** for the provenance conditions on a reviewer-authored row |
| **Amended by** | —         |
| **Supersedes** | —         |

---

## Context

Stage P5-0's review engine is **verdict-capable but not write-capable**. A reviewer reading a cited
segment can promote a row (`trust_tier=1`) or reject it (`trust_tier=2`), and nothing else. That
asymmetry costs the project data in three separate ways, all measured against the live candidate pool
on 2026-08-01 (`variant_claims_candidates.json`, 9,096 rows, 639 at `trust_tier=2`).

**1. A rejection records no reason.** It is `trust_tier=2` on the row plus a bare 5-tuple in
`promotion_log.json`'s `rejectedKeys`; only 12 of 29 batch entries carry even a batch-level
`rationale`. So "the direction is reversed" — a *correctable* error implying a true fact stated in
that very passage — is indistinguishable from "the passage does not say this" (nothing to recover)
and from "right fact, wrong figure" (an entity problem, ADR-022's). Nothing downstream can act on
639 rejections because nothing downstream can tell them apart.

**2. The true claim the reviewer just read is discarded.** Of the 581 rejected `parentage` rows, 560
yield a derivable inverse key (`parse_parent` names a confirmed entity); the remaining **21** do not
and are uncheckable by this join rather than negative. Of those 560:

| | rows |
|---|---|
| corrected (inverse-direction) row attested **at the same passage** | **34** |
| corrected row present **only at a different passage** — the attesting `passage_ref` is lost | 243 |
| corrected row **absent from the entire 9,096-row pool** | **283 (51% of the 560)** |
| …of those 283, corrections **immediately seedable** (both names already in `entities`) | **101**, over 62 passages |
| …blocked on a missing entity (Track D's work) | 182 |

The four figures partition the 581 (`34 + 243 + 283 + 21`); B9 is what pins them, and a divergence
means this table is stale, not the script. Half of every direction-error rejection therefore destroys
a fact that was on screen at the moment of rejection. In a product whose differentiator is
passage-level attribution, the middle row matters too: a claim recovered at some *other* passage
cites the wrong location.

**3. The rejection never reaches the table with no human gate.** `parentage` claims are projections
of `parent_of` edges (`conflict_detector._RELATION_TO_CLAIM`: `parent_of → (to_name, "child of
{from}")`), so a claim and an edge are two views of one extraction. `relationships` is seeded
mechanically into V11 with **no review gate at all** (CLAUDE.md, Data Model). **162** of the 581
rejected claims have their exact directional counterpart still sitting in
`relationships_candidates_cleaned.json`. Rejecting the claim marks the disagreement decided while the
edge may still be live. This is GAP-011's shape on a new seam, and is filed as **GAP-012**.

**Why this cannot be fixed by extracting again.** The reversal is a systematic class, not noise —
that is precisely what makes A14 (`audit/claim_direction.py`) able to find it by rule, requiring the
reversed reading be attested in that source and the correct reading never be. The same model on the
same segment reproduces it. Re-extraction also re-keys every reviewed decision, an exposure Stage P6
measured at 1,092 decisions and rising with every batch.

**The economics, which is what makes the fix cheap — and what makes it urgent going forward rather
than retroactively.** The scarce resource in Track C is the *read*: 2.54M characters ≈ 424k words
across the queued passages. The reviewer already has the segment open at the instant of rejection.
Capturing the reason and the correction there costs seconds; recovering them later costs a re-read.

The standing 639 are **mostly recoverable for free**, and this ADR does not claim otherwise: **252 of
the 268 passages holding them still carry tier-3 rows**, so the queue reaches them on its own and
F5's mechanism types the **390** rejections sitting there at no extra read. Only **249 rows over 16
passages** are stranded today.

What is *not* recoverable is everything a reading batch writes from here on. A batch **finishes** the
passages it opens: of the 23 passages C1 has adjudicated, only **6** still hold a tier-3 row, so the
queue will not return to the other 17. Every rejection a batch records from now on therefore lands at
a passage that leaves the queue in the same act — permanent residue at the moment of writing — and
every correction on screen is discarded with it. That is the asymmetry the interrupt is for: not the
backlog behind us, which the queue largely absorbs, but the residue each further batch creates
irreversibly.

Construction: `trust_tier`/`passage_ref` join over `variant_claims_candidates.json`, and the
`p5-track-c1-*` entries of `promotion_log.json` for the adjudicated-passage set (B9).

Construction of every figure above: `ingestion/extraction/rejection_audit.py` (Track B9), joining
`variant_claims_candidates.json` to `relationships_candidates_cleaned.json`,
`entities_candidates_confirmed_v1.json` and `promotion_log.json`; inverse key =
`(parent, "parentage", "child of " + subject, source_id)`.

## Decision

### 1. A rejection carries a reason, drawn from a closed vocabulary

Eight values. Seven are reasons; the eighth is transitional and has a stated exit.

| code | meaning | what it obliges downstream |
|---|---|---|
| `reversed_direction` | the claim says A is child of B; the passage attests B is child of A | **a correction is owed**; check the mirror edge (GAP-012) |
| `wrong_subject_namesake` | the fact is right, the figure is wrong (GAP-009/GAP-010 shape) | `Z_HOLD` / `namesake_registry.json` work; no correction |
| `not_in_passage` | the cited segment does not state this at all (buckets D/E) | nothing owed; check the mirror edge |
| `misread_idiom` | a vocative, epithet or Homeric formula parsed as a claim (GAP-007 shape) | deny-list candidate |
| `malformed_subject` | subject is `<UNKNOWN>`, `<none>` or empty | mechanical; nothing owed |
| `duplicate_of_promoted` | already represented by another promoted row | nothing owed |
| `true_but_unattributable` | the claim is true, but *this source* does not say it | nothing owed |
| `unclassified_legacy` | a rejection recorded before this ADR | **transitional** — exits via Track F5's register |

The vocabulary is closed on purpose. An open free-text reason field would reproduce the current
state, where the reasoning exists somewhere (notebook markdown, a DEV entry) but nothing can query
it. Each code was chosen to map onto both something the reviewer can *see* in the segment and
something a later pass must *do*; a code that obliges nothing and explains nothing does not belong
in it. A rejection that fits none of the seven is a signal the vocabulary is wrong — extend it here,
in this ADR, rather than reaching for free text.

### 2. The reason is stored on the candidate row, and the merge is generalised to carry it

`run_extraction._write_claims_preserving_review` currently carries exactly one field across a
re-extraction — `trust_tier` — and **destroys everything else** on rows it regenerates. Any reason
field added naively is therefore erased by the next extraction run. The merge is generalised from a
single hardcoded field to a whitelist:

```python
_REVIEW_OWNED_FIELDS = ("trust_tier", "rejection_reason")
```

This is the generalisation the function's own docstring already states as its principle: *"the
extraction owns which claims exist, review owns their `trust_tier`."* The principle was always about
review-owned fields; only the implementation was single-field.

The reason is **also** written into the batch's `promotion_log.json` entry: `rejectedKeys` entries
become `{"key": [...], "reason": "..."}` objects instead of bare 5-tuples, so a batch entry remains a
complete account of that batch without replaying the candidate file. The 29 existing entries stay
valid — readers accept both shapes, and a legacy bare tuple reads as `unclassified_legacy`.

### 3. Corrections live in a separate overlay file, never in the candidate file

New artifact: `ingestion/extraction/output/claim_corrections.json`. Schema is the six candidate
fields plus `origin: "review-correction"`, `corrects` (the rejected 5-tuple it answers),
`evidence_span` (verbatim text from the open segment), `batchLabel`, `date`.

**Why not simply add the corrected row to `variant_claims_candidates.json`.** That file is
merge-on-write, and the merge deliberately does *not* resurrect a reviewed row the extraction no
longer produces — keeping it "would reinstate a claim no source supports," which is correct for
machine output. A reviewer-authored row is by definition never produced by extraction, so it would
be dropped by the very next `run_extraction` run. That is the DEV-101 failure (one re-extraction,
71 hand-reviewed rows destroyed) reintroduced through a different door.

The overlay is never written by extraction, so it survives by construction rather than by
discipline. It is also the correct conceptual boundary, and states it in one line: **extraction owns
what the model found; the overlay owns what the human found.**

Consumers:
- `seedgen/variant_claims_gen._reviewed_rows` unions the overlay in, then applies the **same**
  entity-presence and 4-tuple dedup filters. An overlay row is not exempt from the reachable ceiling.
- `audit/coverage.py::variant_claims_ceilings` counts overlay rows in **both** the numerator and the
  ceiling, and its printed derivation chain gains an `+N overlay` term. Without this, a seeded row
  absent from the candidate pool makes A16 — the instrument every batch closes on — misreport.

### 4. Machine proposes, human confirms

For a `reversed_direction` rejection, `review_passage` pre-fills the inverted row and displays A14's
matched span as its evidence. The reviewer confirms it explicitly, exactly as a bucket-A row is
confirmed against its matched span. No code path writes a correction without that confirmation.

This is deliberately not auto-insertion, for two independent reasons. It would be unreviewed
automated insertion into `variant_claims`, which ADR-004 and the CLAUDE.md guardrail forbid. And the
mechanical inverse is a *hypothesis*, not the truth: `Dione | parentage | child of Nereus` inverts to
`Nereus | child of Dione`, a claim the passage may support in neither direction. The machine is good
at finding which rows are wrong and bad at knowing which row is right; the split follows that.

### 5. A correction counts as coverage

The seeding rule's "rejection is not coverage" clause is correct and stays. It is joined by a
correction-yield clause (`docs/TODO2.md`): a confirmed correction is a seeded row and counts exactly
like a promotion, and every batch reports `corrections authored ÷ reversed_direction rejections`.
Without it, a reversal-heavy batch reads as pure loss — the incentive that produced 286 rejections
against 4 promotions on 2026-07-29/30, and which a batch would rationally resolve by adjudicating
*around* reversals instead of correcting them.

## Consequences

### Accepted costs
- A further artifact in `extraction/output/`, and a second input to `seedgen` and A16. Both are
  narrow, but "the candidate file is the only source of promoted rows" stops being true, and any
  future tool reading promotions must read two files.
- Rejection becomes marginally more expensive: a code is now required, and the notebook raises if one
  is missing (the same posture as the existing approved∩rejected contradiction guard).
- **591** existing rejections start at `unclassified_legacy` (639 less the 48 B13 types mechanically),
  over at most 268 passages. The queue-reachability split is measured over the full 639 — **390 rows
  at 252 passages the queue reopens, 249 at 16 passages it does not** — so B13's 48 come off one side
  or the other and F5's true cost is **at most 249 rows**, less again whatever C0's 62-passage pass
  absorbs. B13 records the post-typing split rather than inheriting this one. The 390 are typed for
  free when the queue returns; only the stranded side needs dedicated reads, and that residue is
  scheduled, not deferred — Track F5.
- The correction channel widens what a reviewer can write, and therefore what a reviewer can get
  wrong. ADR-004 Amendment 2 is the mitigation and is not optional.

### Benefits gained
- The 101 immediately-seedable corrections become reachable from 62 segment reads — the highest
  row-per-read ratio available anywhere in the stage (C1 spends 100 reads for 2,229 adjudications,
  most of which are not promotions).
- Rejections become queryable: "how many reversals are still uncorrected" is a number, not a reading
  exercise across 29 log entries.
- GAP-012 becomes decidable. The 162 mirror edges cannot be classified today because the rejection
  that implicates them carries no reason; typing them is what separates *edge is wrong and live*
  from *edge belongs to a different figure*.
- Coverage stops being a one-way ratchet against the reviewer: a batch that finds mostly errors can
  now show a positive result honestly, instead of showing a rejection count.

### Detector budget (`docs/TODO2.md`, the seeding rule)
**Zero spent.** `rejection_audit.py` and `claim_edge_reconcile.py` live in `ingestion/extraction/`,
outside the `audit` package, so `discover_checks()` (`audit/__main__.py`) never sees them — the same
location invariant Stage P6 relied on for its G-track tooling. The A16 change is an edit to an
instrument that cannot emit a finding, which the budget exempts explicitly.

## Alternatives Considered

**Re-extract with an improved prompt.** Rejected. It does not address the class: A14's rule is
satisfied only when the source attests the reversed reading and never the correct one, so the model
is misreading text that is genuinely ambiguous in isolation, and a prompt change moves which rows are
wrong rather than removing wrongness. It also re-keys every reviewed decision (1,092 today, growing
per batch), and it is the exact iteration cost this decision exists to avoid.

**Auto-insert the mechanical inverse for A14-class rows.** Rejected. Unreviewed automated insertion
into `variant_claims` is forbidden by ADR-004 and by the CLAUDE.md guardrail, and adopting it would
require repealing that rule rather than amending it. Independently unsafe, per the `Dione` case
above.

**Edit the rejected row in place instead of writing a correction.** Rejected. ADR-004 Amendment 1
point 5 makes a rejection a recorded verdict of the same weight as a promotion, marked
`[ALREADY REJECTED]` for every later reviewer. Overwriting it destroys that verdict and silently
re-opens a decided row.

**Free-text rejection notes instead of a closed vocabulary.** Rejected. It is what the 12 batch-level
`rationale` strings already are, and their existence is why the current state is undiagnosable: prose
records reasoning without making it actionable. A closed set is queryable and forces the vocabulary
to be revised deliberately.

**A dedicated correction review UI.** Rejected for the same reason ADR-004 rejected a review web app:
`review_passage` already prints the segment and the rows, and a pre-filled proposal plus a
confirmation keystroke is the whole interaction.

---

See `docs/DEVIATIONS.md` #DEV-150, `docs/DATA-GAPS.md` GAP-012, and Stage P5 Tracks B9–B13 / C0 / F5
in `docs/TODO-phase2-stage-p5.md`.
