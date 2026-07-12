# ADR-007: Data-Driven Conflict Detection and Surfacing (Open Claim Types, Router-Independent Enrichment)

| Field        | Value       |
|--------------|-------------|
| **Date**     | 2026-07-10  |
| **Status**   | Accepted    |
| **Amends**   | ADR-004 (seed-data extraction), ADR-005 (schema-boundary routing) |

---

## Context

Conflict awareness (surfacing where ancient sources disagree, attributed, instead of
flattening to one confident answer) is the product's defining feature (`CONCEPT.md §1, §5`).
A review of the Phase 1 plan against that goal surfaced three flaws in how conflicts were
detected, stored, and surfaced. All three trace back to a single conceptual error: **treating
conflict as a property of the *question* (decided by routing) rather than a property of the
*data* (decided by comparing sources).**

### Flaw 1: Detection was relationship-only

`variant_claims` (the CONFLICT data) was populated by three paths (`IMPLEMENTATION_PLAN.md §4`,
ADR-004):

1. An LLM `is_contested` flag, which fires only when a *single* source names a disagreement inline
   ("some say… others say…"). It is blind to conflicts that emerge only by comparing two separate texts.
2. `conflict_detector.py`'s mechanical cross-source scan: the only reliable detector, but it
   ran **only over `relationships`** (the controlled `parent_of`/`married_to`/`killed_by` vocab).
3. A hand-curated minimum floor (Aphrodite, Io, Achilles).

A conflict about a non-relationship attribute (manner of death, birthplace, transformation)
that wasn't inline-flagged was findable only by hand, because `variant_claims.claim_type` /
`claim_value` were free-form prose with no groupable key. There was no mechanical way to detect
"two sources disagree about how Achilles died."

### Flaw 2: The RAG fallback was not conflict-aware

`RagAgent` (`IMPLEMENTATION_PLAN.md §5`) answered-and-cited with a single synthesized answer.
A conflict that never reached `variant_claims` and routed to RAG (which, per ADR-005, is where
all non-modeled attributes route) was **flattened into one answer**, the exact failure the
product exists to prevent.

### Flaw 3: Surfacing was gated by the router's guess

`QueryRouter` classified some questions as `CONFLICT`, and only that route triggered the
`variant_claims` lookup (via `ConflictQueryHandler`). But the router cannot know whether the
sources actually disagree. It only guesses from question phrasing. A conflict-shaped question
misrouted to `SQL` or `RAG` (e.g. "Who were Aphrodite's parents?", which reads like a plain
fact lookup) **silently dropped its stored conflict**. The router was being asked to detect
something only the data can answer.

### Governing principle

> **Conflict *detection* is offline (ingestion time). Conflict *surfacing* is a data lookup at
> query time. *Routing* selects a retrieval strategy only, and never decides conflict.**

This ADR restructures detection, storage, and surfacing around that principle. Nothing here was
built at decision time: the affected migrations (V7, V11, V12), the `ingestion/extraction/`
pipeline, `RagAgent`, `QueryRouter`, and `QueryService` are all Stage 4–8 work. This is therefore
a pre-implementation amendment, recorded the way ADR-005 amended `IMPLEMENTATION_PLAN.md §5`
without rewriting it.

---

## Decision

### 1. Open `claim_type` + normalization map + query-based conflict finding (offline detection)

`claim_type` is **free text with no `CHECK` constraint** (an intentional departure from the
repo's `entities.type` / `sources.stance` / `sources.role` CHECK convention). The extractor may
emit *any* attribute label it observes in the text, including categories nobody enumerated
upfront. A curated **normalization/alias map** (`ingestion/extraction/claim_type_aliases.json`)
collapses surface variants to a canonical value (`death_manner`, `manner_of_death`, `how he died`,
`slaying`, `slain by`, `killed by` → `death`) before grouping.

The extractor stores **every** attributed claim of the observed types into the candidate stage,
not only inline-contested ones. A conflict then becomes a **query**, not an extraction-time
judgment:

```
GROUP BY (subject_entity, normalize(claim_type))
HAVING count(DISTINCT source_id) >= 2
```

Consequences of this shape:

- **Non-relationship conflicts are detected mechanically**: birthplace, death-manner, and
  transformation disagreements group exactly like parentage does.
- **Unanticipated claim types auto-detect.** The moment two sources use the same normalized
  label, the conflict surfaces as a candidate, so the developer does not have to predict the
  category. The vocabulary *grows from observed data* via the alias map rather than being
  guessed complete upfront (this directly answers "what about claim types I'm not yet aware of").
- **Detection no longer depends on the LLM *noticing* a disagreement.** It depends only on two
  sources making a claim of the same kind about the same subject.

`conflict_detector.py` is generalized from a relationships-only scan to a single GROUP-BY pass
over **all** candidate claims. Relationship candidates are mapped into the same space
(`parent_of → parentage`, `married_to → marriage`, `killed_by → death`), so structured
relationships and free-form claims flow through one detector.

**The relation→claim_type map and the `claim_type_aliases.json` canonical vocabulary are one
shared namespace** (DEV-020). Every relationship mapping must target a canonical that *also* owns
the corresponding free-text surface variants, so a disagreement captured half as a typed
relationship and half as free-text prose still groups under one key. Concretely, `parentage`,
`marriage`, and `death` are each canonicals in the alias map, and `death` collapses both manner
surface forms (`death_manner`, `manner_of_death`, `how he died`) and killer surface forms
(`slaying`, `slain by`, `killed by`). Mapping `killed_by` to a canonical the free-text death claims do **not** share (an
earlier draft used `slaying`) would split one death disagreement across two GROUP-BY keys —
`slaying` vs `death_manner` — silently defeating both offline detection and the exact-match
`ConflictLookup` at query time. Unifying the whole death dimension (killer *and* manner) under
`death` is deliberate and is the **conflict-grouping** key; it is orthogonal to ADR-005's
**routing** distinction between "who killed whom" (SQL via `killed_by`) and "manner of death"
(RAG). Because surfacing is router-independent (§5), a "who killed Achilles?" question and a "how
did Achilles die?" question both probe to `death` and surface the same unified conflict, whatever
route retrieved their primary answer.

One consequence of unifying killer *and* manner under one key: two sources can group as a `death`
"conflict" while being **complementary rather than contradictory** — e.g. one source names the
killer (`killed by Paris`) and another the manner (`a wound to the heel`). This is acceptable by
design: the product surfaces *attributed versions* of a claim dimension and lets the reader judge,
rather than asserting that the versions logically contradict. `ConflictSynthesizer` (§5) formats
all attributed versions *without picking a winner* and does not claim the versions contradict, so
complementary claims read as complementary. The alternative — splitting killer and manner into
separate keys to avoid this — reintroduces the fragmentation DEV-020 exists to prevent, which is
the worse failure.

### 2. Store-all is the candidate stage only; the runtime table stays reviewed-conflicts-only

"Store every attributed claim" applies to `extraction/output/variant_claims_candidates.json`
(all rows `trust_tier=3`). GROUP-BY detection runs over candidates **offline**. The human review
gate (ADR-004) promotes only conflict-participating, verified rows into `V12__seed_variant_claims.sql`
at `trust_tier=1`. The **runtime** `variant_claims` table therefore continues to hold only
reviewed conflicts. Its semantics are unchanged, so ADR-005's SQL routing surface is untouched
and no new SQL-answerable surface is introduced that the router would need to learn about.

The minimum-coverage floor (Aphrodite, Io, Achilles) and the `trust_tier` 3→1 gate remain hard
requirements, unchanged from ADR-004.

### 3. Conflict-aware RAG backstop (query-time catch-all)

`RagAgent`'s `@SystemMessage` is extended:

> *If the retrieved passages give different accounts of the same point from different sources,
> present each account with its attribution rather than choosing one or merging them.*

This is the true catch-all for *any* conflict that was never structured at all: it needs no
schema, no `claim_type`, no prior detection. `RagResponse{answer, citations}` is sufficient (the
disagreement lives in `answer` prose; both sources appear in `citations`), so no DTO change is
needed. `ContentRetriever` `maxResults=5` already allows multiple sources to be retrieved together.

### 4. Remove `CONFLICT` from the router (routing = retrieval strategy only)

- `RouteDecision` becomes `SQL | RAG | MIXED`.
- The `QueryRouter` prompt (ADR-005 §Decision.1) drops its *"route to CONFLICT if sources
  disagree"* instruction; the schema-boundary → RAG behavior is retained.
- `ConflictQueryHandler` is **deleted**. Its entity-resolution chain (name → alias → trigram)
  and `variant_claims` fetch move into a shared `ConflictLookup` component (§5).
- `QueryService`'s dispatch `when` loses its CONFLICT branch.

The router never makes a conflict-intent guess. There is one conflict path (enrichment), not two.

### 5. Data-driven, claim-type-relevant enrichment on every query (query-time surfacing)

After *any* handler answers, `QueryService` runs an enrichment step:

```
answer = dispatch(route, question)              // route ∈ SQL | RAG | MIXED
if !answer.serviceError:
    try:
        probe     = conflictProbe.extract(question)          // {subject, claimType}
        conflicts = conflictLookup.find(probe.subject, normalize(probe.claimType))
        if conflicts.isNotEmpty():
            answer = answer.copy(conflicts = conflictSynthesizer.synthesize(conflicts))
    catch:
        /* log; return answer unchanged — enrichment must never break the primary answer */
return answer
```

- **`ConflictProbe`** (`@AiService`, temperature 0.0) returns `{subject, claimType}`. It may be a
  new interface or an extension of the existing `EntityExtractor` (which already returns the
  subject); folding claim-type extraction into it keeps enrichment to one LLM call. It returns an
  empty/`none` `claimType` when the question maps to no modeled attribute. Then no structured
  lookup runs, and the RAG backstop (§3) covers any unstructured disagreement.
- **`ConflictLookup`** (shared) resolves the entity (exact → alias → trigram) and exposes two fetches over
  that one resolution. The **enrichment** fetch filters `variant_claims` to
  `subject_entity_id = ? AND claim_type = normalize(probeClaimType)`. `normalize()` is applied only to the
  **probe input**, not to the stored column — this exact-match requires that `V12` rows were promoted with the
  **normalized canonical** `claim_type` (surface variants collapsed at promotion time, per §1/§2), so that both
  rows of a conflict share one `claim_type` value. If promotion left surface variants in place, the two rows of
  a single conflict would carry different `claim_type` strings and the lookup would return only one — silently
  dropping the conflict. The composite index `idx_variant_claims_subject_type (subject_entity_id, claim_type)`
  already planned in `IMPLEMENTATION_PLAN.md §3` covers this lookup exactly.
- **`ConflictSynthesizer`** is reused unchanged to format the fetched versions.

**Claim-type filtering** (rather than subject-only surfacing) is deliberate **for the enrichment
path**: it keeps surfacing precise. An *appearance* question about Achilles yields an **empty**
`conflicts[]` even though Achilles has a stored *death* conflict, while a *death* question surfaces
it. This preserves the integrity of grounded refusals (`CONCEPT.md §13`, gold Q16–17): a refusal
about appearance is not polluted with an unrelated death conflict.

The **`GET /api/v1/conflicts/{entityName}` browse endpoint** is the one deliberate exception. It is
an explicit developer/demo lookup keyed on an entity with no claim-type context, so `ConflictLookup`
also exposes a **subject-only** fetch that returns every stored `variant_claims` row for the resolved
entity, across all `claim_type`s. This path never feeds enrichment and cannot pollute a grounded
refusal, because it is an explicit by-entity request rather than an automatic per-answer step. The
claim-type-filtered fetch remains the default and the only one the enrichment step uses.

**Enrichment writes `conflicts[]`, never `answer`.** FACT/DATA gold scoring (which inspects
`answer`) is therefore unaffected; `routeDecision` is unaffected. Only the conflict checks
benefit.

**Presentation is data-driven, not a mode switch.** `conflicts[]` renders prominently whenever
non-empty. For an inherently-contested fact (e.g. Aphrodite's parentage) the retrieval answer
comes back thin or empty, so the conflict block naturally *becomes* the visible answer, with no
`CONFLICT` route required to trigger it.

### 6. Contested relationships: one canonical edge in the graph; the contradiction in `variant_claims`

Relationships are a **typed, traversable graph** (`relationships(from_id, relation, to_id,
source_id)`) supporting enumeration and recursive lineage (`WITH RECURSIVE`, `CONCEPT.md §13`).
Storing two contradictory `parent_of` edges for one subject would **branch every traversal**:
"trace Zeus to Chaos" would fork into two family trees, and every DATA query would have to
disambiguate.

Policy: **`relationships` holds one canonical edge per fact; the contradiction lives in
`variant_claims`.**

- **Candidate stage:** the extractor pulls *all* attributed edges, including contradictory ones
  (`(Aphrodite, parent_of, Zeus, Homer)` and the Hesiod version). `conflict_detector.py` uses
  these to emit a `variant_claims` candidate (§1).
- **Review → runtime:** the developer keeps **one canonical edge** in `V11__seed_relationships.sql`
  (default preference: the spine source, per `sources.role='spine'`) and records the
  **disagreement in `V12__seed_variant_claims.sql`**. The contradiction is *not* stored as
  competing edges in the runtime graph.

Critically, **"canonical for traversal" is not "picking a winner for the user."** The user still
sees every version, because enrichment (§5) surfaces the `variant_claims` conflict on top of the
canonical answer. The internal graph representation and the user-facing answer are decoupled:
the graph stays clean and traversable; the product promise ("never silently flatten a conflict")
holds.

### 7. Attribute-structuring rule: structure as a sourced relation, or not at all

When a new attribute category (e.g. location/origin) is considered for the structured schema,
the rule is: **model it as a sourced relation type, never as a bare entity column.**

- A bare column (like `entities.type`, `entities.generation`, `entities.domain`) carries **no
  `source_id`**. It cannot be cited (ADR-005 already forbids fabricating a citation for these)
  and it **cannot participate in conflict detection or surfacing**, because both mechanisms key
  on `source_id`.
- A relation type (e.g. `originates_from`, with places promoted to `entities.type='place'`)
  inherits source attribution *and* flows through the conflict pipeline for free.
  (Note: `V3__create_entities.sql`'s CHECK constraint on `entities.type` does not include
  `'place'` — any such promotion requires an `ALTER TABLE ... DROP/ADD CONSTRAINT` migration
  extending the CHECK first. Not a blocker, just a known cost of each new entity category.)

This decision is **gated by ADR-005's existing promotion criteria** (recurring question pattern,
structurally enumerable, consistent corpus coverage). A conflict being representable in
`variant_claims` is a reason **against** adding a column: it does *not* meet the "enumerable
filterable fact" bar; it meets the "attributed claim" bar, which `variant_claims` already serves
with zero schema change. Schema extension is only warranted when a question needs the operations
structure uniquely provides (enumerate / filter / join / traverse), which no current gold
question does. No schema extension is adopted in this phase.

---

## Rationale

1. **Detection belongs where the sources are compared, not where the question is phrased.** The
   GROUP-BY-over-candidates design makes conflict a consequence of the data, reproducible and
   auditable, instead of a hope that an LLM flagged "some say." It generalizes the one reliable
   mechanism (cross-source scan) from relationships to every claim type.
2. **Open `claim_type` trades DB-level integrity for robustness to the unknown.** The product's
   whole premise is uncertainty about what the corpus contains; a closed vocabulary would silently
   drop conflict categories nobody anticipated. The normalization map recovers grouping
   consistency, and the RAG backstop covers anything the structured layer misses. The layered
   design degrades gracefully rather than dropping data.
3. **Router-independent surfacing removes a whole class of silent failure.** The most expensive,
   most-reviewed data in the system (`variant_claims`) is no longer hostage to a probabilistic
   routing guess. It surfaces whenever the data has it.
4. **The canonical-graph / conflict-store split reconciles two real needs**: a clean traversable
   graph for DATA/MIXED questions, and honest conflict surfacing, without compromising either.
5. **Reuses existing infrastructure.** Same `trust_tier` gate, same candidate-file review flow,
   same `EntityExtractor`/`ConflictSynthesizer`, same `idx_variant_claims_subject_type` index.
   Net structural change is a deletion (`ConflictQueryHandler`) plus a shared component
   (`ConflictLookup`) and one enrichment step.

## Consequences

### Benefits gained
- Non-relationship and previously-unanticipated conflicts are detected mechanically.
- Conflicts surface on any route, immune to router misclassification.
- Grounded refusals stay clean (claim-type-relevant filtering).
- One conflict code path instead of two; the router has one fewer class to confuse.
- FACT/DATA answer scoring is untouched (enrichment writes only `conflicts[]`).

### Accepted costs / trade-offs
- **No `CHECK` on `claim_type`.** The DB no longer guards the vocabulary; grouping correctness
  depends on the normalization map staying reasonably complete. Mitigated by review (unrecognized
  labels are visible in candidate files) and by the RAG backstop.
- **One extra temperature-0.0 LLM probe + one indexed lookup per query** for enrichment. Cheap,
  but non-zero latency on every request.
- **A misclassified `claimType` in the probe can miss a conflict** (surfaces nothing rather than
  something wrong). Mitigated by the normalization map and the RAG backstop.
- **Choosing a canonical relationship edge** is a curation judgment (default: spine source). It
  is *not* a user-facing "winner" (enrichment still surfaces all versions), but it is a decision
  the reviewer must make per contested edge.
- **Eval churn:** conflict gold questions (Q13–15) lose their `expected_route: CONFLICT`; their
  real test becomes the `conflicts[] ≥ 2 distinct versions` check (see Action Items).

### Amendments to prior ADRs
- **ADR-004**: `variant_claims` candidate generation now uses open `claim_type` + a normalization
  map + a generalized GROUP-BY detector over *all* candidate claims (not relationships only), and
  extracts all attributed claims rather than only contested ones. The review gate and `trust_tier`
  semantics are unchanged.
- **ADR-005**: the `QueryRouter` no longer emits `CONFLICT`; conflict surfacing is decoupled from
  routing entirely (enrichment). The schema-boundary → RAG routing and empty-result fallback are
  retained. The boundary still constrains single-fact retrieval of unmodeled attributes, but it no
  longer constrains conflict detection or surfacing.

## Alternatives Considered

**Keep `CONFLICT` as a router route (status quo / ADR-005).** Rejected: it asks the router to
detect a data property it cannot see; a misrouted conflict-shaped question silently drops its
stored conflict.

**Keep `CONFLICT` as a presentation-only hint (router still emits it, but only to choose
primary-vs-supplement rendering).** Considered as a lighter option. Rejected: it retains a fuzzy
conflict-intent guess in the router for no correctness benefit, since enrichment already
guarantees surfacing and thin/empty primary answers already promote the conflict block
naturally. Deleting `CONFLICT` is simpler and fully consistent with the governing principle.

**Controlled `CHECK` vocabulary for `claim_type` + an `other` escape hatch.** Considered: cleaner
DB integrity, matches repo convention. Rejected for this phase because novel types would land in
`other` and *not auto-group* until a human named them, reintroducing manual dependence for exactly
the "unknown unknowns" case this ADR aims to handle. Free-text + normalization map gives better
recall on unanticipated types; the RAG backstop covers the rest.

**Subject-only enrichment (surface all conflicts for the subject, regardless of question topic).**
Considered: simplest. Rejected because it pollutes grounded refusals and off-topic answers with
tangential conflicts (an appearance question surfacing the Achilles death conflict). Claim-type
filtering costs a small classification step and is worth it.

**Store contradictory relationships as multiple edges; derive `variant_claims` from them.**
Rejected: branches graph traversal and complicates every DATA/lineage query. The canonical-edge +
`variant_claims` split (§6) keeps the graph clean while preserving the conflict.

**Add columns/tables for unmodeled attributes (locations, appearance, etc.) now.** Rejected per
§7 and ADR-005's non-goal: no current demand meets the promotion criteria; `variant_claims`
covers the *conflict* dimension and RAG covers *retrieval* with citations, neither needing a
schema change.

## Traceability

- `CONCEPT.md §1, §5, §13`: conflict awareness as the differentiator; family-tree/genealogy demo
- `IMPLEMENTATION_PLAN.md §3`: V7/V11/V12 schema, `idx_variant_claims_subject_type`, `trust_tier`
- `IMPLEMENTATION_PLAN.md §4`: extraction pipeline, `conflict_detector.py`, `schema.py`
- `IMPLEMENTATION_PLAN.md §5`: `QueryRouter`, `RouteDecision`, `RagAgent`, `ConflictQueryHandler`,
  `EntityExtractor`, `ConflictSynthesizer`, `QueryService`
- `IMPLEMENTATION_PLAN.md §7`: gold questions Q13–17
- `ADR-004`: seed-data extraction strategy (amended)
- `ADR-005`: schema-boundary routing (amended)

## Action Items

**Offline / extraction (Stage 4):**
- [ ] `schema.py`: `ExtractedVariantClaim.claim_type` stays free-text `str`; extractor hinted (not
      restricted) with the known canonical types.
- [ ] Add `ingestion/extraction/claim_type_aliases.json` (canonical → variants) + a `normalize()`
      helper used by both the detector and, at query time, `ConflictLookup`.
- [ ] `claim_extractor.py`: extract all attributed claims of observed types, not only contested.
- [ ] `conflict_detector.py`: single GROUP-BY pass over all candidate claims keyed on
      `(subject, normalize(claim_type))`; map relationship candidates into the same space.
- [ ] `V7__create_variant_claims.sql`: `claim_type TEXT` with **no** CHECK constraint.
- [ ] Relationship review (V11/V12): keep one canonical edge per contested fact (spine-preferred);
      record the contradiction in V12. Preserve the Aphrodite/Io/Achilles floor.
- [ ] `V12` promotion: write each row's `claim_type` as the **normalized canonical** value (apply
      `normalize()` at promotion), so runtime `ConflictLookup`'s exact-match returns both rows of a conflict.

**Runtime (Stages 5–8):**
- [ ] `RouteDecision`: `SQL | RAG | MIXED`; remove `CONFLICT`.
- [ ] `QueryRouter` prompt: remove the CONFLICT instruction; keep schema-boundary → RAG.
- [ ] Delete `ConflictQueryHandler`; extract `ConflictLookup` (entity resolution + a claim-type-
      filtered fetch for enrichment **and** a subject-only fetch for the `/conflicts/{entityName}` endpoint).
- [ ] `ConflictProbe` (`@AiService`, temp 0.0) → `{subject, claimType}`, or extend `EntityExtractor`.
- [ ] `RagAgent`: add the conflict-aware disagreement instruction to the system message.
- [ ] `QueryService`: add the enrichment step (skip on `serviceError`; wrap so it never breaks the
      primary answer).

**Evaluation & docs:**
- [ ] `evaluation/gold-questions.json`: re-point Q13–15 `expected_route` (parentage → SQL, death →
      RAG); update `IMPLEMENTATION_PLAN.md §7` scoring so conflict questions score on `conflicts[]`,
      not a CONFLICT route match. Optionally add one non-scored RAG-backstop probe.
- [ ] Log **DEV-014** in `docs/DEVIATIONS.md` pointing to this ADR.
- [ ] Add `> ⚠️ Amended by ADR-007` pointer notes to `IMPLEMENTATION_PLAN.md` §3, §4 (incl. the
      Extraction-Pipeline subsection), §5, §7, §8, and the Stage 9 sequence block, and to `ADR-005 §Decision.1`.
- [ ] Add a `QueryRouterTest` case asserting the router never emits CONFLICT and that a conflict-
      shaped question routed to SQL/RAG still yields a populated `conflicts[]` via enrichment.
