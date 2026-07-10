# ADR-010: Evaluation Set Expansion & Per-Category Scoring

| Field        | Value       |
|--------------|-------------|
| **Date**     | 2026-07-10  |
| **Status**   | Proposed    |
| **Amends**   | IMPLEMENTATION_PLAN.md §7 (Evaluation); ADR-007 (Q13–15 re-pointing) |

---

## Context

The gold set is 17 questions across five categories (FACT, DATA, MIXED, CONFLICT, REFUSAL),
scored 3 pts each, target ≥75% aggregate (`IMPLEMENTATION_PLAN.md §7`). A review found three
weaknesses, amplified by the ADR-007/ADR-009 changes:

1. **The aggregate metric is brittle at n=17.** Each question is ~6% of the score; 13/17 passes
   (76%), 12/17 fails (71%). A pass/fail hinging on one flaky question carries little signal.
2. **The differentiator is thinly covered.** ~3 CONFLICT and ~2 REFUSAL questions: too few to
   trust the two capabilities the demo most rests on.
3. **New behaviors are untested.** ADR-007 introduced conflict surfacing via enrichment on
   *non-CONFLICT* routes, claim-type-relevant filtering (an appearance question must yield an
   *empty* conflict block), and a router that never emits CONFLICT. ADR-009 (if accepted) adds
   numeric aggregation. None of the original 17 exercise these, and ADR-007 already re-points
   Q13–15 away from `expected_route: CONFLICT`.

The gold set's role is a **smoke test with teeth** (prove each capability, catch regressions),
not a statistical benchmark. The fix is *targeted coverage*, not bulk size.

## Decision

1. **Grow to ~25 curated questions** with purpose-built additions (not bulk generation):
   - **CONFLICT via enrichment on a non-CONFLICT route**: a conflict-shaped question the router
     sends to SQL/RAG that must still populate `conflicts[]` (tests ADR-007 §5, router-independence).
   - **Claim-type-relevant REFUSAL**: an *appearance* question about a subject that has a stored
     *death* conflict, asserting `conflicts[]` is **empty** (tests ADR-007 claim-type filtering).
   - **Schema-boundary routing**: "Where is Achilles from?" → `expected_route: RAG`, no fabricated
     citation (ADR-005's open action item).
   - **Numeric / aggregation** (only if ADR-009 is accepted): "how many ships from X" → SQL with a
     count + citation, plus one numeric conflict (`ship_count` disagreement).
   - Additional CONFLICT and REFUSAL items to lift both above the current 2–3 floor.

2. **Report per-category pass rates with floors on CONFLICT and REFUSAL**, not only a blended
   aggregate. A 75% aggregate can hide a broken differentiator (e.g. 1/3 conflict). For this
   product, "CONFLICT ≥ floor" and "REFUSAL ≥ floor" are more honest bars than the average.

3. **Keep it curated.** Each question retains hand-authored `required_keywords` /
   `required_authors` / `forbidden_patterns` / `refusal_criteria`. Reject bulk auto-generation:
   quality and maintainability over count.

## Rationale

- **Coverage, not size, is the gap.** The additions map 1:1 onto behaviors that currently have no
  test; adding them is closing holes, not padding a number.
- **Per-category floors protect the differentiator.** Conflict-awareness is the whole product; it
  must not be able to fail silently behind a passing aggregate.
- **Curated beats bulk for a PoC**: high-signal, low-maintenance, and the authoring cost is the
  point (a good `forbidden_patterns` list is what catches hallucinations).

## Consequences

**Positive**
- New ADR-007/ADR-009 behaviors become regression-protected.
- The differentiator can't hide behind an average; eval results are more trustworthy.
- Larger n reduces single-question brittleness.

**Negative / trade-offs**
- More hand-authoring now and more maintenance as corpus/schema shift.
- `EvaluationRunner` and the §7 scoring logic must add per-category aggregation and floors, and
  drop the CONFLICT route-match for conflict questions (scoring them on `conflicts[]` instead).
- The numeric additions are contingent on ADR-009 being accepted.

## Alternatives Considered

- **Keep 17, aggregate-only (status quo).** Rejected: brittle metric, thin differentiator
  coverage, new behaviors untested.
- **Bulk-expand to 100+ (auto-generated).** Rejected: dilutes the hand-authored quality that
  makes each question a real check; heavy maintenance; a PoC eval is a smoke test, not a benchmark.
- **Add questions but keep aggregate-only scoring.** Rejected: without per-category floors a
  broken CONFLICT capability can still pass; the scoring change is the higher-value half.

## Traceability

- `IMPLEMENTATION_PLAN.md §7`: gold-question schema, scoring, `EvaluationRunner` (amended).
- `ADR-005`: schema-boundary gold question (open action item, now scheduled here).
- `ADR-007 §5`: enrichment / claim-type filtering behaviors the new questions test; Q13–15
  re-pointing.
- `ADR-009`: numeric/aggregation questions (contingent on acceptance).

## Action Items

- [ ] Author the ~8 new gold questions above in `evaluation/gold-questions.json`.
- [ ] Update `IMPLEMENTATION_PLAN.md §7` + `EvaluationRunner`: per-category pass rates, floors on
      CONFLICT/REFUSAL, conflict questions scored on `conflicts[]` not route match.
- [ ] Confirm the numeric questions are added only if ADR-009 is accepted.
- [ ] Log **DEV-017**; add `> ⚠️ Amended by ADR-010` to `IMPLEMENTATION_PLAN.md §7`.
