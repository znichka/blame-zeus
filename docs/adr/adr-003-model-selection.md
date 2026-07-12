
# ADR-003: LLM and Embedding Model Selection for the PoC

| Field        | Value       |
|--------------|-------------|
| **Date**     | 2026-07-08  |
| **Status**   | Accepted    |

**Supersedes:** none. **Extended by:** ADR-004 (seed-data-extraction-strategy), which builds a full offline extraction pipeline on top of the extraction-model choice made here.

> ⚠️ Amended by ADR-008 — the chat model (`gpt-4o-mini` → Claude Haiku 4.5) and extraction model
> (`gpt-4o` → Claude Opus 4.8) choices below are updated; the embedding choice (`text-embedding-3-small`)
> is reaffirmed and the structure (per-role temps, provider-agnostic chat, locked embeddings) is unchanged.
> See `docs/adr/adr-008-model-selection-update.md` and `DEVIATIONS.md` DEV-015.

---

## Context

CONCEPT.md defines five AI capabilities that run in real time, at query time (§10): query routing, text-to-SQL generation (including recursive CTEs for lineage), RAG synthesis with citations, conflict-aware synthesis, and entity extraction. It also implies two capabilities that run offline: embedding the narrative corpus for RAG (§9, §11) and (once the extraction approach was formalized in ADR-004) LLM-assisted generation of seed data (`entities`, `relationships`, `variant_claims`).

Before any of `core-api` could be built, the team needed to decide which model(s) power each of these roles, which embedding model backs the pgvector store, and how tightly the codebase should couple itself to one vendor's SDK. Three properties of the PoC shaped the decision:

- **Structured output is load-bearing, not cosmetic.** The product's differentiator (attributed, conflicting claims with citations) depends on the chat model reliably returning well-formed JSON (`RagResponse`) and safe, constrained SQL, not just fluent prose.
- **Scale is small and fixed.** Six public-domain sources, a few hundred pages of corpus, a 15-20 question gold set (CONCEPT §12). This is not a workload that needs frontier-tier context windows or throughput.
- **Two runtimes, two languages.** `core-api`/`telegram-bot` are Kotlin/Spring; `ingestion` (including, later, extraction) is standalone Python. Any model decision has to work cleanly in both without duplicating integration logic.

## Options Considered

**Chat/completion provider:** OpenAI (GPT-4o family), Anthropic Claude, Google Gemini, self-hosted open-source models (e.g. Llama 3 / Mistral via vLLM or Ollama).

**Embedding model:** OpenAI `text-embedding-3-small`, OpenAI `text-embedding-3-large`, a self-hosted sentence-transformer model.

**JVM integration layer:** LangChain4j vs. Spring AI vs. calling provider SDKs directly from application code.

### Chat/completion provider

OpenAI was selected as the Phase 1 provider. The deciding factors were coverage and integration cost rather than a claim that competing models are weaker: OpenAI's models cover chat, embeddings, and structured extraction in one vendor, which meant the PoC could stand up its entire AI surface behind a single API key pair and one SDK family (LangChain4j's OpenAI starter in the JVM, the `openai` Python SDK in ingestion) instead of integrating multiple providers for a proof of concept. Anthropic and Google were not disqualified on capability (both were viable candidates for the chat role), but choosing between them and OpenAI as the *default* wasn't worth resolving for Phase 1 given the chat model was going to be made swappable regardless (see Decision). Self-hosted open-source models were rejected outright for this phase: there was no budget or timeline in a PoC to stand up and tune a hosting stack, and the reliability of structured JSON output and text-to-SQL generation from smaller open models was judged too inconsistent for a demo whose credibility depends on syntactically valid, safe SQL and well-formed citations every time.

### Embedding model

`text-embedding-3-small` (1536 dimensions) was chosen over `text-embedding-3-large`. At this corpus size (six sources, not a production-scale document set), the retrieval-quality gap between the two tiers was judged marginal relative to the cost and index-size difference, and 1536 dimensions keep the pgvector HNSW index cheap to build at PoC scale. A self-hosted embedding model was rejected for the same infra-overhead reason as self-hosted chat models. Once chosen, the embedding model was treated as effectively locked in for the life of the PoC: embeddings generated at ingestion time must match the model used at query time bit-for-bit in dimensionality and semantics, so changing this choice later means re-ingesting the entire corpus, not swapping a config value.

### JVM integration layer

LangChain4j was chosen over Spring AI and over calling the OpenAI Java SDK directly. Spring AI was evaluated and explicitly rejected: running both frameworks in the same codebase risks duplicate or conflicting bean definitions for the same model concerns, and LangChain4j's `@AiService` interface pattern mapped more directly onto the concept's five distinct AI roles, letting each be its own mockable interface with its own temperature setting. Calling the OpenAI Java SDK directly was rejected because it would hardcode the provider into business logic exactly where CONCEPT.md's routing/synthesis/extraction roles most need to stay swappable.

## Decision

1. **LangChain4j is the sole LLM integration layer inside the JVM services** (`core-api`, `telegram-bot`). Every AI role from CONCEPT.md §10 is modeled as an `@AiService` interface, with no inline `ChatLanguageModel.generate()` calls in business logic and no direct Anthropic or OpenAI Java SDK usage anywhere in those modules.
2. **OpenAI is the Phase 1 model provider** for chat, embeddings, and offline extraction: one vendor across the whole pipeline.
3. **Chat model default: `gpt-4o-mini`**, configured via `LLM_CHAT_MODEL` with no hardcoded default (it must be set explicitly in `application.yml`/environment). It backs query routing, text-to-SQL generation, RAG synthesis, conflict synthesis, and query-time entity extraction. The `@AiService`/`ChatLanguageModel` abstraction keeps this provider swappable: replacing it later (e.g. with an Anthropic or Gemini `ChatLanguageModel` implementation) is a bean-and-starter-dependency change, not a rewrite of the five AI interfaces.
4. **Temperature is set per role, not per model:** `0.0` for routing and text-to-SQL generation, where determinism is required for SQL-safety validation and reproducible test behavior; `0.3` for RAG and conflict synthesis, where natural prose is wanted but must stay grounded in retrieved context.
5. **Embedding model: `text-embedding-3-small`, fixed at 1536 dimensions.** Used identically at ingestion time and query time via a dedicated API key (`app.llm.embedding-api-key`), decoupled from the chat model's key so the chat provider can be swapped without touching embeddings. Not swappable without a full corpus re-ingestion.
6. **Offline seed-data extraction uses a distinct, higher-capability model tier (`gpt-4o`)**, called via the `instructor` library on the same OpenAI Python client already used for embeddings, never the JVM chat model and never at query time. This reflects that `variant_claims` accuracy is the product's core differentiator (CONCEPT §8): a misattributed or hallucinated conflict actively undermines trust, so the one-time, offline cost of a stronger model buys more reliable attribution (e.g. correctly separating "Castor says X" from "Hesiod says Y" within a single source paragraph) than the cheaper runtime tier would. This choice is the seed for what ADR-004 later formalizes into a full extraction pipeline.
7. **The `ingestion` Python job is the sole sanctioned exception** to the "everything through LangChain4j" rule: it uses the OpenAI Python SDK directly for both embedding and extraction, because it is corpus-prep tooling that never runs at query time and never touches `LangChain4jConfig.kt`.

## Consequences

**Positive**

- One vendor for chat, embeddings, and extraction minimizes Phase 1 integration surface: two API keys (`LLM_API_KEY`, `OPENAI_API_KEY`), two SDK families total, both already covered by chosen libraries (LangChain4j, `instructor`).
- The provider-agnostic `ChatLanguageModel` abstraction means the `gpt-4o-mini` default is a starting point, not a commitment: swapping to Claude or Gemini later touches `LangChain4jConfig.kt` and a starter dependency, not the five `@AiService` interfaces or the handlers that call them.
- Per-role temperature discipline gives deterministic, testable SQL and routing while keeping synthesized answers readable.
- Separating the extraction tier (`gpt-4o`) from the runtime chat tier (`gpt-4o-mini`) puts spend where the product's trust guarantee actually depends on it, without paying flagship-model latency and cost on every live query.

**Negative / trade-offs**

- The embedding model is a hard lock-in for the PoC's lifetime: any future change (larger OpenAI embedding model, a different provider, a self-hosted model) requires re-embedding and re-ingesting the full corpus. That's an accepted, deliberate PoC-scope trade, not something to revisit without a demonstrated retrieval-quality problem.
- Running two OpenAI model tiers (`gpt-4o-mini` for runtime roles, `gpt-4o` for extraction) adds configuration surface: `LLM_CHAT_MODEL` vs. the extraction pipeline's `EXTRACTION_MODEL`, both of which have to be kept straight in `.env.example` and are easy to conflate during setup.
- Single-vendor selection means an OpenAI outage affects chat, embeddings, and extraction simultaneously. Acceptable for a PoC/demo; would need reconsideration before any production hardening.
- No hosted or open-source fallback exists. If OpenAI API access is unavailable, the PoC cannot run RAG, text-to-SQL, or ingestion at all.
