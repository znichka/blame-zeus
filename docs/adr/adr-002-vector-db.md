# ADR-002: pgvector over a Dedicated Vector Database (Qdrant / Chroma)

| Field        | Value       |
|--------------|-------------|
| **Date**     | 2026-07-08  |
| **Status**   | Accepted    |

---

## Context

The system requires a vector store to support semantic retrieval of chunked ancient source passages. Each chunk carries metadata (`source_id`, `author`, `work`, `section`, `claim_ids`, `entities`) that must:

1. Be filterable at query time, and
2. Be joinable to relational tables (`claim`, `conflict`, `source`) during the conflict-lookup stage of the retrieval pipeline (defined in ADR-001).

The system already uses **PostgreSQL** as its primary relational database for structured mythology data (entities, claims, relationships, participants, conflicts).

Five vector store options were evaluated against this context:

| Option | Description |
|---|---|
| **pgvector** | PostgreSQL extension adding vector similarity search; runs inside the existing Postgres instance |
| **Qdrant** | Purpose-built vector database with native hybrid search (dense + sparse), strong metadata filtering, and a REST/gRPC API |
| **Weaviate** | Purpose-built vector database with schema-driven data modeling and native hybrid search (BM25 + vector) |
| **Pinecone** | Fully managed, cloud-only vector database with no self-hosting option |
| **Chroma** | Lightweight, embeddable vector store commonly used in Python-first RAG prototypes; limited hybrid search support |

---

## Decision Drivers

The choice was evaluated against the following criteria, in priority order:

1. **Relational integration**: the conflict-lookup stage requires resolving vector-retrieved `claim_ids` against a relational `conflict` table. This is a structural requirement of the pipeline, not a preference.
2. **Hybrid search capability**: the corpus contains a high density of semantically opaque proper nouns, requiring both dense (embedding) and sparse (keyword) retrieval.
3. **Operational complexity**: the number of services, connection pools, and failure surfaces introduced by the choice.
4. **Metadata filtering**: the ability to filter chunks by structured attributes (source, author, entity, claim type) using patterns consistent with the rest of the codebase.
5. **Scale requirements**: the corpus size and query load the system must support.

---

## Decision

**We will use pgvector within the existing PostgreSQL instance.**

---

## Rationale

### 1. The Conflict-Lookup Stage Requires a Relational JOIN

The three-stage retrieval pipeline requires that, after initial hybrid retrieval, the `claim_ids` extracted from chunk metadata are used to query the `conflict` table and fetch chunks from disagreeing sources:

```sql
SELECT c2.chunk_text, c2.metadata
FROM conflict cf
JOIN myth_chunks c2 ON c2.claim_id = ANY(cf.claim_b_ids)
WHERE cf.claim_a_id = ANY(:retrieved_claim_ids);
```

With pgvector, this executes as a single SQL query inside one transaction. With Qdrant or Chroma, the same lookup requires two round trips:

1. A query to PostgreSQL to resolve `claim_ids` into conflicting claim pairs
2. A query to the vector store to fetch the corresponding chunks by ID

This cross-service pattern adds network latency, introduces an additional failure surface, and prevents the lookup from participating in a single transaction. pgvector removes this split entirely: one database, one connection, one query.

### 2. Hybrid Search Is Achievable Within PostgreSQL

The corpus requires hybrid retrieval (dense + sparse) due to its density of proper nouns with limited semantic signal in embedding space. PostgreSQL provides both natively:

- **Dense search**: pgvector's `<=>` cosine distance operator over `vector(1536)` columns, indexed with `hnsw`
- **Sparse/keyword search**: PostgreSQL full-text search (`tsvector` / `tsquery`), indexed with `GIN`

The two are combined via Reciprocal Rank Fusion (RRF) in a single query:

```sql
WITH dense AS (
    SELECT id, chunk_text, metadata,
           embedding <=> :query_embedding AS dense_rank
    FROM myth_chunks
    ORDER BY dense_rank
    LIMIT 20
),
sparse AS (
    SELECT id, chunk_text, metadata,
           ts_rank(fts_vector, plainto_tsquery('english', :query)) AS sparse_rank
    FROM myth_chunks
    WHERE fts_vector @@ plainto_tsquery('english', :query)
    LIMIT 20
),
rrf AS (
    SELECT
        COALESCE(d.id, s.id) AS id,
        COALESCE(d.chunk_text, s.chunk_text) AS chunk_text,
        COALESCE(d.metadata, s.metadata) AS metadata,
        (COALESCE(1.0 / (60 + dense_rank_pos), 0) +
         COALESCE(1.0 / (60 + sparse_rank_pos), 0)) AS rrf_score
    FROM dense d
    FULL OUTER JOIN sparse s ON d.id = s.id
)
SELECT * FROM rrf ORDER BY rrf_score DESC LIMIT 10;
```

> **Note:** The rank-position calculation above is illustrative; the production implementation computes `dense_rank_pos` / `sparse_rank_pos` via window functions and is encapsulated in a single `MythChunkRepository` method, tested in isolation from the rest of the application.

This is more verbose than Qdrant's native hybrid search API, but requires no infrastructure beyond the existing PostgreSQL instance.

### 3. A Single Database Reduces Operational Complexity

Introducing a dedicated vector database alongside PostgreSQL would add:

- A second service to deploy, monitor, and back up
- A second connection pool to manage
- A second failure point in the retrieval pipeline
- A risk of schema drift between the vector store and the relational schema over time

Given a bounded corpus of seven sources with a well-defined data model, this operational cost is not offset by a corresponding gain in retrieval quality. pgvector keeps the entire data layer under one backup strategy, one connection pool, and one set of credentials.

### 4. Metadata Filtering Uses Standard SQL

Every chunk carries metadata that must be filterable by source, author, entity, and claim type. In pgvector, this is stored as a `jsonb` column or as typed columns on `myth_chunks`, filtered via standard `WHERE` clauses and GIN-indexed `jsonb` operators, the same pattern used elsewhere in the application.

In Qdrant, equivalent filtering requires constructing payload filters in Qdrant's own filter syntax, which cannot reuse the application's existing SQL-based query patterns or repository abstractions.

### 5. Corpus Scale Does Not Require Purpose-Built Vector Infrastructure

Qdrant's primary advantages over pgvector (higher query throughput at scale, built-in horizontal scaling, quantisation, and native sparse vector formats such as SPLADE) become relevant at corpus sizes in the millions of vectors, or under high concurrent query load.

The corpus in scope (seven ancient sources, at most tens of thousands of chunks) does not approach this scale. An `hnsw` index in pgvector is sufficient for the expected workload.

---

## Consequences

### Accepted Costs

| Cost | Detail |
|---|---|
| **Hybrid search SQL complexity** | The RRF fusion query is more complex than Qdrant's single API call. Mitigated by encapsulating it in a single repository method, tested independently. |
| **No native sparse vector support** | pgvector does not support learned sparse embedding formats (e.g. SPLADE); sparse retrieval relies on PostgreSQL full-text search instead. Sufficient for this corpus; would need revisiting for larger or more technical corpora. |
| **Index tuning required** | `hnsw` parameters (`m`, `ef_construction`) and FTS configuration (`english` dictionary) require tuning during ingestion. Primarily a one-time cost; minor re-tuning may be needed only if corpus size or query patterns change materially. |
| **Extension dependency** | Requires `CREATE EXTENSION vector` in the Flyway baseline migration. **Open risk:** not all managed PostgreSQL providers support this extension; availability must be confirmed against the team's chosen provider before migration (see Assumptions below). |

### Benefits Gained

- Conflict-lookup stage executes as a single SQL `JOIN`: no cross-service network call, no additional failure surface
- Metadata filtering uses standard SQL, consistent with all other repository queries
- Single database instance: one backup strategy, one connection pool, one deployment unit
- Hybrid search (dense + sparse + RRF) is fully achievable within PostgreSQL, without additional infrastructure
- Flyway migration history covers both relational and vector schema in one place

---

## Assumptions and Open Risks

- **pgvector availability**: This decision assumes the team's chosen PostgreSQL hosting provider supports the `pgvector` extension. This must be explicitly confirmed before the baseline migration is written. Availability varies across managed providers and is not assumed to be universal.

---

## Alternatives Considered

### Qdrant

Qdrant offers the cleanest hybrid search API of the options evaluated: native dense + sparse retrieval with built-in RRF, strong metadata filtering, and mature client library support. In isolation, it is the technically stronger vector store.

**Rejected because** the conflict-lookup stage requires a join between vector chunk metadata and relational conflict data. Under Qdrant, this becomes a two-service round trip on every query, adding latency and operational complexity that the corpus scale does not justify.

**Revisit trigger:** If the corpus expands significantly beyond the current seven sources, if query latency becomes a measured bottleneck, or if retrieval quality requires learned sparse embeddings (e.g. SPLADE), Qdrant should be re-evaluated as a dedicated vector layer, with the conflict join either moved to a materialised cache or resolved via application-side merge.

### Chroma

**Rejected early.** Chroma is oriented toward Python-first RAG prototyping, has limited hybrid search support, and offers no meaningful advantage over pgvector in a JVM/Spring Boot stack. Its metadata filtering is weaker than both pgvector and Qdrant for structured query patterns.

### Weaviate

Weaviate's native hybrid search (BM25 + vector, fused server-side) is arguably stronger than the hand-rolled RRF query implemented in pgvector. This is its clearest advantage over the chosen approach. Its schema-driven data modeling also makes it a reasonable fit for structured metadata like `source_id`, `author`, and `entities`.

**Rejected for the same structural reason as Qdrant:** the conflict-lookup stage requires resolving `claim_ids` against the relational `conflict` table. Weaviate's GraphQL-based query model cannot express this as a join; it would require the same two-service round trip (Postgres → resolve conflicts → Weaviate → fetch chunks by ID) as Qdrant, with the same latency and transaction-boundary problems described in Rationale §1.

Additionally, Weaviate's metadata filtering uses its own `where`-filter syntax rather than SQL, which, as with Qdrant, breaks consistency with the rest of the application's query patterns (Rationale §4).

**Revisit trigger:** If the system evolves from a single bounded corpus into a multi-tenant product serving many independent corpora, Weaviate's schema/class model and built-in multi-tenancy become materially more valuable, and the operational cost of a second database becomes easier to justify. It should also be reconsidered if the hand-rolled RRF query in pgvector proves to be a retrieval-quality bottleneck.

---

### Pinecone

Pinecone was evaluated primarily for its zero-operations model: no infrastructure to deploy, monitor, or scale. For a team without dedicated ops capacity, this is a genuine advantage.

**Rejected for three compounding reasons:**

1. **The relational JOIN problem is worse, not better, with Pinecone.** Because Pinecone is an external managed service rather than infrastructure the team controls, the conflict-lookup round trip described in Rationale §1 becomes a call across the public internet to a third-party API, rather than a call to a co-located self-hosted service. This adds latency and an external availability dependency directly into the retrieval pipeline's critical path.
2. **No self-hosting option.** All source data and derived embeddings would leave the team's infrastructure boundary. For a project built on structured, versioned source material, this is an unnecessary loss of control with no offsetting benefit at this scale.
3. **Scale mismatch.** Pinecone's core advantages (serverless elasticity, performance at billions of vectors, managed horizontal scaling) are irrelevant at a corpus of tens of thousands of chunks. Its pricing model is also optimized for larger, variable workloads, not a small, bounded dataset.

**Revisit trigger:** If the system's scope expands to ingest a substantially larger or continuously growing corpus (many sources beyond the current seven, or multi-tenant usage across corpora), and the team is willing to accept vendor lock-in and cross-network latency in exchange for eliminating self-hosted infrastructure, Pinecone should be reconsidered, most likely alongside a redesign of the conflict-lookup stage to avoid requiring a live relational join (e.g., via a denormalized or materialized conflict index).
