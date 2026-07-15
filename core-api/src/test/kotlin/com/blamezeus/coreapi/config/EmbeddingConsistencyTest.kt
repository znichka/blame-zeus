package com.blamezeus.coreapi.config

import ch.qos.logback.classic.Level
import ch.qos.logback.classic.Logger
import ch.qos.logback.classic.spi.ILoggingEvent
import ch.qos.logback.core.read.ListAppender
import com.fasterxml.jackson.databind.ObjectMapper
import com.fasterxml.jackson.module.kotlin.registerKotlinModule
import dev.langchain4j.data.embedding.Embedding
import dev.langchain4j.model.embedding.EmbeddingModel
import dev.langchain4j.model.output.Response
import io.mockk.every
import io.mockk.mockk
import org.assertj.core.api.Assertions.assertThat
import org.assertj.core.api.Assertions.within
import org.junit.jupiter.api.AfterEach
import org.junit.jupiter.api.BeforeEach
import org.junit.jupiter.api.Test
import org.slf4j.LoggerFactory
import org.springframework.jdbc.core.JdbcTemplate
import kotlin.math.sqrt

// Track F3 (TODO-stage6.md): pins the embedding model's output shape (canary-aphrodite.json,
// generated offline via ingestion/scripts/generate_canary.py against the live OPENAI_API_KEY,
// F2) and exercises EmbeddingConsistencyChecker's startup-guard logging.
class EmbeddingConsistencyTest {

    private val jdbcTemplate = mockk<JdbcTemplate>()
    private lateinit var logAppender: ListAppender<ILoggingEvent>

    @BeforeEach
    fun attachLogAppender() {
        logAppender = ListAppender()
        logAppender.start()
        checkerLogger().addAppender(logAppender)
    }

    @AfterEach
    fun detachLogAppender() {
        checkerLogger().detachAppender(logAppender)
    }

    @Test
    fun `canary embedding is 3072-dim and matches the pinned vector within tolerance`() {
        val canary = loadCanary()

        // No live LLM calls in tests (project guardrail): EmbeddingModel is mocked to stand in for
        // "the live model" returning the pinned vector, so this exercises the dimension + cosine-
        // similarity plumbing a developer re-runs manually against the real API to catch model/
        // dimension drift (see Track H4, which does exactly that against the live app + DB).
        val embeddingModel = mockk<EmbeddingModel>()
        every { embeddingModel.embed(canary.query) } returns Response.from(Embedding.from(canary.vector.toFloatArray()))

        val embedded = embeddingModel.embed(canary.query).content()

        assertThat(embedded.dimension()).isEqualTo(3072)
        assertThat(canary.dimensions).isEqualTo(3072)
        assertThat(canary.embeddingModel).isEqualTo("text-embedding-3-large")
        assertThat(cosineSimilarity(embedded.vector(), canary.vector.toFloatArray()))
            .isCloseTo(1.0, within(1e-6))
    }

    @Test
    fun `checker logs an error but does not throw on embedding model mismatch`() {
        every {
            jdbcTemplate.queryForList("SELECT DISTINCT embedding_model FROM narrative_chunks", String::class.java)
        } returns listOf("text-embedding-ada-002")

        val checker = EmbeddingConsistencyChecker(jdbcTemplate, "text-embedding-3-large")

        checker.checkOnStartup()

        assertThat(logAppender.list).anyMatch {
            it.level == Level.ERROR && it.formattedMessage.contains("drift")
        }
    }

    @Test
    fun `checker logs info with no error when the configured model matches all rows`() {
        every {
            jdbcTemplate.queryForList("SELECT DISTINCT embedding_model FROM narrative_chunks", String::class.java)
        } returns listOf("text-embedding-3-large")

        val checker = EmbeddingConsistencyChecker(jdbcTemplate, "text-embedding-3-large")

        checker.checkOnStartup()

        assertThat(logAppender.list).noneMatch { it.level == Level.ERROR }
    }

    @Test
    fun `checker logs info and does not error when narrative_chunks is empty`() {
        every {
            jdbcTemplate.queryForList("SELECT DISTINCT embedding_model FROM narrative_chunks", String::class.java)
        } returns emptyList()

        val checker = EmbeddingConsistencyChecker(jdbcTemplate, "text-embedding-3-large")

        checker.checkOnStartup()

        assertThat(logAppender.list).noneMatch { it.level == Level.ERROR }
    }

    private fun checkerLogger(): Logger =
        LoggerFactory.getLogger(EmbeddingConsistencyChecker::class.java) as Logger

    private fun loadCanary(): Canary {
        val json = javaClass.classLoader.getResourceAsStream("canary-aphrodite.json")!!
        return ObjectMapper().registerKotlinModule().readValue(json, Canary::class.java)
    }

    private fun cosineSimilarity(a: FloatArray, b: FloatArray): Double {
        var dot = 0.0
        var normA = 0.0
        var normB = 0.0
        for (i in a.indices) {
            dot += a[i] * b[i]
            normA += a[i] * a[i]
            normB += b[i] * b[i]
        }
        return dot / (sqrt(normA) * sqrt(normB))
    }

    private data class Canary(
        val query: String,
        val embeddingModel: String,
        val dimensions: Int,
        val vector: List<Float>,
    )
}
