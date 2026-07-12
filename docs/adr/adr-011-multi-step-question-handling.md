# ADR-011: Multi-Step Question Handling (Source-Scoped Retrieval & Question Decomposition)

| Field        | Value       |
|--------------|-------------|
| **Date**     | 2026-07-12  |
| **Status**   | Proposed    |
| **Amends**   | ADR-007 §4 (`RouteDecision` enum), IMPLEMENTATION_PLAN.md §5 (`RagAgent` retrieval wiring) |

---

## Context

The query pipeline is **single-shot**: one routing classification, one retrieval strategy, one
synthesis (`IMPLEMENTATION_PLAN.md §5`, ADR-007). Three question classes strain or break that
shape:

1. **Per-source and comparative questions** — "What does *Hesiod* say about Typhon?", "How does
   Ovid's Arachne differ from other accounts?". The `ContentRetriever` performs unfiltered cosine
   search over all of `narrative_chunks`; whether the right author's chunks surface is luck, not
   design. Yet every chunk already carries `source_id` in both a column and its `metadata` JSONB —
   the filter key exists, it is just never used. For a product whose differentiator is *source*
   awareness, "according to X" questions failing silently is a conspicuous gap.
2. **Multi-hop questions with dependent lookups** — "Which children of the heroes who fought at
   Troy were themselves killed by a god?". No single route answers this: it needs an ordered
   sequence of sub-questions whose later steps depend on earlier answers. `MixedQueryHandler`
   hardcodes exactly one shape (SQL filter → RAG narration) and cannot express any other
   sequence.
3. **Aggregation** — already addressed separately by ADR-009 (`ship_contingents`); explicitly out
   of scope here.

A fully agentic answer (an LLM with tools, iterating until done) would subsume both gaps but
destroys the properties the PoC's evaluation depends on: deterministic route assertions, bounded
LLM-call counts, and per-stage testability (`IMPLEMENTATION_PLAN.md §7–8`).

## Decision

Adopt two scoped mechanisms, one per gap, and explicitly defer the agentic generalization.

### 1. Source-scoped retrieval (adopt; may land as a Phase 1 stretch item)

A lightweight probe — either a new `SourceProbe` `@AiService` (temperature 0.0) or an extension of
the existing `ConflictProbe`/`EntityExtractor` call — extracts an optional **author/work
constraint** from the question. When present, `RagQueryHandler` applies a metadata filter
(`source_id IN (…)`) to the `ContentRetriever` search (LangChain4j supports per-query dynamic
filters on the pgvector store; resolve author → `source_id` via the `sources` table, not a
hand-maintained map).

- "What does Hesiod say about X?" → retrieval restricted to `hesiod-theogony` (+
  `hesiod-homeric-hymns` only if the question names the Hymns; author→sources resolution returns
  all matching rows and the probe may narrow by work).
- Comparative questions ("How do Hesiod and Ovid differ on X?") run one filtered retrieval per
  named source (bounded by the number of authors named, cap 3) and synthesize with the existing
  conflict-aware `RagAgent` instruction (ADR-007 §3), which already mandates per-source
  attribution when accounts differ.
- No constraint extracted → behavior identical to today. The probe is additive and fails open.

### 2. Question decomposition for multi-hop questions (adopt for Phase 2)

- `RouteDecision` gains a fourth value: `COMPLEX`. This is **consistent with ADR-007's governing
  principle** — routing still selects a *retrieval strategy only* (here: "multiple dependent
  retrievals"); it still never decides conflict. The router's prompt instructs: emit `COMPLEX`
  only when no single strategy can answer, i.e. the question requires the answer of one lookup as
  the input of another.
- A new `QuestionDecomposer` `@AiService` (temperature 0.0) turns the question into an **ordered
  list of at most 3 sub-questions**, each answerable by a single existing strategy. A new
  `ComplexQueryHandler` runs each sub-question through the existing dispatch (router → handler),
  threading prior sub-answers into later sub-questions as injected context (the same augmentation
  pattern `MixedQueryHandler` already uses), then a final synthesis call composes the cited
  answer. Citations are the union of sub-answer citations.
- **Recursion is forbidden (depth 1).** If the router classifies a *sub*-question as `COMPLEX`,
  it is coerced to `RAG` and a warning is logged. Guarantees termination and a hard LLM-call
  ceiling: 1 (route) + 1 (decompose) + ≤3 × (route + handler) + 1 (synthesis).
- **Conflict enrichment runs once, on the original question, after synthesis** — unchanged from
  ADR-007 §5. Sub-questions are internal and get no enrichment of their own.
- **Failure degradation:** a failed sub-question is skipped and named in the final answer ("the
  step resolving X failed"), consistent with `QueryService`'s existing philosophy that partial,
  honest answers beat propagated exceptions. If *all* sub-questions fail, the standard
  `serviceError` response applies.

### 3. Non-goal: tool-calling agent (defer to Phase 3+)

Replacing the fixed router with a LangChain4j tool-using agent (`run_sql`, `search_narrative`,
`lookup_conflicts`) is the natural end-state and the existing guardrails (`SqlSafetyValidator`,
read-only `zeus_app`, 3s `statement_timeout`) already make it *safe*. It is deferred because it
makes routing non-deterministic, which breaks the gold-set route assertions and per-stage TDD
that this phase's quality story rests on. Trigger for revisiting: a demonstrated backlog of
questions that decomposition-at-depth-1 cannot express.

## Rationale

1. **Source-scoping is the highest value-to-cost extension available.** The metadata already
   exists on every chunk; the change is one probe and one filter parameter. It converts the
   product's core theme (source attribution) from an output property into an input capability.
2. **Decomposition reuses the pipeline instead of bypassing it.** Every sub-question passes
   through the same routing, SQL safety, citation, and refusal machinery — no second code path
   for the hard questions, so the guardrails hold by construction.
3. **`COMPLEX` respects the ADR-007 boundary.** It is a retrieval strategy (a composite one), not
   a conflict guess; enrichment stays router-independent and runs exactly once.
4. **Bounded by design, not by hope.** Sub-question cap, depth-1 rule, and coercion-to-RAG give a
   provable worst-case call count, keeping latency and cost predictable enough to evaluate.

## Consequences

**Positive**
- "According to X" and comparative questions become reliable instead of retrieval-lucky.
- Multi-hop questions become answerable with citations, without an agent rewrite.
- Worst-case LLM calls per query remain statically known.

**Negative / trade-offs**
- A fourth route value: router prompt, `QueryService` dispatch, eval schema, and the web UI route
  badge all need updating; ADR-010's eval expansion must add a `COMPLEX` category with new gold
  questions (decomposition is exactly the kind of feature that *looks* like it works untested).
- Decomposition quality is a new failure surface: a bad split produces a confidently wrong
  composite answer. Mitigated by the cap, the per-sub-question refusal behavior, and gold
  coverage; not eliminated.
- Latency: a `COMPLEX` question costs up to ~9 LLM calls. Acceptable for Phase 2 scope; noted for
  any future latency budget.
- Two probes now potentially run per query (source probe + conflict probe); folding both into one
  combined extraction call is an optimization to evaluate during implementation.

## Alternatives Considered

- **Tool-calling agent now.** Rejected for this phase: non-deterministic routing breaks the
  evaluation frame (see §3); revisit when depth-1 decomposition demonstrably runs out of road.
- **Hardcode more fixed shapes alongside `MixedQueryHandler`** (e.g. a `CompareQueryHandler`, a
  `TwoHopHandler`). Rejected: each new shape is a new handler + route + eval category; shapes
  multiply without ever covering the space. Decomposition expresses them all in one mechanism.
- **Source-scoping via prompt instruction only** ("answer using Hesiod passages only"). Rejected:
  the retriever has already returned the wrong chunks by the time the prompt runs; the model
  cannot cite what was not retrieved, so it either refuses or leaks non-corpus knowledge.
- **Always-on decomposition (decompose every question, single-question = 1 sub-question).**
  Rejected: adds a mandatory LLM call and a failure surface to the 90% of questions the current
  single-shot pipeline already answers well.

## Traceability

- ADR-007 §4–5: `RouteDecision`, routing = retrieval strategy only, enrichment placement.
- ADR-005: schema-boundary routing (unchanged; sub-questions inherit it).
- ADR-009: aggregation questions (explicitly out of scope here).
- ADR-010: evaluation set expansion (must gain `COMPLEX` and comparative gold questions).
- `IMPLEMENTATION_PLAN.md §5`: `ContentRetriever` wiring, `MixedQueryHandler` augmentation
  pattern; `§7` route-match scoring affected by the new enum value.

## Action Items

- [ ] Decide Phase 1-stretch vs Phase 2 for source-scoped retrieval (Decision 1); if Phase 1,
      add one gold question ("What does Hesiod say about the birth of Aphrodite?").
- [ ] Spike: confirm LangChain4j pgvector dynamic metadata filtering works against the custom
      `narrative_chunks` table (coordinate with the Stage 6 column-name verification).
- [ ] Phase 2: `RouteDecision.COMPLEX`, `QuestionDecomposer`, `ComplexQueryHandler`, depth-1
      coercion rule, per-sub-question failure wording.
- [ ] Extend ADR-010's proposed eval schema with `COMPLEX`/comparative categories and scoring.
- [ ] On acceptance: log **DEV-NNN**; add `> ⚠️ Amended by ADR-011` to ADR-007 §4 and
      `IMPLEMENTATION_PLAN.md §5`.
