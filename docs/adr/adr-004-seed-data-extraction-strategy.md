# ADR-004: Tiered LLM Extraction (with Human Review Gate) for Seed Data, Replacing Full Hand-Curation

| Field        | Value       |
|--------------|-------------|
| **Date**     | 2026-07-08  |
| **Status**   | Accepted    |

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
