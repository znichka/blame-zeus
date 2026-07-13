# ADR-008: Model Selection Update (Claude for Chat & Extraction; Embedding Model Reaffirmed)

| Field        | Value       |
|--------------|-------------|
| **Date**     | 2026-07-10  |
| **Status**   | Accepted    |
| **Amends**   | ADR-003 (LLM and embedding model selection) |

> Applied 2026-07-10 under the *edit-existing-files-only* scope (see `DEVIATIONS.md` DEV-015): docs,
> banners, and existing config values updated now; the two dependency additions and the `@AiService`/
> `instructor` code swaps are deferred to the stages that build `LangChain4jConfig.kt` and
> `claim_extractor.py`. Action-item status reflected in the checklist below.

> ⚠️ §3's embedding reaffirmation is **superseded by ADR-013** (2026-07-13): the escalation path this
> ADR named ("`text-embedding-3-large` is the low-friction quality upgrade") was taken before Stage 3
> corpus growth — `EMBEDDING_MODEL=text-embedding-3-large`, `vector(3072)` + halfvec HNSW via `V8_4`,
> corpus re-embedded. Chat and extraction model decisions here are unaffected.
> See `docs/adr/adr-013-embedding-model-upgrade-3-large.md` and `DEVIATIONS.md` DEV-028.

---

## Context

ADR-003 selected, for Phase 1: `gpt-4o-mini` as the runtime chat model (all five `@AiService`
roles), `gpt-4o` for offline seed-data extraction, and `text-embedding-3-small` for embeddings.
ADR-003 was explicit that the **chat model is swappable** (a `LangChain4jConfig` bean + starter
change, provider kept out of business logic) while the **embedding model is locked** for the
PoC's life (changing it forces a full corpus re-ingestion).

By mid-2026 the `gpt-4o` family is dated compared to what's currently available. A review of current
options (July 2026) found the small/fast tier is now contested by **GPT-5 mini**, **Claude
Haiku 4.5**, and **Gemini 3 Flash** (near-parity, single-digit-point quality gaps), and the
frontier tier by GPT-5.x and **Claude Opus 4.8**. This ADR updates the *choices* ADR-003 made;
it does not change ADR-003's *structure* (per-role temperature, provider-agnostic chat via
`@AiService`, locked embeddings, offline-extraction as a distinct stronger tier).

The project already treats Anthropic as a viable chat provider (ADR-003 §Chat provider) and the
extraction pipeline uses `instructor`, which supports Anthropic directly, so both swaps are
low-friction.

## Decision

1. **Runtime chat model → `Claude Haiku 4.5`** (replaces `gpt-4o-mini`). It backs all five
   runtime roles (routing, text-to-SQL, RAG synthesis, conflict synthesis, `ConflictProbe`
   enrichment; see ADR-007). Chosen for the current small-tier's strongest **instruction-following
   and structured-output reliability**, which is what this workload actually stresses: constrained
   JSON (`RagResponse`) and safe, valid SQL (incl. recursive CTEs) at temperature 0.0. Swap is a
   `LangChain4jConfig` bean + `langchain4j-anthropic-spring-boot-starter` dependency change; the
   five `@AiService` interfaces are untouched.

2. **Offline extraction model → `Claude Opus 4.8`** (replaces `gpt-4o`). Extraction accuracy is
   the product's differentiator (ADR-003 §Decision 6: a misattributed conflict undermines trust),
   and extraction is one-time, offline, and cost-insensitive, so it takes the **strongest tier**.
   Invoked via `instructor.from_anthropic(...)`, mirroring the existing `instructor.from_openai`
   pattern; never at query time, never in `LangChain4jConfig`.

3. **Embedding model → reaffirm `text-embedding-3-small`** (OpenAI, 1536-dim, locked). It is
   *mid-tier* by 2026 MTEB standards; `text-embedding-3-large` is the low-friction quality upgrade
   (same vendor, 3072-dim, `vector(3072)` schema change) and non-OpenAI leaders (Voyage, Cohere,
   Gemini) score higher on retrieval. **Because the embedding is locked after ingestion, any
   upgrade must be decided *before* the corpus is embedded.** Decision for Phase 1: keep `-small`,
   and only escalate to `-large` (or a benchmarked alternative) if a pre-ingestion retrieval check
   on the hardest questions (list/numeric lookups) shows `-small` is the bottleneck.

4. **Per-role temperature discipline is unchanged** (ADR-003 §Decision 4): 0.0 for routing,
   text-to-SQL, and the `ConflictProbe`; 0.3 for RAG and conflict synthesis.

5. **Swap-after-eval discipline.** These are the recommended *targets*, not a mandate to swap
   blind. Run the gold set on whatever is configured, then swap where eval shows weakness: the
   `@AiService` (chat) and `instructor` (extraction) abstractions make each swap cheap.

## Rationale

- **Concentrate quality where trust lives.** Cheap/fast on the high-volume runtime path
   (Haiku 4.5), strongest available on the one-time offline extraction (Opus 4.8). That's the same
   tiering logic ADR-003 already reasoned toward, now with current-generation models.
- **Instruction-following over raw benchmark for the runtime.** The runtime model must emit valid
   SQL and schema-shaped JSON every time; Haiku 4.5's reliability there matters more than a
   marginal general-benchmark lead.
- **The embedding lock forces a now-or-never call.** Reaffirming `-small` is a deliberate,
   documented choice with a defined escalation trigger, not an omission.

## Consequences

**Positive**
- Current-generation quality without changing the AI architecture (roles, temperatures, swap
  mechanics all unchanged).
- Extraction accuracy (the differentiator) runs on a frontier model at one-time offline cost.

**Negative / trade-offs**
- **Two vendors.** Anthropic (chat + extraction) + OpenAI (locked embeddings). This trades away
  ADR-003's single-vendor simplicity; you **cannot drop OpenAI** entirely because the embedding
  model stays `text-embedding-3-small`. Two API keys become three concerns across two providers.
- **`LLM_API_KEY` now points at Anthropic**, `OPENAI_API_KEY` remains for embeddings; `.env.example`
  and `application.yml` comments in `IMPLEMENTATION_PLAN.md §5` must reflect the split.
- An Anthropic outage affects chat *and* extraction (but not embeddings); an OpenAI outage affects
  embeddings/ingestion only. Acceptable for a PoC.
- `EXTRACTION_MODEL` (Python) and `LLM_CHAT_MODEL` (JVM) now name Anthropic models: the "two
  tiers, keep them straight" caveat from ADR-003 §Consequences still applies.

## Alternatives Considered

- **Stay single-vendor OpenAI, upgrade to `GPT-5 mini` (runtime) + `GPT-5` (extraction).** Fully
  viable and keeps one vendor aligned with the locked embeddings. Rejected as the primary choice
  only because Opus 4.8 is the stronger extraction option for the attribution-critical work; if
  single-vendor simplicity is valued over best-in-class extraction, this is the fallback.
- **`Gemini 3 Flash` for runtime.** Cheapest + fastest, with context caching that would benefit
  the repeated schema/system prompts. A strong cost play; not chosen because it adds Google as a
  third vendor and Haiku 4.5 aligns with the Anthropic extraction choice.
- **Keep `gpt-4o`/`gpt-4o-mini` (ADR-003 as-is).** Rejected: dated by mid-2026, and the swap is cheap.
- **Upgrade embeddings to `-large` now.** Deferred, not rejected. Held as the pre-ingestion
  escalation lever (§Decision 3) pending a retrieval-quality signal.

## Traceability

- `ADR-003`: model selection (amended: chat and extraction model choices updated; embedding
  choice reaffirmed; structure unchanged).
- `ADR-007`: the five runtime roles (incl. `ConflictProbe`) this chat model backs.
- `IMPLEMENTATION_PLAN.md §4`: `EXTRACTION_MODEL` (now Opus 4.8 via `instructor`).
- `IMPLEMENTATION_PLAN.md §5`: `LangChain4jConfig` chat beans, `LLM_CHAT_MODEL`, per-role temps.
- `CLAUDE.md`: "LLM provider" section (provider-agnostic chat, fixed OpenAI embedding).

## Action Items

- [ ] **(Deferred — Stage 5)** Add `langchain4j-anthropic-spring-boot-starter` to `core-api`; update
      `LangChain4jConfig` chat beans to `AnthropicChatModel` with `LLM_CHAT_MODEL=claude-haiku-4-5-20251001`.
      *(Bean/dependency not created now — `LangChain4jConfig.kt` does not exist yet.)*
- [x] Point `LLM_API_KEY` at Anthropic; keep `OPENAI_API_KEY` for embeddings; update `.env.example`.
      *(Done: `.env.example`, `application-test.yml` chat-model.)*
- [ ] **(Deferred — Stage 4 A5/A8)** Extraction: `instructor.from_anthropic(...)`,
      `EXTRACTION_MODEL=claude-opus-4-8`; add the `anthropic` Python dependency to
      `ingestion/requirements.txt`. *(Code/dependency not created now — `claim_extractor.py` does not
      exist yet; `TODO-stage4.md` A5/A8 updated to specify Anthropic.)*
- [x] Keep `text-embedding-3-small`; pre-ingestion escalation note recorded (escalate to `-large` only
      if a retrieval check on list/numeric questions shows `-small` is the bottleneck) — in DEV-015 and
      this ADR §Decision 3.
- [x] Log **DEV-015** in `docs/DEVIATIONS.md`; add `> ⚠️ Amended by ADR-008` to ADR-003 and to
      `IMPLEMENTATION_PLAN.md §4, §5`. *(Also reconciled `CLAUDE.md` + `TECH_GUARDRAILS.md`.)*
- [ ] **(Deferred — pre-commit)** Verify the swap against gold questions before committing
      (swap-after-eval discipline). *(Requires the built chat path — runs when Stage 5 wiring lands.)*
