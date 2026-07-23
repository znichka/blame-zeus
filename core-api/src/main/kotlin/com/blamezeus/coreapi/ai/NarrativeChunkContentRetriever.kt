package com.blamezeus.coreapi.ai

import com.blamezeus.coreapi.domain.dto.DebugInfo
import com.blamezeus.coreapi.service.DebugCapture
import com.pgvector.PGvector
import dev.langchain4j.data.document.Metadata
import dev.langchain4j.data.segment.TextSegment
import dev.langchain4j.model.embedding.EmbeddingModel
import dev.langchain4j.rag.content.Content
import dev.langchain4j.rag.content.ContentMetadata
import dev.langchain4j.rag.content.retriever.ContentRetriever
import dev.langchain4j.rag.query.Query
import org.slf4j.LoggerFactory
import org.springframework.beans.factory.annotation.Value
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.stereotype.Component

/**
 * Custom [ContentRetriever] over `narrative_chunks` (DEV-025 — beta5's `PgVectorEmbeddingStore`
 * hardcodes an incompatible `embedding_id UUID/text` schema). Bean name `narrativeChunkContentRetriever`
 * is what `config.RagConfig`'s `retrievalAugmentor` bean wraps.
 *
 * The retrieval query casts to `halfvec(3072)` on both sides (ADR-013/DEV-028): a plain
 * `embedding <=> ?` silently bypasses `narrative_chunks_embedding_hnsw_idx` (seq scan instead of the
 * HNSW index) since plain-vector HNSW caps at 2000 dims. Verified by Track H5's `EXPLAIN ANALYZE` —
 * at the current ~3,500-row corpus size Postgres' planner still prefers a seq scan either way (the
 * table is too small for the index to pay off), but the cast is confirmed load-bearing: forcing
 * `enable_seqscan=off` shows only the cast form can use the index at all.
 *
 * Joins `sources` for `author`/`work`/`stance`: `narrative_chunks` itself only carries `source_id`.
 * Every one of `author`/`work`/`passage_ref`/`stance` is attached to the returned `Content`'s
 * `TextSegment` metadata — `RagConfig`'s `ContentInjector` (`metadataKeysToInclude`) is what actually
 * forwards these into the LLM's prompt; without it, `RagAgent` only ever sees raw chunk text and
 * fabricates citations from background knowledge instead (found live in Track H6).
 *
 * `minScore` is the Track H tuning knob (IMPLEMENTATION_PLAN.md §7); `maxResults` is the final
 * post-dedupe cap. The SQL `LIMIT` over-fetches by [OVERFETCH_MULTIPLIER] so that dropping rows to
 * `minScore` and to one row per `passage_ref` (DEV-034 — sub-chunks of oversized paragraphs share a
 * ref) still leaves up to `maxResults` distinct passages, not fewer.
 */
@Component
class NarrativeChunkContentRetriever(
    private val jdbcTemplate: JdbcTemplate,
    private val embeddingModel: EmbeddingModel,
    @Value("\${app.rag.max-results:5}") private val maxResults: Int,
    @Value("\${app.rag.min-score:0.65}") private val minScore: Double,
    private val debugCapture: DebugCapture,
) : ContentRetriever {

    override fun retrieve(query: Query): List<Content> {
        val queryVector = embeddingModel.embed(query.text()).content().vector()

        val rows = jdbcTemplate.query(
            RETRIEVAL_SQL,
            { rs, _ ->
                Row(
                    id = rs.getInt("id"),
                    content = rs.getString("content"),
                    sourceId = rs.getString("source_id"),
                    passageRef = rs.getString("passage_ref"),
                    author = rs.getString("author"),
                    work = rs.getString("work"),
                    stance = rs.getString("stance"),
                    score = rs.getDouble("score"),
                )
            },
            PGvector(queryVector),
            maxResults * OVERFETCH_MULTIPLIER,
        )

        val results = dedupeByPassageRef(rows.filter { it.score >= minScore }).take(maxResults)

        // Stage P2 Track B3: written unconditionally (cheap map builds) — QueryService only
        // *reads* this via DebugCapture.snapshot() when the request actually asked for debug.
        debugCapture.setRetrievedChunks(
            results.map { DebugInfo.ChunkRef(id = it.id, sourceId = it.sourceId, passageRef = it.passageRef, score = it.score) }
        )

        log.debug(
            "RAG retrieval for '{}': {} chunks, top score {}, passage_refs {}",
            query.text(),
            results.size,
            results.firstOrNull()?.score,
            results.map { it.passageRef },
        )

        return results.map { it.toContent() }
    }

    // Keeps the highest-scored row per passage_ref (rows already arrive ordered by score
    // descending); rows with no passage_ref are never considered duplicates of one another.
    private fun dedupeByPassageRef(rows: List<Row>): List<Row> {
        val seenRefs = mutableSetOf<String>()
        return rows.filter { row -> row.passageRef?.let(seenRefs::add) ?: true }
    }

    private data class Row(
        val id: Int,
        val content: String,
        val sourceId: String,
        val passageRef: String?,
        val author: String,
        val work: String,
        val stance: String,
        val score: Double,
    ) {
        fun toContent(): Content {
            val segmentMetadata = buildMap {
                put("source_id", sourceId)
                put("author", author)
                put("work", work)
                put("stance", stance)
                passageRef?.let { put("passage_ref", it) }
            }
            return Content.from(
                TextSegment.from(content, Metadata.from(segmentMetadata)),
                mapOf(ContentMetadata.SCORE to score),
            )
        }
    }

    companion object {
        private val log = LoggerFactory.getLogger(NarrativeChunkContentRetriever::class.java)

        private const val OVERFETCH_MULTIPLIER = 3

        // Cosine similarity = 1 - cosine distance. Ranking by the subquery's `distance` alias
        // (ascending = most similar first) computes the halfvec cast once and reuses it for both
        // ordering and the returned score, rather than repeating the cast expression twice.
        private val RETRIEVAL_SQL = """
            SELECT id, content, source_id, passage_ref, author, work, stance, 1 - distance AS score
            FROM (
                SELECT nc.id, nc.content, nc.source_id, nc.passage_ref, s.author, s.work, s.stance,
                       nc.embedding::halfvec(3072) <=> (?::vector(3072))::halfvec(3072) AS distance
                FROM narrative_chunks nc
                JOIN sources s ON s.id = nc.source_id
                ORDER BY distance
                LIMIT ?
            ) ranked
        """.trimIndent()
    }
}
