# ADR-001: LangChain4j over Spring AI as the LLM Integration Framework

| Field      | Value                          |
|------------|--------------------------------|
| **Date**   | 2026-07-08                     |
| **Status** | Accepted                       |

---

## Context

We are building a Greek mythology Q&A assistant whose defining feature is
**source-attributed, conflict-aware answers**: every factual claim the system
makes must be traceable to a specific ancient source (Apollodorus, Homer,
Hesiod, Ovid, etc.), and when sources disagree the system must surface that
disagreement explicitly rather than synthesising a blended answer.

The system is built on **Kotlin + Spring Boot** and uses **PostgreSQL** for
both structured relational data and vector storage (pgvector). The corpus spans
seven ancient sources of varying authority and role. The retrieval architecture
is non-standard: it is a **three-stage hybrid pipeline** (dense + sparse
retrieval → conflict lookup → context assembly), not a simple
embed-and-retrieve flow.

Two frameworks were evaluated:

- **LangChain4j**: a Java/Kotlin LLM framework with composable retrievers, AI
  Services, and structured output mapping; requires manual Spring wiring.
- **Spring AI**: a Spring-native LLM framework with autoconfiguration,
  `ChatClient`, and `VectorStore` abstractions; lower integration overhead in a
  Spring Boot app.

---

## Decision

**We will use LangChain4j.**

---

## Rationale

### 1. Multi-stage retrieval is a first-class requirement

Our retrieval pipeline is not a single vector lookup. It requires:

1. **Hybrid retrieval**: dense (pgvector semantic search) + sparse (PostgreSQL
   full-text search via `pg_trgm` / `tsvector`) fused with Reciprocal Rank
   Fusion (RRF).
2. **Conflict lookup**: retrieved chunk metadata (`claim_ids`) is used to JOIN
   the `conflict` table and fetch additional chunks from disagreeing sources.
3. **Source-grouped context assembly**: chunks are grouped by source and
   injected into the prompt as labelled, attributed blocks.

LangChain4j's `EnsembleRetriever` provides RRF fusion over multiple
`ContentRetriever` implementations out of the box. Spring AI has no equivalent
abstraction; the fusion logic would need to be written and maintained manually.
The multi-stage pipeline (retrieve, then query SQL for conflicts, then
re-fetch) fits LangChain4j's composable retriever model directly. Spring AI's
advisor chain is designed for simpler linear flows and would require non-trivial
custom extension for this shape.

### 2. Structured output mapping is central to both ingestion and routing

The system requires LLM-driven structured output in two critical places:

**Ingestion pipeline:** Raw source passages are processed by an LLM to extract
typed `Claim` objects:

```kotlin
Claim(
    type    = PARENTAGE,
    subject = "Persephone",
    object  = "Zeus",
    source  = "Apollodorus"
)
```

These are compared across sources to populate the conflict table at ingestion time rather than discovery at query time.

**Query routing:** Incoming questions are classified as structured fact lookup (→ SQL), semantic/thematic search (→ vector), or hybrid, before retrieval begins.

LangChain4j's AI Services handles both via annotation-driven interfaces with automatic response mapping to Kotlin data classes. Spring AI supports structured output via BeanOutputConverter, but has fewer established patterns for the ingestion pipeline shape and requires more manual wiring for the routing classifier.

### 3. Proper noun density makes hybrid search non-optional

The corpus is dense with proper nouns (deity names, hero names, place names, epithets) that are semantically opaque to embedding models. "Hecatoncheires", "Tartarus", "Bellerophon" will not reliably surface via dense retrieval alone. Sparse keyword search is a hard requirement, not an optimisation.

LangChain4j's EnsembleRetriever composes a dense EmbeddingStoreContentRetriever and a custom sparse retriever (backed by PostgreSQL FTS) with RRF fusion natively. In Spring AI, both retriever legs and the fusion step would require custom implementation with no framework-provided composition model.

### 4. Source attribution requires metadata preservation through the full pipeline

Every vector chunk carries structured metadata:

| source_id | author | work | section | claim_ids | entities |
|-----------|--------|------|---------|-----------|----------|

This metadata must survive retrieval intact and be used downstream: for conflict lookup (via claim_ids), for prompt labelling (via author / section), and for citation generation in the final response.

Both frameworks support metadata on vector documents. However, LangChain4j's retriever pipeline makes it straightforward to inspect, filter, and act on metadata between stages. The conflict lookup stage (which reads claim_ids from retrieved chunks and fires a SQL JOIN) is a natural extension of the retriever chain in LangChain4j. In Spring AI's advisor model, intercepting retrieved results mid-pipeline to perform secondary lookups requires more invasive customisation.

### 5. The Spring integration cost is justified and bounded

The primary argument for Spring AI is zero-friction Spring Boot integration: autoconfiguration of ChatClient, EmbeddingModel, and VectorStore via starters, with no manual @Bean definitions required.

LangChain4j requires explicit @Bean configuration for each component:

```kotlin
@Bean fun embeddingModel(): EmbeddingModel { ... }
@Bean fun embeddingStore(): EmbeddingStore<TextSegment> { ... }
@Bean fun chatModel(): ChatLanguageModel { ... }
@Bean fun hybridRetriever(...): ContentRetriever { ... }
```

This adds roughly three to four configuration classes compared to Spring AI. This cost is real but bounded. Given that we are writing custom retriever stages regardless (the sparse retriever, the conflict lookup stage, the context assembler), we are already outside the zero-configuration zone. The marginal cost of also wiring the base components is low relative to the overall custom work required.

Spring Boot's broader ecosystem (JPA, transactions, Flyway, Actuator, testing) is retained. LangChain4j is the LLM layer only; it does not replace Spring Boot.

## Consequences

### Accepted costs

- Manual Spring wiring for LLM client, embedding model, and vector store beans (three to four config classes).
- API instability risk: LangChain4j moves fast, so dependency upgrades need attention between versions.
- Fewer Spring Boot autoconfiguration conveniences: health indicators and metrics integration require manual addition if needed.
- Smaller Spring-ecosystem community compared to Spring AI for Spring Boot-specific patterns.

### Benefits gained

- EnsembleRetriever with RRF fusion eliminates custom fusion implementation for hybrid search.
- AI Services provides clean annotation-driven structured output for both ingestion claim extraction and query routing.
- Composable retriever model supports the three-stage pipeline (hybrid → conflict lookup → assembly) without fighting the framework.
- Richer community examples for exactly the RAG shape we are building (multi-retriever, metadata-filtered, structured output).
- Model-agnostic by design: OpenAI, Anthropic, and Ollama are all supported, and swapping providers requires a single bean change.

## Alternatives considered

### Spring AI

Rejected as the primary LLM framework for this project. Spring AI's autoconfiguration and Spring-native integration are genuine advantages for standard RAG use cases. However, its advisor chain is designed for linear retrieval flows and does not provide composable multi-stage retrieval primitives. Hybrid search fusion and the conflict-lookup stage would require manual implementation with no framework support. The Spring integration convenience does not offset the cost of building the retrieval architecture against the grain of the framework.

Revisit trigger: If Spring AI ships a composable multi-retriever abstraction with RRF fusion support, the integration cost advantage would make it worth re-evaluating.

### Hand-rolled (no LLM framework)

Considered for a PoC with a small corpus. Rejected because the structured output mapping for claim extraction during ingestion, and the query routing classifier, both require non-trivial prompt engineering and response parsing that AI Services provides for free. The framework earns its keep before retrieval even begins.
