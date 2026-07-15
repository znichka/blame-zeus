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

- [ ] **B1** **Decide: fold into `EntityExtractor`, or a separate `ConflictProbe`?** ADR-007 §5 and
  plan §5 both allow either; folding keeps enrichment to **one LLM call**. Plan §5 lists a standalone
  `EntityExtractor` (temp 0.0, "extracts entity name from question") that **Stage 8's `MixedQueryHandler`
  also needs**. **Recommendation:** build **one** interface that returns `{subject, claimType}` and have
  Stage 8 read `.subject` from it — but name/shape it so Stage 8 isn't forced to also compute a
  claimType it doesn't use. Record the choice; it's a small forward-compat call, not a deviation.
- [ ] **B2** `ai/ConflictProbe.kt` (or `EntityExtractor.kt` per B1) `@AiService(wiringMode = EXPLICIT,
  chatModel = "routingModel")`, temp 0.0. `fun extract(question: String): ProbeResult` with a single
  unannotated param (Track 0.1). Add the `ProbeResult(subject, claimType)` DTO
  (`.ai` or `.domain.dto`).
- [ ] **B3** `@SystemMessage` design: extract the **subject entity** (a canonical mythological name —
  the thing the question is *about*) and the **claim type** the question probes, mapped toward the
  modeled dimensions (`parentage`, `marriage`, `death`, …). It must return the empty/`none` sentinel
  (Track 0.2) for `claimType` when the question maps to **no** modeled attribute — e.g. a pure "why did
  X happen" motivation question — so E skips the structured lookup and lets the RAG backstop cover it.
  Do **not** try to enumerate every claim type in the prompt (the vocabulary is open, ADR-007 §1); give
  the model the canonical dimensions plus "or `none`". Temperature 0.0 for determinism.
- [ ] **B4** Note: the probe's raw `claimType` is a **surface form** (the user's phrasing). `normalize()`
  is applied by `ConflictLookup`/`QueryService` against the DB alias table (DEV-022) — **not** in this
  prompt and **not** hand-mapped in Kotlin. The probe should emit natural phrasing; normalization is
  the DB's job.

---

## Track C — `ConflictSynthesizer`

_Directory:_ `.../ai/`. _Depends on:_ A2 (its return type) + Track 0. Shape depends entirely on the A2
decision.

- [ ] **C1** **If A2 chose structured mapping (recommended):** implement `ConflictSynthesizer` as a
  deterministic component that maps the `ConflictLookup` result rows → `List<ConflictEntry>`
  (`claimValue` from `variant_claims.claim_value`, `sourceAuthor`/`sourceWork` from the joined
  `sources`, `passageRef` from `variant_claims.passage_ref` if A1 added it). No LLM, no winner-picking
  — it just structures. Unit-testable with plain fixtures, no Testcontainers.
- [ ] **C2** **If A2 kept the LLM prose form:** `ai/ConflictSynthesizer.kt` `@AiService(wiringMode =
  EXPLICIT, chatModel = "synthesisModel")`, temp 0.3, `@SystemMessage` = "format each attributed
  version as `According to [Author], [Work]: [claim].`, present **all** versions, **never pick a
  winner**, never assert the versions contradict (they may be complementary — ADR-007 §1 death
  killer-vs-manner note)." Feed it a pre-built summary string of the fetched rows (plan §5).
- [ ] **C3** Whichever form: add a test asserting **every** fetched version appears in the output and
  **no** version is dropped or ranked — the core product promise. Include the complementary-claims case
  (one source names the killer, another the manner) to prove it doesn't assert a contradiction.

---

## Track D — `ConflictLookup` (shared component, **not** an `@AiService`) — TDD

_Directory:_ `.../conflict/` (new package) + matching test dir. _Depends on:_ nothing (start early).
This is the heaviest track. Reuse `AbstractContainerTest` (DEV-008).

- [ ] **D1** `ConflictLookupTest.kt` written first (Testcontainers, seeds `entities` + `entity_aliases`
  + `variant_claims` + `sources` + `claim_type_aliases`). Assert:
  - **(a) exact-name resolution** → returns all `variant_claims` rows for that subject + claim_type.
  - **(b) alias resolution** — a query for `Venus` resolves to `Aphrodite` via `entity_aliases` (V14).
  - **(c) trigram fuzzy resolution** — a near-miss spelling resolves via `idx_entities_name_trgm`
    (`pg_trgm` `similarity()`); pick a realistic threshold and assert a too-far string resolves to
    **nothing** (no false match).
  - **(d) resolution precedence** — exact **beats** alias **beats** trigram (a name that is both an
    exact entity and someone's alias resolves to the exact entity).
  - **(e) `normalize()` via the DB table** — a probe `claimType` of a surface form (`parents`,
    `killed by`) fetches rows stored under the canonical (`parentage`, `death`); a canonical passed in
    directly (`parentage`, which has **no** self-row) still matches (identity fallback).
  - **(f) claim-type-filtered fetch is precise** — a `death` probe on **Achilles** returns the death
    rows and **not** any other claim_type; an **appearance** probe on a subject with only a stored
    death conflict returns **empty** (this is the grounded-refusal guard, ADR-007 §5).
  - **(g) no source-count gate** — the **Io** floor case (`child of Inachus` vs `child of Piren`,
    **both `apollodorus-bibliotheca`**) is **returned** even though it's a single-source pair.
  - **(h) subject-only fetch** returns **all** claim_types for the entity (backs Track F).
  - **(i) unknown entity / empty result** handled gracefully (empty list, no throw).
- [ ] **D2** `conflict/ConflictLookup.kt` — a `@Component`. **Entity resolution** three-step chain over
  one resolution: exact (`LOWER(name) = LOWER(?)`) → `entity_aliases` (`LOWER(alias) = LOWER(?)`) →
  trigram (`ORDER BY similarity(name, ?) DESC` with a floor threshold). Consider a single SQL/CTE or a
  short-circuit chain; `VariantClaimRepository.findByEntityNameIgnoreCase` only covers the **exact**
  step, so the alias + trigram steps need new JPA methods or a `JdbcTemplate` query (the repo layer
  already mixes both — match local convention). Do **not** hardcode the trust_tier or gate on source
  count.
- [ ] **D3** **`normalize()` reads the `claim_type_aliases` DB table** (DEV-022) — `SELECT canonical
  FROM claim_type_aliases WHERE alias = lower(trim(?))`, identity when no row. **Never** a code-side
  copy of the map. Apply it to the **probe input only**; match the stored column by exact equality
  (`claim_type = ?`), leaning on `idx_variant_claims_subject_type`.
- [ ] **D4** Expose **two fetches over the one resolution**, per ADR-007 §5:
  - **`find(subject, claimType)`** — claim-type-filtered (`subject_entity_id = ? AND claim_type =
    normalize(claimType)`). Used by the enrichment step.
  - **`findAllForEntity(entityName)`** — subject-only, all claim_types for the resolved entity. Used
    **only** by the `/conflicts/{entityName}` browse endpoint (Track F).
  Both **join `sources`** so results carry `author`/`work` (+ `passage_ref`, `stance` per A1) — the
  raw row only has `source_id`.
- [ ] **D5** Return a shape C can map to `conflicts[]` (raw rows, or already `List<ConflictEntry>` if C1
  folds the mapping into the lookup — coordinate the C/D boundary so the join+map isn't done twice).

---

## Track E — `QueryService` enrichment step (TDD)

_Directory:_ `.../service/`. _Depends on:_ B (`ConflictProbe`), C (`ConflictSynthesizer`), D
(`ConflictLookup`). This is where the ADR-007 §5 pseudocode lands.

- [ ] **E1** `QueryServiceTest` extended (mock `ConflictProbe`/`ConflictLookup`/`ConflictSynthesizer`).
  Assert:
  - a conflict-shaped question routed to **SQL** yields a populated `conflicts[]` (enrichment runs
    after the SQL answer, not as a route).
  - the same for a **RAG**-routed question — proving router-independence.
  - a **claim-type mismatch** (probe returns `appearance`, subject has only a stored `death` conflict)
    → **empty** `conflicts[]`, `answer` unchanged.
  - a probe returning `none` claimType → structured lookup **skipped**, `answer` unchanged.
  - **enrichment throwing** (probe or lookup or synthesizer) → primary `answer` returned **intact**,
    error logged, `serviceError` **not** flipped by enrichment (it's not a primary-answer failure).
  - enrichment **skipped entirely** when the primary answer already has `serviceError == true`.
  - enrichment writes **only** `conflicts[]` — `answer`, `routeDecision`, `citations`, `sqlGenerated`
    are byte-identical to the pre-enrichment response (guards the "FACT/DATA scoring untouched" claim).
- [ ] **E2** `QueryService.kt` — inject `ConflictProbe`, `ConflictLookup`, `ConflictSynthesizer`. After
  `dispatch(route)` returns, run the ADR-007 §5 block: skip on `serviceError`; `probe = conflictProbe
  .extract(question)`; if `claimType` is not `none`, `conflicts = conflictLookup.find(subject,
  claimType)`; if non-empty, `answer = answer.copy(conflicts = conflictSynthesizer.synthesize(...))`.
  **Wrap the whole enrichment in try/catch** that logs and returns the answer unchanged. Keep this as a
  private `enrich(answer, question)` helper called from the one place `handle()` returns a real answer
  (SQL, RAG, and — when it lands in Stage 8 — MIXED all flow through it).
- [ ] **E3** Confirm the enrichment runs for the **SQL empty-result → RAG fallback** path too (Stage 6
  E3): the fallback returns a RAG answer, which must still be enriched. Make sure `enrich()` wraps the
  final returned answer, not each branch individually, so the fallback isn't accidentally un-enriched.
- [ ] **E4** Update the `QueryService` class doc comment — it currently says nothing about enrichment;
  per CLAUDE.md it is "the only class that knows about all three handlers **plus** the enrichment step."

---

## Track F — `GET /api/v1/conflicts/{entityName}` browse endpoint

_Directory:_ `.../controller/`. _Depends on:_ D4 (`findAllForEntity`). The one place the **subject-only**
fetch is used.

- [ ] **F1** `QueryControllerTest` (or a new slice) — `GET /api/v1/conflicts/Aphrodite` returns all
  stored versions across claim_types; an alias (`Venus`) resolves; an unknown entity returns an empty
  list (or 404 — **decide and state which**, matching how `/entities` handles misses). This path carries
  **no** claim-type context, so it must **not** filter by claim_type.
- [ ] **F2** Add the endpoint to `QueryController` (the class already has the `// added in Stage 7`
  marker). Back it with `ConflictLookup.findAllForEntity` → map to `List<ConflictEntry>` (reuse the
  Track C mapping). It is an explicit by-entity demo/dev lookup — **not** wired into enrichment, and it
  cannot pollute a grounded refusal because it's never an automatic per-answer step (ADR-007 §5).

---

## Track G — Author CONFLICT gold questions

_Directory:_ `evaluation/gold-questions.json`. _Independent_ — pure authoring against the seeded
`variant_claims`. Track H consumes these.

- [ ] **G1** Add CONFLICT questions following `IMPLEMENTATION_PLAN.md §7` schema (matching the existing
  FACT/DATA shape). Each must hit a **real seeded conflict** — from V12 the reliable ones are
  **Aphrodite parentage** (Zeus/Dione across Hesiod/Homer/Apollodorus/Hymns/Ovid — 6+ sources),
  **Achilles death** (Paris vs Apollo across Homer/Ovid/Apollodorus), and **Io parentage** (the
  single-author Inachus-vs-Piren floor case). Encode the expectation as **≥2 attributed versions in
  `conflicts[]`** — note the §7 runner may need a `conflicts_min_count`-style forward-compat key
  (mirror how Stage 5 added `min_row_count`/`sql_must_contain`); state it if you add one.
- [ ] **G2** Author at least one **negative claim-type-mismatch** case for Track H to prove the filter:
  a question about a claim type the subject has **no** stored conflict for (e.g. an appearance/motivation
  question about Achilles) → expects **empty** `conflicts[]` while still returning a normal answer.
- [ ] **G3** Sanity-check each question against live `variant_claims` (a quick `psql` select on
  `subject_entity_id` + `claim_type`) **before** committing, so H isn't chasing conflicts the seed
  data can't surface — mirror the Stage 6 lesson that shortfalls trace to data, not pipeline.

---

## Track H — Verification (sequential, run last)

_Depends on:_ all tracks. Needs a live `.env` (`LLM_API_KEY` + `LLM_CHAT_MODEL` for chat,
`OPENAI_API_KEY` for embedding) and the DB at Flyway head with the full seed + ingested corpus.

- [ ] **H1** Unit/integration suites green: `ConflictLookupTest` (all D1 cases incl. alias, trigram,
  precedence, normalize-via-DB, claim-type filter, **Io no-gate**, empty), Track C synthesizer test,
  `QueryServiceTest` enrichment cases, and the Track F endpoint test.
- [ ] **H2** Boot with real `.env`. **`POST /api/v1/query {"question":"Who were Aphrodite's parents?"}`**
  → inspect `routeDecision` (it will be `SQL` or `RAG` — **not** `CONFLICT`, which doesn't exist) and
  confirm `conflicts[]` has **≥2 entries from different authors** (Zeus per most sources vs. Dione per
  Homer/Apollodorus). This is the stage's headline "done when."
- [ ] **H3** **Router-independence proof:** confirm the Aphrodite conflict surfaces **whatever** route
  it took. If it routes SQL, also try a phrasing that routes RAG (or temporarily observe both) and
  confirm `conflicts[]` is populated either way. Record the actual `routeDecision` seen.
- [ ] **H4** **Claim-type filter proof (grounded-refusal guard):** ask the Track G2 negative case (an
  appearance/motivation question about a subject with only a stored *death* conflict) → `conflicts[]`
  is **empty**, primary `answer` still returned. This protects gold REFUSAL scoring (Stage 10).
- [ ] **H5** **Single-source floor proof:** `POST` an Io parentage question → `conflicts[]` surfaces the
  Inachus-vs-Piren pair **even though both cite `apollodorus-bibliotheca`** (no runtime source-count
  gate). Confirms CLAUDE.md's "hand-added single-source floor case still surfaces."
- [ ] **H6** **Enrichment-never-breaks-the-answer proof:** verify a normal FACT/DATA question that has
  **no** stored conflict returns exactly as it did in Stages 5/6 — same `answer`, `citations`,
  `sqlGenerated`, `routeDecision`, empty `conflicts[]`. (Regression guard: enrichment writes only
  `conflicts[]`.) Optionally force a probe/lookup failure and confirm the answer still returns.
- [ ] **H7** **Attribution quality:** confirm each `conflicts[]` entry carries a real
  `sourceAuthor`/`sourceWork` (and `passageRef` if A1 added it) from the `sources` join — no
  `"Unknown"`/placeholder authors (the Stage 6 DEV-049 failure mode; the join must be real).
- [ ] **H8** **`GET /api/v1/conflicts/Aphrodite`** returns all stored versions across claim_types;
  `GET /api/v1/conflicts/Venus` resolves via alias; an unknown name behaves per F1's decision.
- [ ] **H9** `EXPLAIN`/log spot-check (optional): confirm the claim-type-filtered fetch uses
  `idx_variant_claims_subject_type` (or note the same small-table seq-scan caveat as Stage 6 H5 if the
  planner declines it at seed scale — not a bug).
- [ ] **H10** Log any deviations in `DEVIATIONS.md` (new DEV-NNN — the A2 `ConflictSynthesizer`
  structured-vs-prose decision and the B1 probe/EntityExtractor fold are the likely ones), mark
  affected items above with `[DEVIATED - see DEVIATIONS.md #DEV-NNN]`, add the stage-note pointer to
  `IMPLEMENTATION_PLAN.md §9`, and flip the Stage 7 boxes in `TODO.md`.
