package com.blamezeus.coreapi.domain.entity

import jakarta.persistence.Column
import jakarta.persistence.Entity
import jakarta.persistence.GeneratedValue
import jakarta.persistence.GenerationType
import jakarta.persistence.Id
import jakarta.persistence.Table

// `embedding` is deliberately unmapped: it's a pgvector column LangChain4j's
// PgVectorEmbeddingStore/custom ContentRetriever own, never plain JPA reads/writes
// (DEV-025). ddl-auto: validate only checks mapped columns exist, so leaving it out
// entirely is safe and simpler than a @Transient placeholder.
@Entity
@Table(name = "narrative_chunks")
class NarrativeChunk(
    @Id
    @GeneratedValue(strategy = GenerationType.IDENTITY)
    val id: Int = 0,
    val content: String,
    @Column(insertable = false, updatable = false)
    val contentHash: String? = null,
    val sourceId: String,
    val passageRef: String? = null,
    // The Python ingestion pipeline is this column's only writer (V8_4/DEV-028).
    @Column(insertable = false, updatable = false)
    val embeddingModel: String? = null,
)
