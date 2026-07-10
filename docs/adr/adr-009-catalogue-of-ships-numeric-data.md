# ADR-009: Catalogue of Ships (Numeric/Tabular Structured Data In Scope)

| Field        | Value       |
|--------------|-------------|
| **Date**     | 2026-07-10  |
| **Status**   | Proposed    |
| **Amends**   | ADR-005 (schema-boundary non-goal), ADR-007 §7 (attribute-structuring rule) |

---

## Context

ADR-005 made "no schema extension in this phase" a non-goal and routed all unmodeled attributes
(including numeric details) to RAG, with the empty-result fallback as a backstop. ADR-007 §7
sharpened the structuring rule to **"model a fact as a *sourced relation*, or not at all,"** gated
by ADR-005's promotion criteria (recurring question pattern, structurally enumerable, consistent
corpus coverage).

A review of numeric questions exposed a case those rules handle poorly. "How many ships came from
city X in the Trojan War?" routes to RAG today, but numeric/list retrieval is RAG's weakest mode:
the answer lives in the **Catalogue of Ships** (Homer, *Iliad* Book 2), a long enumerated list of
contingents, so semantic search may grab the wrong contingent, land in an adjacent chunk, or fall
below `minScore` and produce a wrong refusal. Aggregation ("total Greek fleet," "largest
contingent") is impossible for RAG at all: it retrieves, it does not compute.

The Catalogue is also the one numeric category that is **inherently tabular** in the source
(contingent/place → leader → ship count) and therefore *does* meet the promotion criteria:
structurally enumerable, consistent, and answerable only by operations (count/sum/max/filter)
that structure uniquely provides. It also fits neither existing structured shape: it is **not a
bare column** (which ADR-007 §7 forbids, being unsourced and conflict-incapable) and **not a
relation** (a ship count is not an edge between two figures). It is a third shape: a **sourced
numeric fact table.** This is precisely the `numerical_claim` direction ADR-004 considered and
deferred to Phase 2.

## Decision

**Bring numeric/tabular structured data into scope for the Catalogue of Ships**, via a dedicated
sourced table (working name `ship_contingents`):

```
ship_contingents(
  id,
  contingent      TEXT,              -- place/region/people, e.g. 'Argos', 'Boeotians'
  leader_entity_id INTEGER NULL REFERENCES entities(id),   -- when the leader is a modeled entity
  ship_count      INTEGER NOT NULL,
  source_id       TEXT NOT NULL REFERENCES sources(id)     -- Homer, Iliad Bk 2 (Murray)
)
```

Consequences of this shape:

1. **A new capability class: aggregation.** Enables "how many ships from X," "which contingent
   was largest," "total fleet": count/sum/max/filter queries that neither RAG nor
   `relationships`/`variant_claims` can answer. `SchemaIntrospector` surfaces the table
   automatically, so `QueryRouter` learns these questions are **SQL-answerable** and text-to-SQL
   handles them, moving "how many ships from X" from fragile RAG to precise, cited SQL.
2. **Sourced, therefore cited and conflict-capable.** `source_id` means results carry a citation
   (Homer, *Iliad* Bk 2), and, because ship counts genuinely vary across sources and manuscript
   traditions, a numeric disagreement flows through the ADR-007 conflict pipeline like any other
   (`variant_claims` with `claim_type='ship_count'`, surfaced by enrichment).
3. **Populated by extraction or hand-curation.** The Catalogue is highly regular, so it is a good
   extraction target (a dedicated pass over *Iliad* Bk 2), with the same review gate as other
   seed data. Small enough to hand-curate if extraction is unreliable.

**Reconciliation with prior ADRs:**
- **ADR-005 non-goal**: this is the first schema extension that *meets* the promotion criteria,
  so it is the sanctioned exception, not a reversal. Other unmodeled attributes (appearance,
  epithets, general locations) remain RAG-only.
- **ADR-007 §7**: adds a **numeric-fact-table** shape alongside relations. It is a *principled*
  exception to "structure as a relation": the rule's intent is "only structure what needs
  operations structure uniquely provides"; aggregation is such an operation, and the source is
  already tabular. It is emphatically *not* a bare unsourced column.

## Rationale

1. **The failure mode is real and RAG can't fix it**: numeric list lookup and aggregation are
   structurally outside retrieval's competence; a better embedding only nudges the margin.
2. **It meets the bar the general rule sets**: recurring shape, enumerable, consistent corpus
   coverage, needs aggregation. Adding it is applying ADR-005/ADR-007's own criteria, not
   overriding them.
3. **It reuses the conflict machinery**: sourced numbers get citations and conflict surfacing for
   free, keeping the product's provenance guarantee intact for numeric facts too.
4. **Scoped precedent**: a concrete first instance of the deferred `numerical_claim` idea,
   without reopening the broad numeric-extraction scope ADR-004 rejected.

## Consequences

**Positive**
- "How many ships from X" and aggregation questions become precise, cited, and testable.
- Establishes a clean, sourced pattern for future numeric/tabular data if demand appears.

**Negative / trade-offs**
- A new migration (`Vn__create_ship_contingents.sql`), a new extraction/curation task, and a new
  `SchemaIntrospector` table entry.
- A new capability class (aggregation) to cover in tests/eval (see ADR-010).
- `leader_entity_id` is nullable (not every contingent's leader is a modeled entity), so joins to
  `entities` are partial.
- Modest scope creep risk: must stay a *principled* exception; the promotion criteria remain the
  gate for any further numeric tables.

## Status note

**Proposed, pending two commitments:** (a) confirming the *Iliad* Catalogue is prepared as corpus
text (`CONCEPT.md §8` lists Homer *Iliad* / Murray as in-corpus, so the text is available), and
(b) a decision that numeric aggregation questions are in demo scope. Promote to **Accepted** once
both hold; until then, the questions remain RAG-answered (fragile) per ADR-005.

## Alternatives Considered

- **Keep RAG-only (status quo, ADR-005).** Rejected: fragile for lookup, impossible for
  aggregation.
- **Model contingents as a relation type.** Rejected: a ship count is a numeric attribute of a
  contingent, not an edge between two figures; forcing it into `relationships` distorts the graph.
- **A generic `numerical_claim` table now (the full ADR-004-deferred schema).** Rejected for this
  phase as over-broad; `ship_contingents` is the scoped first instance. Revisit the generic form if
  a second numeric category earns promotion.
- **A bare `entities` numeric column.** Rejected: unsourced, uncitable, conflict-incapable
  (ADR-007 §7), and it doesn't model per-contingent granularity.

## Traceability

- `ADR-004`: deferred `numerical_claim`/richer-schema idea (this is a scoped first instance).
- `ADR-005`: schema-boundary non-goal + promotion criteria (this is the criteria-met exception).
- `ADR-007 §7`: attribute-structuring rule (adds a numeric-table shape).
- `CONCEPT.md §8`: Homer *Iliad* (Murray) as in-corpus source.
- `IMPLEMENTATION_PLAN.md §3` (new migration), §4 (extraction), §5 (`SchemaIntrospector`,
  `TextToSqlAgent`), §7 (new numeric gold questions; see ADR-010).

## Action Items

- [ ] Add `Vn__create_ship_contingents.sql`; register the table in `SchemaIntrospector`'s table list.
- [ ] Add a Catalogue-of-Ships extraction pass (or hand-curated seed) with source attribution to
      Homer, *Iliad* Bk 2 (Murray, 1919); apply the standard review gate.
- [ ] Add numeric gold questions ("how many ships from X", an aggregation, a numeric conflict);
      coordinate with ADR-010.
- [ ] Log **DEV-016**; add `> ⚠️ Amended by ADR-009` to ADR-005 §Non-Goal and ADR-007 §7.
