# ADR-015: Unified Answer Composition (Final LLM Compose Stage, Conflicts Woven Into Prose)

| Field        | Value       |
|--------------|-------------|
| **Date**     | 2026-07-20  |
| **Status**   | Accepted    |
| **Amends**   | ADR-007 (§5 conflict surfacing — presentation only) |
| **Amended by** | —         |

---

## Context

blame-zeus answers every question through one of three retrieval strategies — `SqlQueryHandler`,
`RagQueryHandler`, `MixedQueryHandler` — after which a router-independent enrichment step attaches
`conflicts[]` (ADR-007). All paths converge on a single `QueryResponse{answer, routeDecision,
citations, conflicts, sqlGenerated, serviceError}` rendered by both the REST API and the Thymeleaf
web UI.

In practice the three routes produce **structurally different output**, and the difference is
visible to the end user:

1. **SQL answers are not human-readable and are usually uncited.**
   `SqlQueryHandler.formatAnswer` mechanically joins raw DB rows —
   `"Zeus, olympian, 1; Hera, olympian, 1"` — never prose. Citations are sniffed opportunistically
   from result columns named `author`/`work` (`extractCitations`); the many entity/relationship
   queries that do not project those columns yield **no references at all**. There is no
   `ChatModel` pass on the SQL path, so the quality gap versus RAG is structural, not incidental.

2. **RAG and MIXED answers are LLM prose with structured citations** (`RagAgent` → `RagResponse`),
   so they look nothing like SQL answers even for comparable questions.

3. **Conflicts are always a separate, deterministic side-box.** Per ADR-007 §5 and DEV-051,
   `ConflictSynthesizer` is a non-LLM 1:1 mapper that writes only `conflicts[]` and never touches
   `answer`. The disagreement — the product's defining feature — is therefore rendered *beside* the
   answer, never *within* it. On the web page it is an orange "Sources disagree" list detached from
   the prose.

The product goal (`CONCEPT.md §1, §5`) is a single, human-friendly, source-attributed answer in
which disagreement reads as part of the narrative. The current per-route divergence works against
that goal: the same question can return fluent cited prose or a bare row dump depending only on how
the router classified it.

### Why this is an architectural decision, not just a fix

Resolving (3) means putting conflict content **into `answer`**, which directly reverses a decision
ADR-007 §5 made on purpose: keep conflict presentation deterministic, data-driven, and out of the
synthesized answer so an enrichment failure can never corrupt a good answer, and so no LLM ever
"picks a winner." That guarantee is worth preserving even as we change the presentation, so the
reversal is scoped narrowly and recorded here rather than buried in an implementation deviation.

## Decision

Introduce a single **final composition stage**, `AnswerComposer`, that runs on **every** non-error
route as the last step of `QueryService.handle()`, after conflict claims have been fetched. It
replaces the divergent per-route presentation with one uniform, human-friendly shape.

### 1. `AnswerComposer` — a new `@AiService`

A LangChain4j chat service (`ai/AnswerComposer.kt`) bound by EXPLICIT wiring to the existing
`synthesisModel` bean (temperature 0.3, same bean `RagAgent` uses — no new bean in
`LangChain4jConfig.kt`, no new provider surface). It takes the primary material plus any conflict
claims and returns JSON deserialized into `ComposedAnswer{answer, citations}`:

```
compose(question, material, conflicts) -> ComposedAnswer
```

- `material` — the draft handler output rendered as facts: for SQL, the rows serialized with
  column names (`name=Zeus, type=olympian, generation=1`); for RAG/MIXED, the draft prose plus its
  citations. The composer rewrites this into one fluent answer.
- `conflicts` — the structured `variant_claims` rows for the question (or the literal `none`).
  When present, the composer **weaves each version into the prose, attributed, without picking a
  winner** — preserving ADR-007's neutrality requirement while changing where the disagreement
  appears.
- Output — a single answer string carrying inline `[n]` citation markers, and a `citations` list
  that is the **deduped union of answer sources and conflict sources**, ordered by first appearance,
  such that marker `[n]` indexes `citations[n-1]`.

The composer is held to `RagAgent`'s citation discipline: use only the provided material, copy
`author`/`work`/`passageRef`/`stance` verbatim, never invent a source, and ensure every `[n]` has a
matching reference and vice versa.

### 2. Pipeline reorder in `QueryService`

```
route → handler.handle()            = DRAFT   (facts + best-effort citations)
      → conflictProbe + lookup      = CLAIMS  (structured variant_claims rows)
      → answerComposer.compose(...)  = FINAL   (uniform prose + unified references + inline [n])
```

The former `enrich()` (which copied `conflicts[]` onto the answer) becomes a helper that *returns*
the `List<ConflictClaim>`; composition consumes those claims. `conflicts[]` is still populated on
the response (via `ConflictSynthesizer`) for API consumers, transparency, and the fallback path.

### 3. Failure containment (ADR-007's guarantee, preserved)

The composer call is wrapped. On any exception — or for a `serviceError` draft — `QueryService`
returns the **pre-composition draft** unchanged (SQL row dump / RAG prose) together with the
structured `conflicts[]` and `conflictsInProse = false`. A new boolean `QueryResponse.conflictsInProse`
records whether weaving succeeded; the web UI renders the legacy "Sources disagree" box **only** in
the fallback case, so conflict information is never lost and never duplicated.

### 4. Presentation

`QueryResponse.answer` is now prose with inline `[n]` on all routes; `citations` is the unified
ordered reference list (list order == marker number); the web template renders one numbered
**References** list and drops the default conflict box in favour of woven prose.

## Alternatives considered

- **Dedicated SQL-only narrator, conflicts left deterministic.** Add a narrow `SqlAnswerNarrator`
  for the SQL route and keep the ADR-007 §5 side-box. Smaller blast radius and no reversal of
  ADR-007, but SQL and RAG/MIXED would still differ (RAG has no inline markers), and it does not
  satisfy the requirement that disagreement appear *in* the answer text. Rejected: solves (1)/(2)
  only, not (3), and leaves two presentation code paths.

- **Deterministic conflict sentence appended to the answer.** Render `variant_claims` into a fixed
  template sentence with no LLM. Cheap and risk-free, fully honours DEV-051's spirit, but the prose
  is templated rather than fluent and cannot integrate the disagreement into the surrounding
  narrative. Rejected on quality grounds (the user prioritised result quality); retained instead as
  the conceptual basis for the fallback rendering.

- **Compose only when conflicts exist.** Run the composer conditionally to save a call on plain
  RAG answers. Rejected: uniform structure (including inline markers on RAG) is the goal, so the
  composer must run on every route.

## Consequences

**Positive**
- One uniform, human-friendly answer shape across SQL, RAG, and MIXED — prose, inline `[n]`, a
  single References list.
- SQL answers gain real prose and real citations (from projected provenance columns).
- Source disagreement is narrated in-line, attributed — the product's defining feature is now part
  of the answer rather than a detached box.
- ADR-007's "enrichment never breaks the answer" and "never pick a winner" guarantees are retained
  via the wrapped fallback and the neutral, attribution-only weaving instruction.

**Negative / costs**
- **One additional LLM call per query** (the composer runs on every non-error route, including
  plain RAG). Accepted as a deliberate quality-first trade-off for a Phase 1 PoC.
- The composer re-processes already-synthesized RAG prose to add markers and weave conflicts,
  introducing a small risk of rewording; mitigated by temperature 0.3, a fidelity-preserving system
  prompt, and the requirement to reuse verbatim source metadata.
- ADR-007 §5's presentation stance (deterministic, out-of-`answer`) is superseded for prose. The
  **data model is unchanged**: `variant_claims`, `ConflictLookup`, `ConflictProbe`, and the
  deterministic `ConflictSynthesizer` all remain; only where the result is rendered changes.

**Follow-ups**
- Record `DEV-0NN` in `docs/DEVIATIONS.md` cross-referencing this ADR; add the deviations note to
  the affected stage in `IMPLEMENTATION_PLAN.md`; annotate ADR-007 §5 as amended by ADR-015.
- TDD: mock `AnswerComposer` in `QueryServiceTest` (no live LLM); assert uniform composition,
  `conflictsInProse` semantics, and fallback preservation of the draft answer + structured
  `conflicts[]`; update `SqlQueryHandlerTest` for the column-named `formatAnswer` and the
  controller/web tests for the unified references shape.
