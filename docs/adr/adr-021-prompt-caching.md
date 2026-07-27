# ADR-021: Anthropic Prompt Caching — Enable, Measure, and Record That It Saves Nothing Yet

| Field        | Value       |
|--------------|-------------|
| **Date**     | 2026-07-27  |
| **Status**   | Accepted (implemented and landed 2026-07-27 — see DEV-097) |
| **Amends**   | — |
| **Amended by** | —         |
| **Supersedes** | —         |

---

## Context

Every user question costs **3–5 Anthropic chat calls**. `QueryService.handle`
(`core-api/src/main/kotlin/com/blamezeus/coreapi/service/QueryService.kt:42-102`) runs
route → dispatch → conflict probe → compose, plus one corrective SQL regeneration on the DEV-057
path:

| Route | Chat calls |
|---|---|
| RAG | 3 (router, `RagAgent`, `ConflictProbe`, `AnswerComposer`) — 4 including the composer |
| SQL | 4, or 5 with the DEV-057 attribution retry |
| MIXED | 4 |
| SQL → empty → RAG fallback | 5 |

Each call re-sends its full system prompt cold. Those system prompts are **constant for the
lifetime of the process** — nothing dynamic reaches them. `{{schema}}` is the only interpolated
value and `SchemaIntrospector` memoizes it with `by lazy`; LangChain4j's `ServiceOutputParser`
appends its `"You must answer strictly in the following format…"` instruction to the **user**
message, not the system message. So the same fixed prefixes are re-billed on every request, and the
evaluation harness multiplies that by 16 gold questions × 3 runs per ADR-017 gate.

That is textbook prompt-caching shape, and ADR-008 already recorded it as a known, un-taken cost
play — `adr-008-model-selection-update.md:112-114` rejected Gemini Flash despite *"context caching
that would benefit the repeated schema/system prompts"*.

**The constraint that reshapes the decision.** Anthropic enforces a **minimum cacheable prefix**,
it is model-specific, and it is **not monotonic across generations**:

| Chat model | Minimum cacheable prefix |
|---|---|
| Claude Opus 5 | 512 tokens |
| Claude Sonnet 5, Sonnet 4.6, Opus 4.8 | 1,024 tokens |
| Claude Opus 4.7 | 2,048 tokens |
| **Claude Haiku 4.5** (`LLM_CHAT_MODEL` since ADR-008) | **4,096 tokens** |

Haiku 4.5 has the **highest minimum of any current model**. Below it, `cache_control` is a **silent
no-op**: no cache entry, no error, no charge, no saving. Measured against this codebase — the schema
block measured live against the seeded database at 5,708 chars of table/column/comment/CHECK/FK text
plus 879 chars of vocabulary values ≈ 6,600 chars ≈ ~1,900 tokens:

| System prompt | Est. tokens | ≥ 4,096? |
|---|---|---|
| `TextToSqlAgent.generateSql` + `{{schema}}` | ~3,350 | ✗ |
| `TextToSqlAgent.generateSqlWithAttribution` + `{{schema}}` | ~2,200 | ✗ |
| `AnswerComposer` | ~520 | ✗ |
| `QueryRouter` | ~330 | ✗ |
| `RagAgent` | ~310 | ✗ |
| `ConflictProbe` | ~250 | ✗ |

**Nothing qualifies. The expected saving on the current model is zero.**

---

## Decision

### 1. Enable system-message caching on both chat model beans

`LangChain4jConfig` sets `.cacheSystemMessages(promptCacheEnabled)` on **both** `routingModel` and
`synthesisModel`, driven by `app.llm.prompt-cache-enabled`
(`${LLM_PROMPT_CACHE_ENABLED:true}` in `application.yml`, never a literal inside a `@Bean` method,
per TECH_GUARDRAILS). The two beans are independent `AnthropicChatModel` instances differing only by
temperature; the flag does not carry across, so setting it on one would silently leave every RAG and
composer call at full price.

`cacheTools` is deliberately left off: no `tools` are ever sent, so it would attach `cache_control`
to nothing.

### 2. Enable it even though it saves nothing today

Below the minimum the flag costs nothing — there is no cache write to pay the ~1.25× premium on.
It begins paying the moment the prefix clears the bar, which can happen without anyone revisiting
this decision: a larger seeded corpus grows the schema block, or the chat model changes. The
alternative — waiting until it would pay — means rediscovering this whole analysis later.

The honest framing is recorded here rather than in a commit message so no future reader infers a
saving that does not exist.

### 3. Add telemetry, because prompt caching fails silently

`config/CacheTelemetryListener.kt` is a `ChatModelListener` attached to both beans. Per chat call it
reads `AnthropicTokenUsage` and reports `inputTokens`, `cacheCreationInputTokens`, and
`cacheReadInputTokens` — to DEBUG logs, and accumulated across the request into `DebugCapture` so
`GET /api/v1/query?debug=true` reports the per-request totals.

Without this, "caching is enabled" is unfalsifiable. With it:

- **Both counters staying 0 across two identical questions inside the 5-minute ephemeral TTL** is
  the empirical proof the prefix is under the model's minimum. That is the expected result today.
- **`inputTokens` per call is the measured prefix size** — the evidence the deferred model decision
  in §5 needs, replacing the estimates in the table above.

A `ChatModelListener` was chosen over declaring the `@AiService` methods as `Result<T>`, which is
the other way LangChain4j exposes token usage: that would ripple through all three handlers,
`QueryService`, and their tests purely to read a token count. The listener writes into
`DebugCapture`'s ThreadLocal — the same cross-boundary reach DEV-064 established for
`NarrativeChunkContentRetriever`, which sits equally deep under LangChain4j's machinery — and
swallows its own exceptions, since it runs inside the chat call and anything thrown would degrade a
good answer to `serviceError`.

### 4. Freeze the schema prefix

Caching is a **byte-exact prefix match**, so any per-run drift in the prefix silently converts a
cache read into a cache write. `SchemaIntrospector.vocabularies()` ordered by `count(*) DESC` with
no tiebreaker, leaving equal-frequency values unordered. Added `, <column> ASC`. This is worth doing
independent of caching — it removes a latent source of prompt nondeterminism across restarts — and
`SchemaIntrospectorTest` now pins it by asserting two independently built introspectors produce
byte-identical prompts.

### 5. Defer the chat-model question to evidence

Switching `LLM_CHAT_MODEL` to Claude Sonnet 5 (1,024-token minimum) would make both `TextToSqlAgent`
prompts cache immediately on the SQL and MIXED routes. That is a real cost lever, but it is a model
change, not a caching change: it alters answer quality, per-token price, and latency, and ADR-017
requires a 3-run eval comparison to land. Recorded as an open item in `TODO2.md` to be decided on
the numbers the telemetry produces, not on this ADR's estimates.

### 6. This is not the banned "caching layer"

`TECH_GUARDRAILS.md` lists *"Redis or any caching layer"* under Do-Not-Add. That rule is about a
**response cache** — storing answers and serving them without calling the model. This is
**provider-side prompt caching**: a builder flag on an existing LangChain4j model, no new dependency,
no new bean type, no stored responses, and no change to what the model returns. A guardrails row now
states the distinction explicitly, because a reviewer reading "caching" will otherwise reach for the
Do-Not-Add list.

---

## Alternatives considered

- **Do nothing until the prefix clears the minimum.** Rejected: the analysis that establishes *when*
  it would clear is exactly the work done here, and leaving it unrecorded means paying for it twice.
  Enabling now is free and self-activating.
- **Switch `LLM_CHAT_MODEL` to Sonnet 5 or Opus 5 as part of this change.** Rejected for this ADR
  (see §5): it is a model decision needing an eval gate, and bundling it would make a
  behavior-neutral billing change into a quality-affecting one — impossible to attribute if the eval
  moved.
- **Pad the system prompts to clear the 4,096-token minimum.** Rejected outright. Adding tokens to a
  prompt so it qualifies for a discount on those same tokens is self-defeating, and it degrades
  prompts that DEV-069 and DEV-057 tuned deliberately.
- **Expose token usage by declaring `@AiService` methods as `Result<T>`.** Rejected: correct
  LangChain4j API, but it changes the return type of every AI service and ripples through the
  handlers, `QueryService`, and their tests to obtain a number a listener can read out-of-band.
- **Also cache in `ingestion/extraction/claim_extractor.py`.** Rejected: its stable prefix (system
  prompt + source hint + the `instructor` tool schema) is ~600 tokens against
  `EXTRACTION_MODEL=claude-sonnet-5`'s 1,024-token minimum — also a no-op — and `checkpoint.py`
  already makes re-runs cost zero API calls (DEV-038). No recurring cost to reduce.
- **Use the 1-hour cache TTL (`ttl: "1h"`) instead of the 5-minute default.** Not applicable: the
  LangChain4j beta5 builder exposes only the boolean, which emits `{"type": "ephemeral"}`. Moot
  while nothing caches; revisit alongside §5.

---

## Consequences

**Positive**

- The wiring is correct and self-activating: the day the prefix clears the minimum, caching starts
  with no code change.
- The claim is falsifiable. Cache effectiveness is now a number in the logs and on
  `?debug=true`, not an assumption.
- Measured per-call `inputTokens` become available as the input to the §5 model decision.
- The schema prefix is now provably deterministic across restarts — a latent prompt-drift bug fixed
  regardless of caching.

**Negative / costs**

- **No cost reduction today.** On Claude Haiku 4.5 the saving is exactly zero, and this ADR exists
  partly to make sure that is not misread later.
- Three new fields on `DebugInfo` (`inputTokens`, `cacheCreationTokens`, `cacheReadTokens`). The
  `@JsonInclude(NON_NULL)` contract on `QueryResponse.debug` is unaffected — `debug` is still
  omitted entirely when `debug=false` — so the pre-P2 wire contract is byte-for-byte intact.
- One more `@Component` and one more constructor dependency in `LangChain4jConfig`.
- `LangChain4jConfigTest` asserts on `AnthropicChatModel`'s private fields by reflection. That is
  the only way to pin the flag without a live LLM call (forbidden by TECH_GUARDRAILS), but it is
  coupled to LangChain4j internals and will need updating if those field names change on a version
  bump.

**Scope note / sequencing**

Behavior-neutral by construction: `cache_control` changes billing only, never model output. The
3-run eval comparison is expected to be identical, and any movement is noise rather than an effect
of this change.

**Follow-ups**

- Record `DEV-097` in `docs/DEVIATIONS.md` cross-referencing this ADR.
- Add the deviation banner to `IMPLEMENTATION_PLAN.md` §5 and the `TECH_GUARDRAILS.md` row
  distinguishing provider-side prompt caching from the banned response cache.
- Open item in `TODO2.md`: decide the §5 chat-model question once the telemetry has produced real
  per-agent `inputTokens` figures against the seeded corpus.
- Independent of caching, the larger cost lever remains the **number** of calls per query (3–5).
  `TODO-adr-015.md:60` records the composer's per-query call as a deliberate, explicitly accepted
  quality trade-off, so narrowing it is a separate decision and is explicitly *not* opened here.
