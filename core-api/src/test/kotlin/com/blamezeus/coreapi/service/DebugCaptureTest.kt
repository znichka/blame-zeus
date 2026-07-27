package com.blamezeus.coreapi.service

import com.blamezeus.coreapi.domain.dto.DebugInfo
import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.Test

// Stage P2 Track A5. Pure JVM, no Spring context, no DB -- DebugCapture is a plain ThreadLocal
// wrapper (DEV-064), not itself LLM- or DB-backed.
class DebugCaptureTest {

    private val debugCapture = DebugCapture()

    @Test
    fun `snapshot with nothing set returns an all-defaults DebugInfo without throwing`() {
        val snapshot = debugCapture.snapshot()

        assertThat(snapshot).isEqualTo(DebugInfo())
    }

    @Test
    fun `reset then set each field, snapshot returns them all`() {
        debugCapture.reset()

        debugCapture.setProbe("Aphrodite", "parentage", 2)
        debugCapture.setFirstAttemptSql("SELECT * FROM entities")
        debugCapture.setSqlRows(listOf(mapOf("name" to "Zeus")))
        debugCapture.setRetrievedChunks(
            listOf(DebugInfo.ChunkRef(id = 7, sourceId = "hesiod-theogony", passageRef = "188-200", score = 0.91))
        )
        debugCapture.setFallbackFromSqlToRag(true)
        debugCapture.setComposerSucceeded(true)
        debugCapture.setDraftAnswer("Hesiod says she was born from sea foam.")

        val snapshot = debugCapture.snapshot()

        assertThat(snapshot).isEqualTo(
            DebugInfo(
                probeSubject = "Aphrodite",
                probeClaimType = "parentage",
                claimRowCount = 2,
                firstAttemptSql = "SELECT * FROM entities",
                sqlRows = listOf(mapOf("name" to "Zeus")),
                retrievedChunks = listOf(
                    DebugInfo.ChunkRef(id = 7, sourceId = "hesiod-theogony", passageRef = "188-200", score = 0.91)
                ),
                fallbackFromSqlToRag = true,
                composerSucceeded = true,
                draftAnswer = "Hesiod says she was born from sea foam.",
            )
        )
    }

    @Test
    fun `addRetrievedChunk appends rather than replacing`() {
        val first = DebugInfo.ChunkRef(id = 1, sourceId = "homer-iliad", passageRef = "1.1-1.10", score = 0.8)
        val second = DebugInfo.ChunkRef(id = 2, sourceId = "homer-iliad", passageRef = "1.11-1.20", score = 0.75)

        debugCapture.addRetrievedChunk(first)
        debugCapture.addRetrievedChunk(second)

        assertThat(debugCapture.snapshot().retrievedChunks).containsExactly(first, second)
    }

    // ADR-021: one question makes 3-5 chat calls, so the per-request figure the debug surface
    // reports has to be the sum, not the last call's numbers.
    @Test
    fun `addTokenUsage accumulates across calls rather than overwriting`() {
        debugCapture.addTokenUsage(inputTokens = 300, cacheCreationTokens = 3200, cacheReadTokens = 0)
        debugCapture.addTokenUsage(inputTokens = 3350, cacheCreationTokens = 0, cacheReadTokens = 3200)

        val snapshot = debugCapture.snapshot()
        assertThat(snapshot.inputTokens).isEqualTo(3650)
        assertThat(snapshot.cacheCreationTokens).isEqualTo(3200)
        assertThat(snapshot.cacheReadTokens).isEqualTo(3200)
    }

    @Test
    fun `a second reset clears prior state, no bleed across simulated requests on the same thread`() {
        debugCapture.setProbe("Aphrodite", "parentage", 2)
        debugCapture.setFirstAttemptSql("SELECT * FROM entities")
        debugCapture.addTokenUsage(inputTokens = 3350, cacheCreationTokens = 0, cacheReadTokens = 3200)

        debugCapture.reset()

        assertThat(debugCapture.snapshot()).isEqualTo(DebugInfo())
    }
}
