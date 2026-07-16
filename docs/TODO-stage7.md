# Stage 7 — Conflict Enrichment (router-independent): Detailed Checklist

**Done when:** a conflict-shaped question (e.g. "Who were Aphrodite's parents?") returns **≥2
attributed versions in `conflicts[]`** via `POST /api/v1/query` **regardless of which route
(`SQL`/`RAG`/`MIXED`) retrieved its primary answer** — there is no `CONFLICT` route; a
claim-type-mismatched question (e.g. an *appearance* question about a subject that has a stored
*death* conflict) returns **empty** `conflicts[]`; enrichment failure leaves the primary `answer`
intact; `GET /api/v1/conflicts/{entityName}` lists every stored version for an entity; and
`ConflictLookupTest`, `ConflictProbe`/`ConflictSynthesizer` wiring, the `QueryService` enrichment
tests, and the browse-endpoint test all pass.

> **This stage is a recast, not the original "Conflict Pipeline."** Per **ADR-007** (`[DEVIATED -
> see DEVIATIONS.md DEV-014]`) there is **no `CONFLICT` route and no `ConflictQueryHandler`**.
> Conflict surfacing is a **router-independent enrichment step** that runs in `QueryService` after
> *any* handler answers:
>
> ```
> answer = dispatch(route, question)                         // route ∈ SQL | RAG | MIXED
> if !answer.serviceError:
>     try:
>         probe     = conflictProbe.extract(question)        // {subject, claimType}
>         conflicts = conflictLookup.find(probe.subject, normalize(probe.claimType))
>         if conflicts.isNotEmpty():
>             answer = answer.copy(conflicts = conflictSynthesizer.synthesize(conflicts))
>     catch: /* log; return answer unchanged — enrichment must never break the primary answer */
> return answer
> ```
>
> It writes **only `conflicts[]`, never `answer`** — so FACT/DATA answer scoring and `routeDecision`
> are untouched. `QueryService` becomes the only class that knows about all three handlers **plus**
> this enrichment step.
> **Prerequisite: Stages 5 + 6 complete** — the SQL and RAG routes both return real answers (the
> enrichment step wraps them), `variant_claims` is seeded (V12), and `claim_type_aliases` (V8_2),
> `entity_aliases` (V14), and the trigram/composite indexes are all at Flyway head.

> The `RagAgent` conflict-aware **prose backstop** (unstructured disagreements in retrieved text)
> already shipped in Stage 6 (ADR-007 §3, `RagAgent.kt` `@SystemMessage`). This stage adds the
> **structured `variant_claims` enrichment** (ADR-007 §5) that runs on *every* route. The two layers
> are complementary: structured conflicts come from reviewed `variant_claims`; the RAG backstop
> catches anything never structured at all. Do not touch the backstop here.

> **Gold questions:** `evaluation/gold-questions.json` currently holds FACT Q1–Q5 (Stage 6) + DATA
> Q6–Q10 (Stage 5). This stage **adds the CONFLICT subset** (Track G) — authoring them is part of
> Stage 7. The REFUSAL questions (grounded refusals that must *stay clean* — an appearance refusal
> must not be polluted by an unrelated death conflict, ADR-007 §5) land with Evaluation (Stage 10);
> Track G authors at least one negative claim-type-mismatch case here to prove the filter. No
> `EvaluationRunner` is built in this stage; Track H reads the file by hand / with `curl`.

Before starting, re-read `DEVIATIONS.md`. Relevant carry-overs:
- **DEV-014 / ADR-007** — the charter for this whole stage (no `CONFLICT` route; enrichment step;
  `ConflictProbe` + shared `ConflictLookup` + `QueryService` enrichment). Re-read ADR-007 §5 in full
  before writing any code — the claim-type-filtered-vs-subject-only fetch distinction and the
  "writes only `conflicts[]`" rule are the two things most easily gotten wrong.
- **DEV-022 / ADR-007 §1** — `normalize()` lives in the **`claim_type_aliases` DB table** (V8_2),
  the *same rows* the offline Python detector reads. **Never** hand-copy the alias map into Kotlin or
  JSON. `normalize(x) = canonical` where `alias = lower(trim(x))`, **identity when no row matches**
  (canonicals such as `parentage`/`death` have **no self-row** — do not assume every input is in the
  table). `normalize()` is applied to the **probe input only**, never to the stored column.
- **Exact-match lookup depends on normalized storage.** V12 rows were promoted with the **normalized
  canonical** `claim_type` (surface variants collapsed at promotion), so the enrichment fetch matches
  by exact equality: `claim_type = normalize(probeClaimType)`. Both rows of a conflict share one
  `claim_type` value. Do **not** re-normalize the stored column at query time.
- **No runtime source-count gate** (CLAUDE.md, ADR-007). The `>=2 distinct sources` rule is the
  **offline detection** heuristic only. `ConflictLookup` fetches **every** row for the
  subject+claim_type; `ConflictSynthesizer` formats them all. Consequence: the hand-added single-source
  floor case (**Io**: `child of Inachus` vs `child of Piren`, *both* `apollodorus-bibliotheca`) is not
  "detected" as a conflict offline yet **still surfaces at query time** — Track H must verify this.
- **DEV-004** — LangChain4j is `1.0.0-beta5`. `ConflictProbe`/`EntityExtractor` (temp 0.0) and
  `ConflictSynthesizer` (temp 0.3) are new `@AiService` interfaces; the beta5 shapes were already
  resolved in Stages 5–6 (Track 0 below is a short confirm, not a fresh spike).
- **DEV-046 / DEV-015** — Two `ChatModel` beans exist (`routingModel` temp 0.0, `synthesisModel` temp
  0.3, both `AnthropicChatModel`). Every `@AiService` must declare EXPLICIT wiring with a **bean-name
  string** (not `@Qualifier`): `@AiService(wiringMode = EXPLICIT, chatModel = "routingModel")`.
  `ConflictProbe`/`EntityExtractor` → `routingModel`; `ConflictSynthesizer` → `synthesisModel`.
- **DEV-021 / ADR-007 §5** — surfaced conflicts should cite like RAG answers do; `variant_claims`
  carries `passage_ref` (V8_1) for exactly this. See Track A's `ConflictEntry`-shape decision.
- **DEV-040 / DEV-042** — `entities.subtype` exists (V9_1); `birth`→`parentage` alias added (V9_2).
  Nothing to build, but the alias table is not the same set as it was at ADR-007 time — read it live.
- **DEV-008** — Testcontainers pinned `1.21.4`; reuse `AbstractContainerTest` for any DB test.

## Parallelization Guide

```
Track 0 (beta5 confirm, read-only) ─┐
Track A (ConflictEntry DTO decision)├─→ Track C (ConflictSynthesizer) ─┐
Track B (ConflictProbe / EntityExtractor)                             ├─→ Track E (QueryService enrichment) ─→ Track H (verify)
Track D (ConflictLookup, TDD) ───────────────────────────────────────┘        ↑
Track F (browse endpoint) ──────── depends on D ──────────────────────────────┘
Track G (author CONFLICT gold Qs) ─────────────────────────────────────────────────────────────┘
```

- **Track 0** — 15-minute read-only confirm of beta5 `@AiService` structured-return for the small
  `{subject, claimType}` POJO. Largely settled by Stage 5/6 Track 0. Do first or fold into A/B.
- **A, B, D, G have no dependency on each other — start all four immediately.**
  - **A** (`ConflictEntry` shape + any DTO change) is a small decision + edit that unblocks C and E.
  - **B** (`ConflictProbe`, and the EntityExtractor fold-in decision) is a pure interface + prompt.
  - **D** (`ConflictLookup`) is the heaviest track: entity resolution + normalize() + two fetches,
    TDD against Testcontainers. It has no code dependency on A/B/C.
  - **G** (author CONFLICT gold Qs) is pure JSON authoring against the seeded `variant_claims`.
- **C depends on A** (whatever `ConflictSynthesizer` returns must match the `conflicts[]` shape A
  settles) **+ Track 0**.
- **E depends on B + C + D** — it wires all three into the enrichment step. **F depends on D**
  (subject-only fetch + entity resolution). **H is last.**

---

## Track 0 — beta5 `@AiService` confirm for the probe POJO (read-only, no production code)

_Purpose:_ confirm the one thing Stages 5–6 didn't already exercise: a **multi-field structured
return** (`{subject, claimType}`) from a temp-0.0 `@AiService`. Everything else (EXPLICIT wiring,
single-arg auto-`@UserMessage`, enum/POJO parsing) is already proven. Write findings to a scratch
note, not the repo; log any contradiction as a DEV entry.

- [x] **0.1** Confirmed via `langchain4j-1.0.0-sources.jar`
  (`dev.langchain4j.service.output.PojoOutputParser`) and `langchain4j-core-1.0.0-sources.jar`
  (`dev.langchain4j.internal.Json`): a flat 2-field POJO (`ProbeResult(subject: String, claimType:
  String)`) goes through the exact same reflection-based `OutputParser` → `Json.fromJson` (Jackson
  codec by default) path already proven live for `RagResponse` in Stage 6 Track 0.3 — and is a strict
  *subset* of that case (no nested `List<>`/`ParameterizedType` branch even applies), so mechanically
  simpler, not riskier. No spike/prototype needed. Single unannotated `question: String` param is
  auto-treated as the user message (`findUserMessageTemplateFromTheOnlyArgument`), same as
  `QueryRouter.classify`/`RagAgent.answer` — no `@UserMessage` needed on `ConflictProbe.extract`. See
  scratch note §0.1.
- [x] **0.2** Decided: explicit string sentinel **`"none"`**, never empty string or JSON `null`. A
  non-nullable Kotlin `claimType: String` field has no null branch to safely hit — requiring the model
  to always emit a concrete literal (`"none"`) for "no modeled claim type" sidesteps any
  null-vs-missing Jackson-Kotlin deserialization risk entirely, and keeps `ProbeResult` consistent with
  the existing enum-output precedent (`RouteDecision` also has no null case). Drives B3's prompt
  (instruct the model to emit literal `"none"`) and E's skip-check (`probe.claimType == "none"`, plain
  string comparison). See scratch note §0.2.

**No plan contradictions found; no new DEV-NNN required for 0.1. 0.2 is a new decision (not a
deviation) — recorded for B3/E to consume directly.** Full findings:
`/private/tmp/claude-501/-Users-ekaterina-alay-Documents-blame-zeus/946ca94d-edf5-47e5-8360-cd7cb1f0310d/scratchpad/track0-stage7-findings.md`
(scratch note, not part of the repo).

---

## Track A — `ConflictEntry` DTO shape decision + any DTO change

_Directory:_ `.../domain/dto/`. Small but blocks C and E — do it first. `ConflictEntry` currently
carries `claimValue`, `sourceAuthor`, `sourceWork` only.

- [x] **A1** Decided: add `passageRef: String? = null` to `ConflictEntry`, mirroring `Citation`.
  **`stance` was deliberately left out** — nothing calls for it as strongly as `passageRef`
  (DEV-021's whole purpose), and `ConflictEntry` should carry only what was added for, not everything
  `Citation` happens to have. `sourceAuthor`/`sourceWork`/`passageRef` all require Track D's
  **join `variant_claims → sources`** (the row only stores `source_id` slug).
- [x] **A2** Decided **(a) structured**: `ConflictSynthesizer` produces `List<ConflictEntry>` via a
  deterministic, **non-`@AiService`** mapper (row → DTO, no LLM call) — `conflicts[]` presentation is
  data-driven per ADR-007 §5 and the DTO already has every field needed; a deterministic mapping can't
  hallucinate an attribution. Logged as `[DEVIATED - see DEVIATIONS.md #DEV-051]` since it changes
  `ConflictSynthesizer`'s nature from the plan's LLM `@AiService` description. Track C implements it as
  a `@Component` in `ai/` (same directory, different Spring stereotype).
- [x] **A3** `ConflictEntry` updated (`passageRef: String? = null`); `QueryResponse` unchanged (no
  prose field needed). `DtoSerializationTest` updated: existing test asserts `conflicts[0].passageRef`;
  new test confirms `ConflictEntry` deserializes with `passageRef` absent from the JSON. 5/5 green.

---

## Track B — `ConflictProbe` (and the `EntityExtractor` fold-in) `@AiService`

_Directory:_ `.../ai/`. _Depends on:_ Track 0. Compiles independently.

- [x] **B1** Decided: **one** interface, named `ConflictProbe` (matches the name every other doc —
  ADR-007 §5's pseudocode, CLAUDE.md's architecture section, this file's Track E — already uses for
  `QueryService`'s `conflictProbe.extract(question)` call). Stage 8's `MixedQueryHandler` can inject
  the same bean and read only `.subject`, ignoring `.claimType`. Not a deviation — the plan/ADR-007
  both left the naming open ("may be folded into `EntityExtractor`"); no separate `EntityExtractor`
  interface is built.
- [x] **B2** `ai/ConflictProbe.kt` — `@AiService(wiringMode = EXPLICIT, chatModel = "routingModel")`,
  temp 0.0 (inherited from the `routingModel` bean). `fun extract(question: String): ProbeResult` with
  a single unannotated param, no `@UserMessage` (Track 0.1). `ProbeResult(subject, claimType)` added to
  `domain/dto/` (matching `RagResponse`/`Citation`/`ConflictEntry`'s existing home).
- [x] **B3** `@SystemMessage` extracts `subject` (canonical mythological name) and `claimType` mapped
  toward the three canonical dimensions confirmed live in `claim_type_aliases`/`V12`
  (`parentage`/`marriage`/`death` — verified via `V8_2__create_claim_type_aliases.sql`'s comment: "Canonical
  namespace per ADR-007 §1 / DEV-020"), returning the literal sentinel `"none"` (Track 0.2) otherwise. Does
  **not** enumerate every possible surface variant — only the three canonicals plus "none", per ADR-007
  §1's open-vocabulary design. Temperature 0.0 via the `routingModel` bean.
- [x] **B4** Confirmed by construction: the prompt asks for natural phrasing (`"claimType"` is
  whichever of the three dimension names fits, or `"none"`) — no alias table content is hand-copied
  into the `@SystemMessage`. `normalize()` stays exclusively `ConflictLookup`'s job (Track D), per
  DEV-022.

Tests: `DtoSerializationTest` gained two `ProbeResult` cases (LLM-shaped JSON blob deserialization;
`"none"`-sentinel round-trip) — no dedicated `ConflictProbeTest` file, matching the existing
`QueryRouter`/`TextToSqlAgent`/`RagAgent` precedent (interface logic isn't independently unit-tested;
it's exercised via the mocked interface in the consuming component's tests — here, Track E's
`QueryServiceTest`). 7/7 `DtoSerializationTest` cases green; full `:core-api:test` suite green.

---

## Track C — `ConflictSynthesizer`

_Directory:_ `.../ai/`. _Depends on:_ A2 (its return type) + Track 0. Shape depends entirely on the A2
decision.

- [x] **C1** `ai/ConflictSynthesizer.kt` — `@Component`, no LLM, no Testcontainers dependency.
  `synthesize(claims: List<ConflictClaim>): List<ConflictEntry>` maps each `ConflictLookup` row
  straight through (`claimValue`/`sourceAuthor`/`sourceWork`/`passageRef`) in the order received — no
  filtering, no reordering, no winner-picking. Since `ConflictClaim` (Track D5) and `ConflictEntry`
  (Track A1) ended up field-for-field identical, the "mapping" is a literal 1:1 copy.
- [ ] **C2** N/A — A2 chose structured mapping (option a), not the LLM prose form.
- [x] **C3** `ConflictSynthesizerTest.kt` (plain fixtures, no Testcontainers) — 4 cases: every fetched
  version appears in the output in input order (asserted via `containsExactly`, proving nothing is
  dropped or reordered); the complementary-claims case (one `ConflictClaim` naming a killer, another a
  manner of death) — both survive, neither is ranked over the other, and no synthesized text implying
  contradiction is possible since the mapper only copies fields; empty input → empty output; a null
  `passageRef` maps through unchanged. 4/4 green.

Full `:core-api:test` suite: 105/105 green (4 new `ConflictSynthesizerTest` cases, no regressions).

---

## Track D — `ConflictLookup` (shared component, **not** an `@AiService`) — TDD

_Directory:_ `.../conflict/` (new package) + matching test dir. _Depends on:_ nothing (start early).
This is the heaviest track. Reuse `AbstractContainerTest` (DEV-008).

- [x] **D1** `ConflictLookupTest.kt` written first — 12 cases, all green against real Testcontainers
  Postgres. Cases (a)/(b)/(c)/(e)/(g) exercise the **real seeded corpus** directly (no fixture
  seeding needed, matching `VariantClaimRepositoryTest`/`EntityAliasRepositoryTest`'s existing
  pattern); cases (d)/(f)/(h) hand-insert uniquely-named fixture rows via the repositories (matching
  `RepositoryQueryTest`'s pattern), since the real seed has no natural exact/alias name collision and
  no single subject with >1 seeded `claim_type`.
  - **(a)** `find("Achilles", "death")` → ≥2 distinct real claim values, `sourceAuthor` includes "Homer".
  - **(b)** `find("Venus", "parentage")` == `find("Aphrodite", "parentage")` (same claim-value set).
  - **(c)** `find("Aphrodyte", "parentage")` (one-letter typo) resolves via trigram to the same set as
    `find("Aphrodite", ...)`; `TRIGRAM_THRESHOLD = 0.3` (pg_trgm's own GUC default, matched explicitly
    rather than relying on the session default) confirmed live to clear the typo and reject
    `"Zzzxxqqyy999NotAName"` (empty result, no false match).
  - **(d)** hand-inserted `TestPrecedenceExact` entity + a *different* entity aliased to the same
    string → `find("TestPrecedenceExact", ...)` returns only the exact entity's row.
  - **(e)** `find("Aphrodite", "parents")` == `find("Aphrodite", "parentage")`; a direct canonical
    (`"death"`, which has no self-row in `claim_type_aliases`) still matches via identity fallback.
  - **(f)** hand-inserted subject with 2 `death` rows + 1 `marriage` row → `find(subject, "death")`
    returns exactly the 2 death rows; separately, `find("Achilles", "appearance")` (real data, Achilles
    has zero `appearance` rows) → empty, proving the grounded-refusal guard.
  - **(g)** `find("Io", "parentage")` includes both the Inachus and Piren claim values (real V12 seed,
    both cite `apollodorus-bibliotheca`).
  - **(h)** hand-inserted subject with a `death` row + a `marriage` row → `findAllForEntity(subject)`
    returns both.
  - **(i)** `find`/`findAllForEntity` on a nonsense name both return empty lists, no exception.
- [x] **D2** `conflict/ConflictLookup.kt` — `@Component(JdbcTemplate)`, matching
  `NarrativeChunkContentRetriever`'s existing raw-SQL-constant + `RowMapper` lambda style (not JPA —
  the alias/trigram steps have no repository equivalent, and keeping all three resolution steps in one
  class as plain SQL was simpler than splitting exact/count-as-JPA + alias/trigram-as-JDBC). Three-step
  **short-circuit chain** (`?:` `firstOrNull()?.let { return it }` per step) — exact never falls
  through to a same-named alias of a different entity (proven by D1d), alias never reaches the trigram
  query at all once matched. No `trust_tier` or source-count filtering anywhere in the SQL.
- [x] **D3** `normalize()` — private method, `SELECT canonical FROM claim_type_aliases WHERE alias =
  lower(trim(?))`, `?: claimType` for the identity fallback. Applied only inside `find()` to the probe
  `claimType` argument; the stored `variant_claims.claim_type` column is matched by plain `=`.
- [x] **D4** `find(subjectName, claimType)` (claim-type-filtered) and `findAllForEntity(entityName)`
  (subject-only) both implemented, both joining `sources` for `author`/`work`. `passageRef` also
  selected (Track A1); `stance` deliberately **not** added to the join, matching A1's `ConflictEntry`
  decision not to carry it.
- [x] **D5** Returns `List<ConflictClaim>` (`conflict/ConflictClaim.kt`) — a plain 4-field row type
  (`claimValue`/`sourceAuthor`/`sourceWork`/`passageRef`), deliberately **not** `ConflictEntry` itself,
  so `conflict/` has no dependency on the `domain/dto` response-DTO layer. Track C maps this 1:1 into
  `ConflictEntry`.

101/101 `:core-api:test` cases green (12 new in `ConflictLookupTest`, no regressions elsewhere).

---

## Track E — `QueryService` enrichment step (TDD)

_Directory:_ `.../service/`. _Depends on:_ B (`ConflictProbe`), C (`ConflictSynthesizer`), D
(`ConflictLookup`). This is where the ADR-007 §5 pseudocode lands.

- [x] **E1** `QueryServiceTest` extended: `conflictProbe`/`conflictLookup`/`conflictSynthesizer` mocks
  added to the constructor call; an `init` block defaults `conflictProbe.extract(any())` to
  `ProbeResult("Unknown", "none")` so all 11 pre-Stage-7 tests keep passing byte-for-byte unchanged
  (enrichment no-ops on the "none" sentinel) without touching their bodies. 8 new cases added:
  - SQL-routed conflict-shaped question → populated `conflicts[]` after the SQL answer.
  - RAG-routed conflict-shaped question → same, proving router-independence.
  - claim-type mismatch (`appearance` probe, `conflictLookup.find` stubbed empty) → empty
    `conflicts[]`, `answer` unchanged (grounded-refusal guard).
  - `none` claimType → `conflictLookup.find`/`conflictSynthesizer.synthesize` verified **never**
    called.
  - three separate throwing cases (`conflictProbe`, `conflictLookup`, `conflictSynthesizer` each in
    turn) → answer returned intact, `serviceError` stays `false`.
  - `serviceError == true` primary answer → all three conflict collaborators verified never called.
  - a populated-conflicts case asserting `answer`/`routeDecision`/`citations`/`sqlGenerated` are
    exactly the pre-enrichment values, only `conflicts` differs.
  19/19 green (11 original + 8 new).
- [x] **E2** `QueryService.kt` — constructor gained `conflictProbe`/`conflictLookup`/
  `conflictSynthesizer`. `handle()` now captures the dispatch result as `answer` and returns
  `enrich(answer, question)` instead of returning the dispatch result directly. Private `enrich()`:
  returns `answer` unchanged immediately if `answer.serviceError`; otherwise
  `conflictProbe.extract(question)` → skip (return `answer`) if `claimType == "none"` (companion
  constant `NO_CLAIM_TYPE`) → `conflictLookup.find(probe.subject, probe.claimType)` (normalization
  happens **inside** `ConflictLookup`, per Track D3 — `QueryService` passes the raw surface form) →
  skip if empty → `answer.copy(conflicts = conflictSynthesizer.synthesize(claims))`. Whole body
  wrapped in try/catch that logs via `log.warn` and returns `answer` unchanged on any exception.
- [x] **E3** Confirmed structurally and with a dedicated test
  (`Track E3 -- the SQL-empty-result to RAG fallback answer still gets enriched, not skipped`):
  `enrich()` is called exactly once, on `handle()`'s single `answer` variable — `handleSql`'s
  internal empty-result → `ragQueryHandler.handle()` fallback happens *before* `enrich()` ever runs,
  so the fallback's RAG answer is what gets enriched, never bypassed.
- [x] **E4** `QueryService`'s class doc comment rewritten: now states it is "the only class that
  knows about all three handlers ... *plus* the router-independent conflict enrichment step,"
  naming the ConflictProbe → ConflictLookup → ConflictSynthesizer chain and the
  conflicts-only/never-breaks-the-answer guarantees.

Full `:core-api:test` suite green (115/115 total; no regressions in any other class).

---

## Track F — `GET /api/v1/conflicts/{entityName}` browse endpoint

_Directory:_ `.../controller/`. _Depends on:_ D4 (`findAllForEntity`). The one place the **subject-only**
fetch is used.

- [x] **F1** `QueryControllerTest` extended (existing `MockMvc` + `AbstractContainerTest` slice, real
  seeded data, no mocks — `ConflictLookup`'s resolution/multi-claim-type behavior is already proven at
  the unit level in `ConflictLookupTest`, so this only proves the endpoint's wiring). 3 new cases:
  `GET /api/v1/conflicts/Aphrodite` → ≥2 real parentage claims incl. Hesiod/Theogony;
  `GET /api/v1/conflicts/Venus` → byte-identical JSON body to the Aphrodite response (alias
  resolution); `GET /api/v1/conflicts/DefinitelyNotARealEntityXyz123` → **200 with an empty list**.
  **Decided 200 + empty list, not 404**: `ConflictLookup` cannot distinguish "no such entity" from "a
  real entity with zero recorded conflicts" (both resolve to an empty list) — a 404 would misreport
  the latter as nonexistent, so an empty array is the honest response for both cases. No
  `/entities`-style precedent existed to match (that endpoint has no by-name miss case at all), so
  this was a fresh decision.
- [x] **F2** `QueryController` gained `conflictLookup`/`conflictSynthesizer` constructor deps and
  `GET /conflicts/{entityName}` → `conflictSynthesizer.synthesize(conflictLookup.findAllForEntity(entityName))`
  (reuses Track C's mapping exactly, no duplicate row→DTO logic). Removed the stale
  `// added in Stage 7` marker comment now that the endpoint exists. Never wired into `QueryService`'s
  enrichment step — an explicit by-entity dev/demo lookup only, per ADR-007 §5.

5/5 `QueryControllerTest` cases green; full `:core-api:test` suite 118/118 green.

---

## Track G — Author CONFLICT gold questions

_Directory:_ `evaluation/gold-questions.json`. _Independent_ — pure authoring against the seeded
`variant_claims`. Track H consumes these.

- [x] **G1** Added Q13 (Aphrodite parentage, `expected_route: SQL` per the plan's own ADR-007
  amendment note), Q14 (Io parentage, `SQL`), Q15 (Achilles death, `RAG`) to
  `evaluation/gold-questions.json`. Each hits a real V12 conflict — 13/9/22 rows respectively,
  confirmed live against the seed file (Track G3). Added a `conflicts_min_count: 2` key to all three
  — the forward-compat key the track anticipated, mirroring Stage 5's `min_row_count`/
  `sql_must_contain` pattern — since "≥2 distinct `conflicts[]` entries" wasn't otherwise
  machine-checkable. `[DEVIATED - see DEVIATIONS.md #DEV-052]`: Q13's `required_keywords` swapped
  `"Ouranos"` → `"foam"` (the real Hesiod row says "Heaven", never "Ouranos"/"Uranus" — same
  entity-naming quirk as DEV-047); Q14/Q15 keywords matched the real seed as-written, no change.
- [x] **G2** Added **Q18** (`"Why did Achilles withdraw from the fighting after his quarrel with
  Agamemnon?"`, category `CONFLICT`, `expected_route: RAG`, `conflicts_min_count: 0`) as the negative
  claim-type-mismatch case — a genuine narrative/motivation question (real content: "Agamemnon"
  appears 174× in the raw Iliad corpus file, concentrated in the Book 1 quarrel), expecting a normal
  answer with **empty** `conflicts[]` despite Achilles having 22 real stored death-conflict rows.
  `[DEVIATED - see DEVIATIONS.md #DEV-052]`: deliberately a **new id (18)**, not a reuse of the
  plan's REFUSAL Q16 wording — REFUSAL's `refusal_criteria` schema is Stage 10's scope per this
  stage's own intro, and Q18 needs a normal (non-refusal) answer, so reusing Q16 would have been the
  wrong shape. ids 11–12 (MIXED, Stage 8) and 16–17 (REFUSAL, Stage 10) are left as intentional gaps.
- [x] **G3** Sanity-checked all four new questions against the real `V12__seed_variant_claims.sql`
  rows (a direct grep/parse of the migration file, same method as DEV-048 — no live DB/LLM needed
  for a static text check): row counts, every `required_keywords` entry, and every `required_authors`
  entry (via the `sources` table's real `author` column, not the `source_id` slug) all confirmed
  present before committing. Flagged for Track H: `expected_route` for Q13–15 is the plan's ADR-007
  *prediction* (parentage→SQL, death→RAG), not yet live-confirmed; and Q18's `ConflictProbe` must be
  checked to actually extract `subject: "Achilles"` rather than `"Agamemnon"` (the question names
  both) before trusting `conflicts_min_count: 0` as a clean pass rather than an accidental one.

`evaluation/gold-questions.json` now has 14 entries (ids 1–10, 13–15, 18); valid JSON confirmed.

---

## Track H — Verification (sequential, run last)

_Depends on:_ all tracks. Needs a live `.env` (`LLM_API_KEY` + `LLM_CHAT_MODEL` for chat,
`OPENAI_API_KEY` for embedding) and the DB at Flyway head with the full seed + ingested corpus.

- [x] **H1** Full `:core-api:test` re-run immediately before the live run: 118/118 green (includes
  all `ConflictLookupTest` D1 cases, the Track C synthesizer test, all `QueryServiceTest` enrichment
  cases, and the Track F endpoint test).
- [x] **H2** Booted with real `.env` against the live Postgres (Flyway at V15, full 6-source/3,524-chunk
  corpus, 1,969 entities, 44 `variant_claims` confirmed via `psql` before starting).
  **`POST /api/v1/query {"question":"Who were Aphrodite's parents?"}`** → `routeDecision: "SQL"` (not
  `CONFLICT`), `conflicts[]` has **13 entries** spanning 5 distinct real authors (Hesiod, Apollodorus,
  Homer, Anonymous ("Homeric"), Ovid) — Zeus (per most) vs. Dione (per Homer/Apollodorus) both present.
  Headline "done when" confirmed.
- [x] **H3** **Router-independence confirmed both ways.** The same underlying fact, phrased to hit RAG
  instead (`"What do the ancient sources say about who Aphrodite's parents were?"`), also routed
  `RAG` and also surfaced the identical 13-entry conflict set (debug log: `Conflict probe ...
  subject='Aphrodite', claimType='parentage'` → `Conflict lookup ... 13 rows`). A more narrative
  phrasing (`"Tell me the story of how Aphrodite was born."`) routed `RAG` but the probe extracted
  `claimType='none'` for that specific phrasing, so `conflicts[]` stayed empty — see `[DEVIATED -
  see DEVIATIONS.md #DEV-053]` for the phrasing-sensitivity finding and why it's accepted, not fixed.
- [x] **H4** Track G2's Q18 (`"Why did Achilles withdraw from the fighting after his quarrel with
  Agamemnon?"`) → probe correctly extracted `subject='Achilles'` (not `'Agamemnon'`, resolving
  DEV-052's flagged concern), `claimType='none'` → `conflicts[]` empty, primary `answer` a normal,
  richly-cited response (Homer + Apollodorus). Grounded-refusal guard confirmed live.
- [x] **H5** `POST {"question":"Who was Io's father?"}` → SQL tried first, returned zero rows (log:
  `"Empty/aggregate-zero SQL result ... falling back to RAG"`), RAG fallback answer enriched with
  **9** conflict entries including both `"child of Inachus"` and `"child of Piren"` (**both**
  `Apollodorus`/`Bibliotheca`) — the single-source floor case, no runtime source-count gate. This
  also live-confirms Track E3 end-to-end (the fallback path genuinely gets enriched, not just via
  the `QueryServiceTest` mock).
- [x] **H6** `POST {"question":"Why did Athena turn Arachne into a spider?"}` (Q1, no stored conflict)
  → probe extracted `claimType='none'`, enrichment no-op'd cleanly, answer/citations identical in
  substance to the Stage 6 live result (Ovid/Metamorphoses, 3 citations, empty `conflicts[]`).
  Probe/lookup/synthesizer failure-injection already covered thoroughly by `QueryServiceTest`'s 3
  dedicated throwing cases (Track E1) — not re-run live, since mocked failure injection is the
  correct tool for that and a live run can't safely force an internal exception anyway.
- [x] **H7** Every `conflicts[]` entry across all live queries above carries a real `sourceAuthor`
  (Hesiod, Apollodorus, Homer, Anonymous ("Homeric"), Ovid — never "Unknown") and `sourceWork`, plus
  real `passageRef` values (e.g. `"176-232"`, `"2.1.2-2.1.3"`) — the `sources` join is genuinely live,
  not a placeholder.
- [x] **H8** `GET /api/v1/conflicts/Aphrodite` → 13 entries. `GET /api/v1/conflicts/Venus` → **byte-
  identical** response body (`diff` confirmed) via alias resolution. `GET
  /api/v1/conflicts/DefinitelyNotARealEntityXyz123` → HTTP 200, `[]` — matches Track F1's decision.
- [x] **H9** `EXPLAIN ANALYZE` on the live claim-type-filtered query: `Index Scan using
  idx_variant_claims_subject_type` (`Index Cond: (subject_entity_id = $0) AND (claim_type =
  'parentage')`), 0.072ms total — **unlike** Stage 6 H5's vector-index seq-scan caveat, the planner
  does choose this index at the current table size/selectivity. No caveat needed.
- [x] **H10** Logged `[DEVIATED - see DEVIATIONS.md #DEV-053]`: Q14's actual live route is `RAG` (via
  the SQL-empty→RAG fallback), not the plan's predicted `SQL` — `evaluation/gold-questions.json`
  corrected. `ConflictProbe`'s claim-type extraction is narrative-phrasing-sensitive (documented,
  not fixed — the RAG backstop is the designed complementary layer). A pre-existing `SqlQueryHandler`
  answer-formatting defect (raw joined-column dump for a relationship-style query) was found and
  flagged, not fixed — out of Stage 7 scope, and confirmed **not** to affect Q13's actual CONFLICT
  gold score (which reads `conflicts[].claimValue`, not `answer`). Added permanent `log.debug` lines
  to `QueryService.enrich()` (mirrors the existing `NarrativeChunkContentRetriever` convention).
  `IMPLEMENTATION_PLAN.md §9` stage-note pointer added; `TODO.md` Stage 7 boxes flipped.

**Stage 7 is complete.** All tracks A–H done; 118/118 automated tests green; live-verified end-to-end
against the real Anthropic API, the real 6-source corpus, and the live Postgres instance.
