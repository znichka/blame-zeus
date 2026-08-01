# ADR-004: Tiered LLM Extraction (with Human Review Gate) for Seed Data, Replacing Full Hand-Curation

| Field        | Value       |
|--------------|-------------|
| **Date**     | 2026-07-08  |
| **Status**   | Accepted    |
| **Amended by** | Amendment 1 (DEV-135 — pre-verification signal may order and annotate, never promote); Amendment 2 (DEV-150 — conditions on a reviewer-*authored* row); **ADR-022** (extends the review gate from *what a claim says* to *who its subject is*); **ADR-023** (extends it from *approving what the machine found* to *recording why it was wrong and what is true instead*) |

---

## Context

The original plan (`CONCEPT.md §8`, `TECH_GUARDRAILS.md` "PoC Boundaries")
mandated that `entities`, `relationships`, and `variant_claims` be **entirely
hand-curated** (no automated extraction) on the reasoning that this data
directly backs the product's core differentiator (trustworthy, attributed
conflict-awareness), and a hallucinated relationship or misattributed claim is
worse than no answer at all.

That reasoning for `variant_claims` specifically still holds. But hand-typing
~60–100 entities, their relationships, and cross-source conflicts across six
ingested primary sources is slow, and much of this data is already sitting in
the corpus in extractable form. Notably, the mythographers frequently flag
their own disagreements inline. Apollodorus on Io: *"the annalist Castor and
many of the tragedians allege that Io was a daughter of Inachus; and Hesiod and
Acusilaus say that she was a daughter of Piren."* One passage, two attributed
parentage claims. This is a structuring task, not an invention task, and LLMs
are well suited to it, provided the output is checked before it's trusted.

## Decision

Adopt a **tiered, semi-automated extraction pipeline** that runs offline
during corpus ingestion, gated by risk:

| Data | Source of truth | Review gate |
|---|---|---|
| `entities`, `relationships` (V10, V11) | LLM-extracted from ingested corpus text | Developer spot-check before merging candidates into the Flyway migration (low ambiguity, mechanical facts) |
| `variant_claims` (V12) | LLM-extracted (explicit in-text disagreement) **+** a supplementary automated cross-source conflict scan | **Every candidate staged at `trust_tier=3`; requires explicit developer promotion to `trust_tier=1`** before it enters the real seed data |
| `sources` (V9), `myths`/`myth_participants` (V13), `entity_aliases` (V14) | Unchanged, hand-curated | N/A, not corpus-derived (bibliographic metadata, editorial groupings, cross-cultural name maps) |

The three "minimum coverage" `variant_claims` rows already specified in
`IMPLEMENTATION_PLAN.md §3` (Aphrodite parentage, Io parentage, Achilles death)
remain a **hard requirement** regardless of what the pipeline surfaces: if
extraction misses one, it is hand-added. Extraction is additive to the
existing quality bar, not a replacement for it.

Extraction is **offline corpus-prep tooling** (`ingestion/extraction/`), not a
runtime capability: it does not touch `LangChain4jConfig.kt`, does not add a
new `@AiService`, and never runs at query time. This keeps it inside the
Python ingestion job's existing (now slightly widened) authorization to call
an LLM SDK directly.

### Pipeline design

```
ingestion/
├── extraction/
│   ├── schema.py             # Pydantic models mirroring V10–V12 exactly:
│   │                         #   ExtractedEntity, ExtractedRelationship (+ is_contested flag),
│   │                         #   ExtractedVariantClaim
│   ├── known_aliases.json    # Roman/cross-cultural equivalents (Zeus/Jupiter, Heracles/Hercules...)
│   │                         # doubles as reference input for hand-curated V14
│   ├── entity_resolver.py    # in-memory dedup: exact name match → known_aliases →
│   │                         # rapidfuzz fuzzy match against the running candidate list
│   ├── claim_extractor.py    # instructor + OpenAI chat completions; per-source extraction
│   │                         # hints (e.g. Apollodorus: "flag 'others say' as is_contested");
│   │                         # tenacity retry, matching the existing embed_batch pattern
│   ├── conflict_detector.py  # supplementary SQL/in-memory pass: same subject + claim_type,
│   │                         # different source_id → auto-flag additional variant_claims
│   │                         # candidates beyond what the LLM explicitly noticed in-text
│   └── run_extraction.py     # entry point → writes candidate JSON to extraction/output/
├── extraction/output/
│   ├── entities_candidates.json
│   ├── relationships_candidates.json
│   └── variant_claims_candidates.json   # every row trust_tier=3 until reviewed
└── notebooks/
    ├── 01_test_extraction.ipynb  # tune the prompt on Apollodorus (the spine source) first:
    │                             # if extraction quality is good there, the rest follows
    └── 02_verify_conflicts.ipynb # developer review/approval pass for variant_claims candidates
```

Extraction runs on **passage-ref-aligned segments**, not the fixed 1500-char
RAG chunks. It reuses the same `passage_ref_extractor` scan already built for
the RAG chunker (`IMPLEMENTATION_PLAN.md §4`), but groups whole sections
between consecutive ref boundaries so a full genealogical statement isn't
split mid-claim. This is a second, coarser segmentation of the same cleaned
text, not a second copy of the corpus.

**New ingestion-only dependencies:** `instructor` (Pydantic-validated
structured extraction with automatic retry-on-invalid-schema, on top of the
same `openai` client instance, not a separate LLM framework) and `rapidfuzz`
(local fuzzy string matching for corpus-time entity dedup). Both are
Python/ingestion-scoped; core-api's LangChain4j/`@AiService` pattern is
untouched.

**Stage order changes:** corpus ingestion (formerly Stages 3–4) must now
happen *before* seed-data generation (formerly Stage 2), since extraction
needs real ingested, cleaned corpus text to run against. Stage numbers are
reassigned so the number reflects execution order; Stage 5 onward
(SQL/RAG/Conflict/Mixed pipelines, evaluation) are unaffected.

## Rationale

1. **Apollodorus and other handbooks already do the conflict-detection work.**
   The Io example shows the source text itself names both variants and their
   proponents in one place: extracting this mechanically is high-recall and
   low-risk *when the output is checked*, which is exactly what the review
   gate provides.
2. **Risk-tiering matches consequence to review cost.** Entities and basic
   relationships are low-ambiguity ("X is a titan," "X is a child of Y"), so
   spot-checking a generated list is proportionate. `variant_claims` is the
   data the product's trust depends on: a wrong or hallucinated conflict
   actively damages the differentiator, so it gets the expensive review step.
3. **This reuses existing infrastructure rather than bolting on something
   foreign.** Same cleaned text (`text_cleaner.py`), same per-source
   passage-ref extractors, same `sources`/`trust_tier` schema.
   `TECH_GUARDRAILS.md` already reserved `trust_tier=3` for "provisional or
   auto-extracted rows" before this decision existed, which anticipated
   exactly this workflow.
4. **A notebook is a sufficient review UI for a PoC.** Building a dedicated
   review web app would be over-engineering; `ingestion/notebooks/` gives a
   fast, good-enough interactive check before promoting candidates.

## Consequences

### Accepted costs
- Two new Python dependencies (`instructor`, `rapidfuzz`), ingestion-only.
- More ingestion surface area: a new `extraction/` subpackage alongside the
  existing `loader/`, `chunker/`, `pipeline/`.
- Extraction quality depends on prompt tuning: budget time to tune against
  Apollodorus first (the spine source) before running the full corpus.
- Stage renumbering in `TODO.md`/`IMPLEMENTATION_PLAN.md §9` (ingestion moves
  before seed data); Stage 5+ content and numbering is unaffected.
- The review gate is still manual labor for `variant_claims`: this decision
  reduces hand-*typing*, not hand-*judgment*, for the highest-stakes table.

### Benefits gained
- Removes the bulk of hand-typing for ~60–100 entities and their
  relationships across six sources.
- Increases `variant_claims` recall beyond what one developer would think to
  go looking for, via the supplementary cross-source conflict scan.
- Preserves the trust guarantee: nothing reaches `trust_tier=1` without
  explicit human approval.
- Re-running extraction after a corpus change is cheap: it regenerates
  candidate files, it doesn't mutate the database directly.

## Alternatives Considered

**Fully automatic, no review gate.** Rejected: this is the specific failure
mode (false certainty / hallucination) the product exists to prevent, and
`variant_claims` is exactly the wrong place to introduce it.

**Status quo (fully manual hand-curation).** Rejected as too slow for the
required breadth (~60–100 entities, several relationship types, multiple
cross-source conflicts) now that the corpus text needed to extract from is
available post-ingestion.

**Adopt the fuller extraction schema from the reference implementation
(`numerical_claim`, `place`, `creature`, `attribute`, `participant`, `event`,
a generic `conflict` table).** Considered, since a reference Python ingestion
plan proposed exactly this shape. Rejected for Phase 1: it doesn't match the
already-built `V1`–`V8` schema (`entities`/`relationships`/`variant_claims`,
not `entity`/`claim`/`conflict`), and it reintroduces the breadth this project
deliberately scoped away from (`CONCEPT.md §7`: "depth beats breadth"). Note
for future iterations: `docs/adr/adr-001-langchain4j-vs-spring-ai.md` and
`adr-002-vector-db.md` describe an earlier, more elaborate architecture
(hybrid dense+sparse retrieval, a generic `conflict` table, `claim_ids` array
metadata) that matches this reference schema closely. Those ADRs predate the
Phase 1 scope-down in `CONCEPT.md`/`IMPLEMENTATION_PLAN.md` and describe a
design that was not carried forward. If Phase 2 revisits broader structured
extraction (numeric claims, places, events), that richer schema is a
reasonable starting point.

**A dedicated review web app for candidate approval.** Rejected as
over-engineering for a PoC; a JSON candidate file plus a Jupyter notebook is
sufficient and much faster to build.

---

## Amendment 1 (2026-07-31) — What "explicit per-row developer review" means operationally (DEV-135)

Stage P5's Track B (`docs/TODO-phase2-stage-p5.md`) replaces subject-prominence
tranche selection with passage-batched review: `review_passage(source_id,
passage_ref)` prints one cited segment and every tier-3 row cited to it, and an
approval or rejection *action* can cover many of those rows at once. This ADR
already calls the notebook "a sufficient review UI for a PoC" (Rationale #4) and
rejected a review web app as over-engineering — this amendment keeps that, and
narrows only the guarantee that was never actually "one row at a time": the
per-row **evidence**, not the per-row **click**.

1. **Every promoted row is displayed with its `claim_value` and evidence** — the
   verbatim span from its own cited passage that pre-verification matched (B3
   bucket A), or the full segment text when nothing matched. A row is never
   promoted from a count or a summary; the reviewer sees the same text a human
   reading the passage would.
2. **The approval action may cover many rows at once**, provided every row was
   individually displayed with its evidence and every row is recorded
   individually in `promotion_log.json` (unchanged — `_claim_key`-keyed, one
   entry per key, same as today).
3. **The pre-verification signal may order and annotate; it may never promote.**
   No code path writes `trust_tier=1` off a bucket assignment alone — bucketing
   (`extraction/claim_evidence.py`) is what a reviewer reads before deciding, not
   a substitute for the decision.
4. **A row whose evidence line reads "no match" may not be approved in a
   batch.** Buckets C, D, E and UNPARSED all mean the automated pass found no
   verbatim span — that row requires an opened segment (which `review_passage`
   already prints) and an individual read before approval.
5. **The same rule binds batch rejection.** A rejection is a recorded per-row
   verdict written to `trust_tier=2`, marked `[ALREADY REJECTED]` for every
   later reviewer — a decision of the same weight as a promotion, not the
   absence of one. A row whose evidence line reads "no match" therefore may not
   be batch-*rejected* either, for the same reason it may not be
   batch-*approved*: "no match" is an absence of evidence, not evidence of
   absence, until a human has read the segment it sits in.
6. **One carve-out, stated as a condition on the segment, not on the
   reviewer's confidence.** Where **neither** party of a `parentage` claim is
   attested anywhere in the cited segment under any spelling either alias layer
   knows (`claim_evidence` bucket E) — and only once B2a's cross-check reports
   `known_aliases.json` and the live `entity_aliases` table agree — the
   *absence itself* is the displayed evidence, and a batch covering only such
   rows, over passages the review queue has not yet opened, may reject them
   (Track C5, budgeted separately under the seeding rule). Where **one** party
   is attested and the other is not (bucket D), this carve-out does not apply:
   that asymmetry is exactly the alias-gap-vs-misattribution ambiguity B2a
   exists to resolve, and only an opened segment settles it. Without this
   carve-out, point 5 would forbid C5 outright, since every bucket-E row's
   evidence line reads "no match" by construction.

No other part of this ADR's Decision or the `trust_tier` gate changes: nothing
promotes without a human decision, nothing skips `promotion_log.json`, and
nothing here authorizes a new tier or a code path that writes `trust_tier=1`
automatically. See `docs/DEVIATIONS.md` #DEV-135.

---

## Amendment 2 (2026-08-01) — Reviewer-*authored* rows, and the conditions on them (DEV-150)

ADR-023 adds a correction channel: when a reviewer rejects a claim because the
cited passage attests something else, they may author the corrected row into
`ingestion/extraction/output/claim_corrections.json`, from which `seedgen` seeds
it exactly as it seeds a promoted candidate. This inverts the direction of the
gate for that small class — the machine proposes, the human *writes* — so the
gate's conditions must be stated explicitly rather than left to be read off a
workflow that no longer describes them.

Everything in Amendment 1 continues to bind. In addition, every row in
`claim_corrections.json`:

1. **Cites the `source_id` and `passage_ref` of a segment the reviewer actually
   opened.** A correction is a reading of a specific passage. It may never cite a
   passage that was not on screen, and never a passage inferred from another
   row's citation.
2. **Carries the `evidence_span` it was authored from** — the verbatim text
   supporting it — displayed at confirmation time exactly as a bucket-A row
   displays its matched span (Amendment 1 point 1). A correction with no span is
   not a correction.
3. **Is never written without a per-row human confirmation.** A machine-proposed
   correction that nobody confirmed is a candidate, not a correction, and no code
   path may write one. This is Amendment 1 point 3 ("may order and annotate; may
   never promote") applied to the proposal step: A14's matched span may pre-fill
   the row and may rank it, and may not author it.
4. **Names the rejection it answers**, via `corrects`. A correction is always the
   second half of a recorded verdict, never a free-standing insertion — which is
   what keeps the rejection intact as a verdict (Amendment 1 point 5) instead of
   being quietly overwritten.
5. **May not invent a claim, a source, or a passage the open segment does not
   support.** The reviewer's licence here is to record what the passage says
   where extraction recorded it backwards — not to supply mythological knowledge
   from outside the corpus. A true claim the cited passage does not state is
   `true_but_unattributable` (a rejection reason), not a correction.

The `trust_tier` gate itself is unchanged, and the trust guarantee is unchanged:
nothing reaches the seeded table without an explicit human decision recorded in
`promotion_log.json`. See ADR-023 and `docs/DEVIATIONS.md` #DEV-150.
