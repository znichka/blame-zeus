# ADR-005: Structured Data Coverage Gaps and Schema-Boundary Routing

| Field        | Value       |
|--------------|-------------|
| **Date**     | 2026-07-08  |
| **Status**   | Proposed    |


## Context

The `entities`/`relationships` schema (`entities(id, name, type, generation, domain)`, `relationships(from_id, relation, to_id, source_id)`) does not model several attribute categories present in the corpus:

| Attribute category | Example question | Modeled? |
|---|---|---|
| Birthplace/homeland | "Where is Achilles from?" | No |
| Physical description | "What did Achilles look like?" | No (existing REFUSAL case, Q16) |
| Epithets/titles | "What is Zeus's epithet as sky-father?" | No |
| Notable objects/weapons | "What weapon did Perseus use to kill Medusa?" | No |
| Manner/detail of death | "How exactly did Achilles die?" | Partial: `killed_by` captures the killer, not the method |

This is a schema-boundary gap, not a data-quality gap. Missing rows (extraction under-coverage) are addressed by review process (`ADR-004`); this ADR addresses attribute categories that have no column or relation type to populate in the first place. No extraction improvement fixes this class of gap. It requires either a schema change or a routing decision.

**Failure mode:** SQL has no confidence signal analogous to RAG's similarity threshold. A query against an existing table always executes, returning either zero rows or the wrong columns, never an explicit "I don't have this." If `QueryRouter` classifies a schema-unanswerable question as `SQL`, the result is a confident, silent, incorrect or empty answer. `QueryService`'s existing fallback (`catch (e: Exception) { RouteDecision.RAG }`) does not trigger here, because misclassification does not throw an exception.

**Gap identification method** (repeatable without mythology domain expertise):
1. Enumerate schema columns; for each, state what question categories it can and cannot answer
2. Generate a broad set of realistic mythology questions independently of the schema; check each against actual columns
3. Present the schema to an LLM and request an explicit list of unanswerable question categories
4. Cross-check against existing precedent: physical appearance is already RAG/refusal-routed (Q16-17), establishing "schema does not cover X → route to RAG" as an accepted pattern

**Design constraint driving this ADR's structure:** an initial draft of this decision proposed a hand-maintained list of "RAG-only" categories embedded directly in `QueryRouter`'s prompt, paired with a separate coverage-matrix document. That design was rejected during review because it creates two independently maintained artifacts (matrix, router prompt) with no enforced link. They can silently diverge, reintroducing exactly the kind of undetected gap this ADR exists to prevent. The schema itself is already a live, always-accurate description of what SQL *can* answer (via `SchemaIntrospector`, already consumed by `TextToSqlAgent`); this ADR uses that same mechanism as the router's source of truth, rather than a second hand-written list.

## Decision

Treat coverage gaps as an explicitly documented condition, addressed via schema-grounded routing plus a documentation artifact, scoped for this PoC phase. Schema extension to close identified gaps is explicitly deferred.

**PoC scope boundary:** This ADR defines routing behavior and documentation only. It does not add automated cardinality estimation or schema extensions. These are named as deferred, not omitted by oversight. See §Deferred to Later Stages.

### 1. Router Derives Schema Boundaries From the Live Schema, Not a Hand-Maintained List

> ⚠️ Amended by ADR-007 — see `docs/adr/adr-007-conflict-detection-and-surfacing.md` and `DEVIATIONS.md` DEV-014.
> `RouteDecision` is `SQL | RAG | MIXED`; the router no longer emits `CONFLICT`. The
> `"route to CONFLICT if sources disagree"` instruction in the prompt below is **removed** (conflict surfacing
> is a router-independent `QueryService` enrichment step, not a route). The schema-boundary → RAG behavior in
> this section is retained. The prompt shown here is the pre-amendment version, kept for context.

`QueryRouter` will be wired with the same `SchemaIntrospector.get()` output already injected into `TextToSqlAgent`, and instructed to route to RAG when a question requests information with no corresponding column or relation type in the supplied schema:

```kotlin
@AiService
interface QueryRouter {
    @SystemMessage("""
        Classify the question into SQL, RAG, MIXED, or CONFLICT.
        
        The structured database contains ONLY these tables and columns:
        {{schema}}
        
        If the question asks for information with no corresponding column or
        relation type in this schema (for example: physical descriptions,
        locations, objects, titles, or any other attribute not listed above),
        route to RAG — even if the question is phrased like a data lookup.
        
        If the question asks whether multiple sources disagree on a claim,
        route to CONFLICT.
    """)
    fun classify(@V("schema") schema: String, @UserMessage question: String): RouteDecision
}
```

This gives the router a single source of truth for what SQL can answer: `information_schema.columns`, surfaced via `SchemaIntrospector`. No hand-maintained enumeration of RAG-only categories exists anywhere in the router logic. If a future migration adds a column (e.g., `entities.origin_city`), the router becomes aware that origin questions are SQL-answerable automatically, with no prompt update required.

**Known limitation, accepted for this phase:** this determines what the schema *positively contains*; the router still performs a judgment call to classify anything outside that list as RAG rather than mechanically guaranteeing correct routing. This is a probabilistic classification step, not a lookup. It is expected to be substantially more reliable than a hand-maintained negative list (since it is always grounded in the actual schema), but it is not a formal guarantee. §Decision.3 exists as a second line of defense for this reason.

### 2. Coverage Matrix Retained as Human-Facing Documentation Only

`docs/schema-coverage-matrix.md` is maintained as a review artifact for developers, used during schema changes, onboarding, and manual gap analysis (per the method in §Context). It is explicitly **not** read by any runtime component. Its role is documentation, not configuration.

| Attribute category | Modeled? | Column/relation | Route |
|---|---|---|---|
| Parentage | Yes | `relationships.relation='parent_of'` | SQL |
| Marriage | Yes | `relationships.relation='married_to'` | SQL |
| Who killed whom | Yes | `relationships.relation='killed_by'` | SQL |
| Entity classification | Yes | `entities.type` | SQL |
| Sphere of influence | Yes | `entities.domain` | SQL |
| Era/generation | Yes | `entities.generation` | SQL |
| Manner/detail of death | No | none | RAG |
| Birthplace/homeland | No | none | RAG |
| Physical appearance | No | none | RAG/Refusal |
| Epithets/titles | No | none | RAG |
| Notable objects/weapons | No | none | RAG |
| Conflicting claims (any type) | Yes | `variant_claims` | CONFLICT |

Update this matrix manually whenever a migration changes columns or relation types, or when a new gold question category is added. Because the router (§Decision.1) no longer reads this file, matrix staleness does not affect runtime routing behavior; it only affects the quality of manual review. This is a deliberate reduction in the matrix's scope from earlier drafts of this decision, made specifically to remove the drift risk described in §Context.

### 3. Handler-Level Fallback for Empty SQL Results

Second line of defense for router misclassification:

```kotlin
val rows = jdbcTemplate.queryForList(sql)
if (rows.isEmpty()) {
    log.warn("Empty SQL result for '{}' — falling back to RAG", question)
    return ragQueryHandler.handle(question)
}
```

Scope is deliberately narrow: catches zero-row results only. Does not evaluate whether a non-empty result is actually relevant to the question; that requires either LLM-based result validation or expected-cardinality estimation, both deferred (see §Deferred to Later Stages).

> ⚠️ Amended by DEV-026 (see `DEVIATIONS.md`, 2026-07-12): "zero rows only" is insufficient for
> aggregations — `COUNT(*)` over an empty match returns **one row containing `0`**, never zero rows,
> so once ADR-009's numeric data lands, "how many ships from ⟨place not in the table⟩" would return a
> confident "0" instead of falling back. The fallback also treats an **aggregate-zero** result as empty:
> a single row whose values are all `0`/`NULL`. A genuine zero count is indistinguishable at this layer
> and also falls back to RAG — acceptable for the PoC (cited text or refusal beats a fabricated number).

### 4. Non-Goal: No Schema Extension in This Phase

Identified gaps are not closed by adding columns. They remain RAG-routed for the duration of this PoC. Reasons:

- Each new column or relation type requires a migration, an extraction schema update, a new extraction prompt hint, a review-process update, and a `SchemaIntrospector`-surfaced prompt update, the same cost structure that makes `variant_claims` review expensive
- Narrative attributes (appearance, homeland, objects) are well-suited to cited RAG retrieval; a flattened SQL value is not necessarily a better answer format
- No confirmed demand exists yet: no current gold question requires these categories

## Consequences

**Positive:**
- Router boundary awareness is derived from a single, always-accurate source (`information_schema.columns` via `SchemaIntrospector`), with no second artifact to keep in sync
- Schema changes automatically expand or contract what the router treats as SQL-answerable, with zero prompt maintenance
- Coverage matrix retains clear value as a review/onboarding artifact without carrying any runtime responsibility, removing the risk of undetected drift between documentation and behavior
- Extends the existing REFUSAL precedent (Q16-17) into a stated, general policy

**Accepted trade-offs for this phase:**
- Schema-grounded routing is a judgment call performed by the LLM, not a deterministic guarantee. A sufficiently ambiguous question can still be misrouted; §Decision.3 mitigates but does not eliminate this
- §Decision.3 catches zero-row results only; a non-empty but irrelevant SQL result is not caught
- Column name matching a question's terminology does not guarantee semantic match (e.g., a `domain` column meaning "sphere of influence" could be misread by the router as covering "geographic territory"). This is a distinct failure mode from the one this ADR addresses and is not solved here
- Some question categories (e.g., "what weapon did Perseus use") will only ever be answered via RAG retrieval quality, with no SQL-precision fallback
- Coverage matrix accuracy depends entirely on manual updates; since it no longer feeds any runtime component, a stale matrix degrades documentation quality only, not system behavior

## Deferred to Later Stages

Explicitly out of scope for this ADR and this PoC phase. Listed here so they are tracked, not forgotten:

| Deferred item | Trigger for revisiting |
|---|---|
| Validate that schema-grounded router prompting (§Decision.1) achieves acceptable classification accuracy on schema-boundary questions in practice | Immediately, via the gold question added in Action Items. If accuracy is poor, add a hand-maintained exclusion list as a supplementary hint for categories the LLM consistently misjudges |
| Non-empty-but-irrelevant SQL result detection (LLM-based result validation or expected-cardinality estimation) | If §Decision.3's zero-row-only check proves insufficient in production usage |
| Automated detection of *new* gaps as corpus/gold set grows | If the gold question set expands significantly beyond the current 17 questions |
| Schema extension for any RAG-only category | Only if a category meets all three promotion criteria below |
| Row-completeness gaps within existing columns (e.g., extraction missing a child of Cronus) | Tracked separately under `ADR-004`; not this ADR's concern |
| Column-name/concept semantic mismatch detection (e.g., `domain` meaning sphere-of-influence vs. geography) | If a real misrouting case of this kind is observed post-PoC |

**Promotion criteria for moving a category from RAG-only to schema-modeled (future decision, not this ADR):**
1. Recurring question pattern confirmed in real usage or an expanded gold set, not hypothetical
2. Attribute is structurally enumerable (a fact, not a description)
3. Corpus contains it consistently enough across entities for extraction to yield real coverage

## Alternatives Considered

**A. Hand-maintained "RAG-only" category list embedded in the router prompt, paired with a separate coverage-matrix document.** Rejected: this was the initial draft of this decision. Creates two independently maintained artifacts with no enforced link; they can silently diverge, which reproduces the exact silent-failure problem this ADR exists to prevent.

**B. Extend schema now to cover all identified gaps.** Rejected: no confirmed demand; front-loads extraction/review cost against `IMPLEMENTATION_PLAN.md` §1 non-goals around exhaustive seed data.

**C. Rely solely on the existing exception-based router fallback (no changes).** Rejected: confirmed insufficient; confident misclassification does not throw, so the existing catch block never activates for this failure mode.

**D. Full expected-cardinality estimation before every SQL execution.** Rejected for this phase as disproportionate to PoC scope. Listed in §Deferred to Later Stages as the next step if §Decision.3 proves insufficient.

## Traceability

- `IMPLEMENTATION_PLAN.md` §5: `QueryRouter`, `TextToSqlAgent`, `SchemaIntrospector`, `SqlQueryHandler`
- `IMPLEMENTATION_PLAN.md` §3: `entities`/`relationships` schema, V3/V4 migrations
- `IMPLEMENTATION_PLAN.md` §7: Q16-17 (existing REFUSAL precedent)
- `CONCEPT.md` §2: "false certainty" as a named failure mode this ADR extends to schema-boundary honesty
- `ADR-004`: seed data extraction strategy; addresses row-completeness, a distinct concern from this ADR's schema-boundary concern

## Action Items

- [ ] Wire `SchemaIntrospector.get()` into `QueryRouter`'s prompt per §Decision.1
- [ ] Create `docs/schema-coverage-matrix.md` per §Decision.2, seeded with the categories in §Context, marked explicitly as documentation-only
- [ ] Implement empty-result fallback in `SqlQueryHandler` per §Decision.3
- [ ] Add gold question(s) testing schema-boundary routing (e.g., "Where is Achilles from?" → `expected_route: RAG`)
- [ ] Add `QueryRouterTest` asserting known schema-boundary questions route to RAG, using a Testcontainers-backed schema so `SchemaIntrospector` output is real, not mocked
- [ ] Measure router classification accuracy specifically on schema-boundary questions after Phase 5 (SQL Pipeline); if below an acceptable threshold, escalate the first row of §Deferred to Later Stages from "deferred" to "immediate"
- [ ] Re-check coverage matrix after Phase 4 (Seed Data) against actual extracted `relation`/`claim_type` values, to confirm no additional undocumented gaps exist
