package com.blamezeus.coreapi.ai

import com.blamezeus.coreapi.AbstractContainerTest
import com.blamezeus.coreapi.service.DebugCapture
import com.pgvector.PGvector
import dev.langchain4j.rag.content.ContentMetadata
import dev.langchain4j.rag.query.Query
import io.mockk.every
import io.mockk.mockk
import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import dev.langchain4j.model.embedding.EmbeddingModel as LcEmbeddingModel
import dev.langchain4j.model.output.Response
import dev.langchain4j.data.embedding.Embedding
import org.springframework.jdbc.core.JdbcTemplate
import kotlin.math.acos
import kotlin.math.cos
import kotlin.math.sin

// Track B1 (TODO-stage6.md): narrative_chunks is never Flyway-seeded (only the offline Python
// ingestion pipeline writes rows), so a fresh Testcontainers DB starts with an empty table —
// no cleanup-vs-real-data conflict, but each test still clears its own rows in @AfterEach.
class NarrativeChunkContentRetrieverTest : AbstractContainerTest() {

    @Autowired
    lateinit var jdbcTemplate: JdbcTemplate

    private val dimensions = 3072
    private val queryVector = FloatArray(dimensions).also { it[0] = 1f }

    @AfterEach
    fun cleanup() {
        jdbcTemplate.update("DELETE FROM narrative_chunks")
    }

    @Test
    fun `orders by cosine similarity, caps at maxResults, drops below minScore, and dedupes by passage_ref`() {
        // scores are cos(angle) between each chunk's vector and queryVector
        insertChunk("row1 content", "ovid-metamorphoses", "1.1", vectorAtScore(1.00)) // exact match
        insertChunk("row2 content, same ref as row1", "ovid-metamorphoses", "1.1", vectorAtScore(0.95)) // dup ref, lower score -> deduped out
        insertChunk("row3 content", "ovid-metamorphoses", "2.2", vectorAtScore(0.90))
        insertChunk("row4 content", "ovid-metamorphoses", "3.3", vectorAtScore(0.85))
        insertChunk("row5 content", "ovid-metamorphoses", "4.4", vectorAtScore(0.80))
        insertChunk("row6 content", "ovid-metamorphoses", "5.5", vectorAtScore(0.75))
        insertChunk("row7 content", "ovid-metamorphoses", "7.7", vectorAtScore(0.70)) // 6th distinct ref clearing minScore -> cut by cap
        insertChunk("row8 content", "ovid-metamorphoses", "6.6", vectorAtScore(0.55)) // below minScore -> excluded

        val retriever = NarrativeChunkContentRetriever(
            jdbcTemplate, fixedEmbeddingModel(queryVector), maxResults = 5, minScore = 0.65, debugCapture = DebugCapture(),
        )

        val results = retriever.retrieve(Query.from("what happened"))

        assertThat(results).hasSize(5)
        assertThat(results.map { it.textSegment().metadata().getString("passage_ref") })
            .containsExactly("1.1", "2.2", "3.3", "4.4", "5.5")
        assertThat(results.map { it.textSegment().text() })
            .containsExactly("row1 content", "row3 content", "row4 content", "row5 content", "row6 content")
    }

    @Test
    fun `each returned Content carries source_id, author, work, stance, and passage_ref in metadata`() {
        insertChunk("row content", "ovid-metamorphoses", "6.129-6.145", vectorAtScore(1.00))

        val retriever = NarrativeChunkContentRetriever(
            jdbcTemplate, fixedEmbeddingModel(queryVector), maxResults = 5, minScore = 0.65, debugCapture = DebugCapture(),
        )

        val result = retriever.retrieve(Query.from("what happened")).single()

        assertThat(result.textSegment().metadata().getString("source_id")).isEqualTo("ovid-metamorphoses")
        assertThat(result.textSegment().metadata().getString("passage_ref")).isEqualTo("6.129-6.145")
        assertThat(result.textSegment().metadata().getString("author")).isEqualTo("Ovid")
        assertThat(result.textSegment().metadata().getString("work")).isEqualTo("Metamorphoses")
        assertThat(result.textSegment().metadata().getString("stance")).isEqualTo("poetic-myth")
        assertThat(result.metadata()[ContentMetadata.SCORE] as Double).isCloseTo(1.00, org.assertj.core.data.Offset.offset(1e-3))
    }

    @Test
    fun `captures retrievedChunks into DebugCapture with id, source_id, passage_ref and score (Stage P2 Track B3)`() {
        insertChunk("row content", "ovid-metamorphoses", "6.129-6.145", vectorAtScore(1.00))
        val debugCapture = DebugCapture()
        val retriever = NarrativeChunkContentRetriever(
            jdbcTemplate, fixedEmbeddingModel(queryVector), maxResults = 5, minScore = 0.65, debugCapture = debugCapture,
        )

        retriever.retrieve(Query.from("what happened"))

        val chunks = debugCapture.snapshot().retrievedChunks
        assertThat(chunks).hasSize(1)
        assertThat(chunks[0].id).isNotNull()
        assertThat(chunks[0].sourceId).isEqualTo("ovid-metamorphoses")
        assertThat(chunks[0].passageRef).isEqualTo("6.129-6.145")
        assertThat(chunks[0].score).isCloseTo(1.00, org.assertj.core.data.Offset.offset(1e-3))
    }

    @Test
    fun `returns an empty list when nothing clears minScore`() {
        insertChunk("orthogonal content", "ovid-metamorphoses", "9.9", vectorAtScore(0.0))

        val retriever = NarrativeChunkContentRetriever(
            jdbcTemplate, fixedEmbeddingModel(queryVector), maxResults = 5, minScore = 0.65, debugCapture = DebugCapture(),
        )

        val results = retriever.retrieve(Query.from("unrelated question"))

        assertThat(results).isEmpty()
    }

    private fun fixedEmbeddingModel(vector: FloatArray): LcEmbeddingModel {
        val embeddingModel = mockk<LcEmbeddingModel>()
        every { embeddingModel.embed(any<String>()) } returns Response.from(Embedding.from(vector))
        return embeddingModel
    }

    // A vector at the given cosine-similarity angle from queryVector = (1, 0, 0, ...): only the
    // first two dimensions vary, the rest stay zero on both sides.
    private fun vectorAtScore(score: Double): FloatArray {
        val angle = acos(score.coerceIn(-1.0, 1.0))
        return FloatArray(dimensions).also {
            it[0] = cos(angle).toFloat()
            it[1] = sin(angle).toFloat()
        }
    }

    private fun insertChunk(content: String, sourceId: String, passageRef: String, vector: FloatArray) {
        jdbcTemplate.update(
            """INSERT INTO narrative_chunks (content, embedding, source_id, passage_ref, embedding_model)
               VALUES (?, ?, ?, ?, ?)""",
            content,
            PGvector(vector),
            sourceId,
            passageRef,
            "text-embedding-3-large",
        )
    }
}
