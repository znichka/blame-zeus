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
