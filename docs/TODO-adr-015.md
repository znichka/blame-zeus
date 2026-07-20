# ADR-015 — Unified Answer Composition: Detailed Checklist

**Done when:** every non-error route (`SqlQueryHandler`, `RagQueryHandler`, `MixedQueryHandler`)
returns a `QueryResponse.answer` that is **fluent prose with inline `[n]` citation markers** and a
**single unified `citations` list** where marker `[n]` indexes `citations[n-1]`; a conflict-shaped
question **weaves each attributed version into the prose without picking a winner**
(`conflictsInProse = true`); on composer failure **or** a `serviceError` draft, `QueryService`
returns the **pre-composition draft unchanged** together with structured `conflicts[]` and
`conflictsInProse = false`; `conflicts[]` is always present (possibly empty) on every response
(for API consumers, transparency, and the fallback box); and the full `:core-api:test` suite is
green.

> **This is post-MVP work — not part of `IMPLEMENTATION_PLAN.md §9`.** It implements
> `docs/adr/adr-015-unified-answer-composition.md`, decided after Stage 9 shipped. It is tracked
> under `TODO.md`'s **Post-MVP Enhancements** section, named by ADR (not a numbered stage), so the
> §9 stage history stays untouched.

> **Design is ADR-015's, not its rejected branches.** A single final composition stage,
> `AnswerComposer`, runs on **every non-error route** as the last step of `QueryService.handle()`,
> after conflict claims are fetched. It does **not** replace the conflict *data* machinery —
> `variant_claims`, `ConflictProbe`, `ConflictLookup`, and the deterministic `ConflictSynthesizer`
> all remain; only **where the conflict result is rendered** changes (into `answer`, not a detached
> box). Do **not** build any of the rejected alternatives: no SQL-only narrator, no templated
> conflict sentence (that idea survives only as the conceptual basis for the fallback rendering),
> and no "compose only when conflicts exist" (the composer runs on every route so structure is
> uniform, including inline `[n]` on plain RAG).

Before starting, re-read `DEVIATIONS.md`. Relevant carry-overs:

- **ADR-007 §5 is superseded *for prose presentation only*.** The **data model is unchanged**.
  Conflict content moves **into `answer`**, which narrowly reverses ADR-007 §5's "keep conflict
  presentation out of the synthesized answer" decision — but ADR-007's two guarantees are preserved:
  (a) "enrichment never breaks the answer" via the wrapped fallback, (b) "never pick a winner" via
  the neutral, attribution-only weaving instruction. ADR-007 §5 must be annotated "Amended by
  ADR-015" (Track F).
- **DEV-051** — `ConflictSynthesizer` stays a deterministic, non-`@AiService` `@Component`
  (`variant_claims` rows → `List<ConflictEntry>`). It is still used to populate `conflicts[]` for
  the response and the fallback box. Do **not** turn it into an LLM service.
- **DEV-046** — two `ChatModel` beans exist (`routingModel`, `synthesisModel`), so every
  `@AiService` interface **must** declare `@AiService(wiringMode = EXPLICIT, chatModel = "...")` by
  LangChain4j bean-name string (not Spring `@Qualifier`) or startup fails. `AnswerComposer` binds to
  the existing **`synthesisModel`** (temp 0.3) — **no new bean in `LangChain4jConfig.kt`, no new
  provider surface** (copy `RagAgent`'s `chatModel` + EXPLICIT wiring — but **not** its
  `retrievalAugmentor`, since `AnswerComposer` receives `material` as a param and does no retrieval).
- **DEV-055** — controller/web tests mock `QueryService` via `@MockkBean` (never a live
  `@AiService`); `TECH_GUARDRAILS` forbids live LLM calls in tests. `QueryServiceTest` mocks each
  `@AiService`/handler with mockk — add an `AnswerComposer` mock there.
- **DEV-053 (partially closed by this ADR).** DEV-053's *user-facing* half — `SqlQueryHandler`'s
  raw comma-joined row dump surfacing as `answer` — is resolved here: the composer turns the
  column-named material into prose. Track C changes `formatAnswer` to emit column-named material for
  the composer; on the composer-**success** path the row *dump* is no longer what the user sees.
  (On the composer-**failure** fallback the draft is returned unchanged, so the column-named material
  — a raw dump, arguably more verbose than the old value-only join — does surface; the closure is
  therefore success-path only.)
- **DEV-054 / Stage 8.5 (NOT touched here).** Q9/Q11/Q12's `WITH RECURSIVE` and MIXED
  over-constraint SQL-generation gaps are out of scope. Those still fail → `serviceError: true` →
  the composer's **fallback path** renders the draft (error banner) unchanged. This ADR neither
  fixes nor regresses them.

**Cost note (accept explicitly).** The composer runs on **every non-error route, including plain
RAG** — that is **one additional LLM call per query**. Accepted as a deliberate quality-first
trade-off for a Phase 1 PoC (ADR-015 Consequences). Do **not** add a "skip composer when no
conflicts" shortcut — uniform structure is the goal.

**Deviation protocol:** latest existing entry is **DEV-055**; new ones start at **DEV-056**. If any
track deviates from ADR-015, log it, mark the touched line `[DEVIATED - see DEVIATIONS.md DEV-NNN]`,
and add the ADR-015 pointer.

---

## Parallelization Guide

```
Track 0 (read-only confirm) ─┐
                             ├─→ Track B (AnswerComposer, TDD) ──┐
Track A (5 design decisions) ┘                                   ├─→ Track D (QueryService reorder + `conflictsInProse` field, TDD) ─→ Track E (template + controller tests) ─→ Track G (manual smoke)
                             ├─→ Track C (SqlQueryHandler, TDD) ─┘
                             └─→ (Track F traceability — any time after B/C/D/E land)
```

- **Track 0 + Track A start immediately, in parallel** — 0 is read-only confirmation, A is five
  decisions on paper.
- **Tracks B and C depend on A** and are mutually independent (new `AnswerComposer` file vs.
  `SqlQueryHandler.formatAnswer` edit — disjoint files).
- **Track D depends on B + C** (needs the composer to call and column-named material to pass).
- **Track E depends on D** (D both *adds* and writes the `conflictsInProse` field; E only renders it
  in the template + controller tests).
- **Track F (traceability docs)** can land any time once the behaviour it documents exists.
- **Track G is last** — manual browser smoke needs everything wired and the app runnable.

---

## Track 0 — Pre-flight confirms (read-only, no production code)

_Purpose:_ corroborate the beans, wiring pattern, field map, and template touch-points the change
builds on. Write findings to a scratch note; log any contradiction as a DEV.

- [x] **0.1** Confirm `synthesisModel` bean exists at temp 0.3 (`config/LangChain4jConfig.kt:39`)
      and that `RagAgent` binds to it via `@AiService(wiringMode = EXPLICIT, chatModel =
      "synthesisModel")` (`ai/RagAgent.kt:16`). `AnswerComposer` copies this exact pattern — **no
      new bean.**
- [x] **0.2** Confirm the `QueryResponse` field map (`domain/dto/QueryResponse.kt`): `answer:
      String`, `routeDecision: RouteDecision?`, `citations: List<Citation>`, `conflicts:
      List<ConflictEntry>`, `sqlGenerated: String?`, `serviceError: Boolean = false`. Track E adds
      `conflictsInProse: Boolean = false`.
- [x] **0.3** Confirm `QueryService.handle()` is `route → dispatch → enrich()` (`service/
      QueryService.kt:33`), that `enrich()` (`:69`) runs `conflictProbe.extract` →
      `conflictLookup.find` → `conflictSynthesizer.synthesize` and copies only `conflicts[]`, and
      that `handleSql` does the SQL-empty → RAG fallback (`:92`). Track D restructures the
      `enrich()`→compose flow; `handleSql`'s SQL-empty → RAG fallback is unchanged and still fires
      before composition.
- [x] **0.4** Confirm `ConflictLookup.find(subject, claimType): List<ConflictClaim>`
      (`conflict/ConflictLookup.kt:23`) and that `ConflictSynthesizer.synthesize(claims):
      List<ConflictEntry>` is deterministic (`ai/ConflictSynthesizer.kt`, DEV-051). Both stay.
- [x] **0.5** Confirm the template's current conflict box (`resources/templates/index.html:46-54`,
      "Sources disagree") and that the citations `<ol>` (`:38`) is already a numbered list. Track E
      makes the conflict box fallback-only and keeps the citations list as the unified References.
- [x] **0.6** Confirm the test patterns to mirror: `QueryServiceTest` (all `@AiService`/handlers
      mockk'd), `SqlQueryHandlerTest`, and `QueryControllerIntegrationTest`/`WebControllerTest`
      (`@MockkBean QueryService`, DEV-055).

---

## Track A — Design decisions (on paper, no production code)

_Purpose:_ pin five choices so B/C/D can proceed without blocking. Record each in the scratch note;
none is a deviation (new-code design) unless it contradicts ADR-015.

- [x] **A1 — `ComposedAnswer` DTO shape.** New `domain/dto/ComposedAnswer.kt` = `data class
      ComposedAnswer(val answer: String, val citations: List<Citation>)`. Reuses the existing
      `Citation` type (`author, work, passageRef, stance?`) so the composer's references match the
      citation shape the template already renders.
- [x] **A2 — `conflictsInProse` default.** Add `conflictsInProse: Boolean = false` to
      `QueryResponse` (default `false` so every existing construction site — handlers, the
      `serviceError` branch — compiles unchanged and defaults to the safe "not woven" state).
- [x] **A3 — `material` serialization + where it's built.** Decision: `QueryService` builds
      `material` **uniformly from the draft `QueryResponse`** = the draft `answer` text plus its
      `citations` rendered as labelled source lines (so RAG/MIXED prose keeps its provenance and the
      composer can re-map to `[n]`). The only handler change needed is **SQL**: `formatAnswer` must
      emit **column-named** rows (`name=Zeus, type=olympian, generation=1`), not the value-only join,
      so the composer has field context (Track C). Do **not** build a separate per-route material
      path.
- [x] **A4 — `conflicts` input rendering.** The `List<ConflictClaim>` fetched by the probe/lookup
      helper is rendered for the composer as attributed claim lines (author, work, passageRef,
      claimValue), or the **literal string `none`** when empty. Decide the exact line format and that
      `none` is passed (not an empty string) so the prompt reads unambiguously. Caveat: RAG's
      conflict-aware backstop (`RagAgent.kt:40`) may already have woven an unstructured disagreement
      into the draft prose (now part of `material`); if the same disagreement is also a structured
      `conflicts` row, B3's system prompt must avoid narrating it twice (dedup is on citations, not
      content).
- [x] **A5 — Unified citation rule.** The composer returns `citations` = the **deduped union of
      answer sources and conflict sources, ordered by first appearance**, such that inline marker
      `[n]` indexes `citations[n-1]`. Hold the composer to `RagAgent`'s citation discipline: use only
      provided material, copy `author`/`work`/`passageRef`/`stance` verbatim, never invent a source,
      every `[n]` has a matching reference and vice versa.

---

## Track B — `AnswerComposer.kt` (TDD)

_Depends on: A1, A5._ New files `ai/AnswerComposer.kt` + `domain/dto/ComposedAnswer.kt`.

- [x] **B1 — Test first.** `AnswerComposerTest` with the model **mocked** (no live LLM per
      TECH_GUARDRAILS): assert the interface returns a `ComposedAnswer` and that the mapping into it
      is faithful. (Prompt-fidelity behaviour is exercised end-to-end in Track G's manual smoke, not
      by a live unit test.)
- [x] **B2 — `ComposedAnswer` DTO** per A1.
- [x] **B3 — `AnswerComposer` `@AiService` interface** —
      `@AiService(wiringMode = EXPLICIT, chatModel = "synthesisModel")` (DEV-046), method
      `compose(question, material, conflicts): ComposedAnswer` with `@V` params + a `@SystemMessage`.
      The system prompt: rewrite `material` into one fluent answer; weave each conflict version into
      the prose **attributed, without picking a winner**; emit inline `[n]` markers; return JSON
      `{"answer": "...", "citations": [{"author","work","passageRef","stance"}]}`; enforce A5's
      citation discipline (verbatim metadata, no invented sources, `[n]` ⇄ reference bijection).
- [x] **B4** Confirm the interface is provider-neutral (no Anthropic/OpenAI import) — only the
      `synthesisModel` bean name ties it to a provider, same as `RagAgent`. Copy only `RagAgent`'s
      `chatModel` + EXPLICIT wiring — **omit** `retrievalAugmentor` (there is no augmentor bean for
      the composer; its multi-param `@V` signature also differs from `RagAgent`'s single unannotated
      param).
- [x] **B5** Run `:core-api:test` — `AnswerComposerTest` green.

---

## Track C — `SqlQueryHandler.formatAnswer` column-named material (TDD)

_Depends on: A3._ Edit `handler/SqlQueryHandler.kt`.

- [x] **C1 — Test first.** Update `SqlQueryHandlerTest` to assert `formatAnswer` emits column-named
      pairs (e.g. `name=Zeus, type=olympian, generation=1`), not the value-only join. Keep the
      existing empty-result / aggregate-zero cases passing (`EMPTY_RESULT_ANSWER` unchanged — the
      SQL-empty → RAG fallback still fires before composition).
- [x] **C2 — Change `formatAnswer`** (`SqlQueryHandler.kt:65`) to serialize each row as
      `key=value` pairs joined per row, rows joined by `; `. This value becomes the SQL route's
      `material`; the composer produces the user-facing prose.
- [x] **C3** Confirm `MixedQueryHandler` needs no change — its `answer` is already RAG prose;
      `QueryService` renders its material from `answer` + `citations` (A3).
- [x] **C4** Run `:core-api:test` — `SqlQueryHandlerTest` green.

---

## Track D — `QueryService` pipeline reorder (TDD)

_Depends on: B + C._ Edit `service/QueryService.kt` (inject `AnswerComposer`) and
`domain/dto/QueryResponse.kt` (add the `conflictsInProse` field **here, not in Track E** — D3's
`draft.copy(...)` and the D1 assertions reference it).

- [x] **D0 — Add the field first.** Add `conflictsInProse: Boolean = false` to `QueryResponse` (A2)
      *before* the reorder — D3's `draft.copy(...)` and the D1 tests won't compile without it. The
      `false` default keeps every other construction site compiling; Track E only renders it.
- [x] **D1 — Test first.** Extend `QueryServiceTest` (add an `AnswerComposer` mockk):
  - [x] **D1.1** A normal route ⇒ `answer`/`citations` come from the composer's `ComposedAnswer`,
        and `conflictsInProse = true` when claims were present and woven.
  - [x] **D1.2** A conflict-shaped question ⇒ composer received the claims and the result carries
        both the woven `answer` **and** a populated `conflicts[]` (via `ConflictSynthesizer`).
  - [x] **D1.3** **Composer throws** ⇒ `QueryService` returns the **pre-composition draft
        unchanged** (draft `answer`/`citations`), `conflicts[]` still populated, `conflictsInProse =
        false`.
  - [x] **D1.4** **`serviceError` draft** ⇒ composer is **not** called; `answer`/`citations`
        unchanged, but `conflicts[]` is still populated via `synthesize(claims)` and
        `conflictsInProse = false` (per D3 — the draft object is *not* literally untouched).
  - [x] **D1.5** Existing pre-composition tests still hold (probe defaults to the `none` sentinel ⇒
        no claims ⇒ composer still runs on the draft with `conflicts = none`).
- [x] **D2 — Refactor `enrich()` → a claims helper** that *returns* `List<ConflictClaim>` (probe →
      `conflictLookup.find`; `none`/empty ⇒ empty list), instead of copying `conflicts[]` onto the
      answer.
- [x] **D3 — New composition step in `handle()`:** after `dispatch` (DRAFT) and the claims helper
      (CLAIMS): if `draft.serviceError` → return draft with `conflicts = synthesize(claims)` and
      `conflictsInProse = false`; else build `material` from the draft (A3), call
      `answerComposer.compose(question, material, renderConflicts(claims))` **wrapped in try/catch**.
      Success ⇒ `draft.copy(answer = composed.answer, citations = composed.citations, conflicts =
      synthesize(claims), conflictsInProse = claims.isNotEmpty())`. Any exception ⇒ log + return the
      draft with `conflicts = synthesize(claims)` and `conflictsInProse = false`.
      **Note (behavior change):** the claims helper runs *before* the `serviceError` branch, so the
      `ConflictProbe` LLM call now fires on `serviceError` drafts too — the current `enrich()`
      (`QueryService.kt:70`) early-returns before the probe. Accepted deliberately so `serviceError`
      responses still carry `conflicts[]` (ADR-015 §3); budget this probe call alongside the composer
      call noted above.
- [x] **D4** Keep `conflicts[]` present (possibly empty) in **all** branches via `ConflictSynthesizer` (API
      consumers + fallback box). `ConflictSynthesizer` / `ConflictLookup` / `ConflictProbe`
      signatures unchanged.
- [x] **D5** Run `:core-api:test` — `QueryServiceTest` green.

---

## Track E — `QueryResponse.conflictsInProse` + presentation

_Depends on: D._ Edit `domain/dto/QueryResponse.kt`, `resources/templates/index.html`, and the
controller/web tests.

- [x] **E1** Add `conflictsInProse: Boolean = false` to `QueryResponse` (A2) — default keeps every
      other construction site compiling.
- [x] **E2 — Template (`index.html`).** Keep the numbered citations `<ol>` as the single unified
      **References** list (now carrying the composer's unified citations; the answer prose already
      contains the inline `[n]`). Gate the "Sources disagree" box (`:46-54`) on
      `th:if="${!response.conflictsInProse && !response.conflicts.isEmpty()}"` — it renders **only**
      in the fallback case, so conflict information is never lost and never duplicated. Note: this box
      sits inside the template's `th:unless="${response.serviceError}"` block (`:35-60`), so on a
      `serviceError` draft `conflicts[]` is preserved for API/JSON consumers only — the web box is
      intentionally suppressed there, not shown.
- [x] **E3 — Controller/web tests.** Update `QueryControllerIntegrationTest` / `WebControllerTest`
      (`@MockkBean QueryService`, DEV-055) for the unified shape: `answer` carries `[n]`,
      `citations` is the unified list, `conflictsInProse` is present in the JSON, and the web box
      shows only when `conflictsInProse == false`.
- [x] **E4** Run `:core-api:test` — all green.

---

## Track F — Traceability (ADR-015 Follow-ups)

_Depends on: the behaviour above existing._ Per the deviation protocol + ADR-015 Follow-ups.

- [ ] **F1** Log **DEV-056** in `docs/DEVIATIONS.md` (append-only) cross-referencing ADR-015:
      Stage/Original Plan/What Changed/Reason/Impact/Date. Note it supersedes ADR-007 §5's prose
      presentation and closes the user-facing half of DEV-053.
- [ ] **F2** Annotate `docs/adr/adr-007-conflict-detection-and-surfacing.md` §5 as **"Amended by
      ADR-015"** (presentation only; data model unchanged).
- [ ] **F3** Mark affected checklist lines `[DEVIATED - see DEVIATIONS.md DEV-056]` where the
      implementation diverged from ADR-015, and update the `TODO.md` Post-MVP entry's boxes.

---

## Track G — Manual browser smoke (last)

_Depends on: B–E wired, app runnable (`docker-compose` DB up, seeded)._

- [ ] **G1** Submit a **DATA/SQL** gold question — `answer` is now prose (not a column dump), with
      inline `[n]` and a single numbered References list; the collapsible SQL block still shows the
      generated SQL.
- [ ] **G2** Submit a **FACT/RAG** and a **MIXED** question — same uniform shape (prose + `[n]` +
      unified References).
- [ ] **G3** Submit a **conflict-shaped** question (e.g. "Who were Aphrodite's parents?") — each
      attributed version is **woven into the prose**, no winner picked; the separate "Sources
      disagree" box is **absent** (`conflictsInProse = true`); `conflicts[]` still present in the
      JSON.
- [ ] **G4** Force the **fallback**: a `serviceError` question (one of Q9/Q11/Q12, still
      broken per DEV-054) renders the error banner unchanged; and a simulated composer failure (if
      practical) shows the pre-composition draft **plus** the legacy "Sources disagree" box
      (`conflictsInProse = false`) — confirming no conflict info is lost.

---

## Definition of Done (roll-up)

- [ ] `AnswerComposer.kt` (`@AiService`, `synthesisModel`, EXPLICIT wiring) + `ComposedAnswer` DTO;
      no new bean, no new provider surface.
- [ ] `SqlQueryHandler.formatAnswer` emits column-named material.
- [ ] `QueryService` runs `route → dispatch (DRAFT) → claims → answerComposer.compose (FINAL)`,
      wrapped; fallback to the draft on composer failure / `serviceError`, `conflicts[]` always
      present (possibly empty).
- [ ] `QueryResponse.conflictsInProse` added; template renders one unified References list on all
      routes and the legacy conflict box only in the fallback case.
- [ ] `QueryServiceTest` (uniform composition + `conflictsInProse` + fallback), `SqlQueryHandlerTest`
      (column-named), and controller/web tests updated; `:core-api:test` fully green.
- [ ] DEV-056 logged; ADR-007 §5 annotated "Amended by ADR-015"; manual gold-question smoke passes.
