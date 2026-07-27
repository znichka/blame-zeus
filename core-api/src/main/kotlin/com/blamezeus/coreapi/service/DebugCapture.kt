package com.blamezeus.coreapi.service

import com.blamezeus.coreapi.domain.dto.DebugInfo
import org.springframework.stereotype.Component

// Stage P2 Track A4 [DEVIATED - see DEVIATIONS.md #DEV-064]: a plain singleton bean (NOT
// `@Scope("request")`) wrapping a ThreadLocal. NarrativeChunkContentRetriever is invoked deep
// inside LangChain4j's `retrievalAugmentor`, under `RagAgent.answer(...)`, on the same request
// thread but with no constructor-arg/param path back to QueryService — a ThreadLocal is the only
// mechanism that reaches across that boundary while keeping every producer's unit tests
// constructible with a plain `DebugCapture()` (no web/proxy context required). The whole pipeline
// is synchronous on the request thread, so a ThreadLocal is sufficient; QueryService's Track C
// funnel is responsible for `reset()` at entry and in a `finally` so nothing leaks across pooled
// request threads.
@Component
class DebugCapture {

    private class MutableState {
        var probeSubject: String? = null
        var probeClaimType: String? = null
        var claimRowCount: Int = 0
        var firstAttemptSql: String? = null
        var sqlRows: List<Map<String, Any?>> = emptyList()
        var retrievedChunks: List<DebugInfo.ChunkRef> = emptyList()
        var fallbackFromSqlToRag: Boolean = false
        var composerSucceeded: Boolean = false
        var draftAnswer: String? = null
        var inputTokens: Int = 0
        var cacheCreationTokens: Int = 0
        var cacheReadTokens: Int = 0
    }

    private val state = ThreadLocal.withInitial { MutableState() }

    fun reset() {
        state.remove()
    }

    fun snapshot(): DebugInfo {
        val s = state.get()
        return DebugInfo(
            probeSubject = s.probeSubject,
            probeClaimType = s.probeClaimType,
            claimRowCount = s.claimRowCount,
            firstAttemptSql = s.firstAttemptSql,
            sqlRows = s.sqlRows,
            retrievedChunks = s.retrievedChunks,
            fallbackFromSqlToRag = s.fallbackFromSqlToRag,
            composerSucceeded = s.composerSucceeded,
            draftAnswer = s.draftAnswer,
            inputTokens = s.inputTokens,
            cacheCreationTokens = s.cacheCreationTokens,
            cacheReadTokens = s.cacheReadTokens,
        )
    }

    fun setProbe(subject: String?, claimType: String?, rowCount: Int) {
        state.get().apply {
            probeSubject = subject
            probeClaimType = claimType
            claimRowCount = rowCount
        }
    }

    fun setFirstAttemptSql(sql: String?) {
        state.get().firstAttemptSql = sql
    }

    fun setSqlRows(rows: List<Map<String, Any?>>) {
        state.get().sqlRows = rows
    }

    fun setRetrievedChunks(chunks: List<DebugInfo.ChunkRef>) {
        state.get().retrievedChunks = chunks
    }

    fun addRetrievedChunk(chunk: DebugInfo.ChunkRef) {
        state.get().apply { retrievedChunks = retrievedChunks + chunk }
    }

    fun setFallbackFromSqlToRag(value: Boolean) {
        state.get().fallbackFromSqlToRag = value
    }

    fun setComposerSucceeded(value: Boolean) {
        state.get().composerSucceeded = value
    }

    fun setDraftAnswer(answer: String?) {
        state.get().draftAnswer = answer
    }

    // ADR-021: called once per chat call by CacheTelemetryListener, which runs on the request
    // thread inside the model call — the same ThreadLocal reach-across DEV-064 established for
    // NarrativeChunkContentRetriever. Accumulates rather than overwrites, because a single
    // question makes 3-5 chat calls and the useful number is the per-request total.
    fun addTokenUsage(inputTokens: Int, cacheCreationTokens: Int, cacheReadTokens: Int) {
        state.get().apply {
            this.inputTokens += inputTokens
            this.cacheCreationTokens += cacheCreationTokens
            this.cacheReadTokens += cacheReadTokens
        }
    }

    companion object {
        // Stage P2 Track B1/B2: shared cap so neither SqlQueryHandler nor MixedQueryHandler ever
        // stores more than a bounded preview of a SQL result in the debug surface.
        const val SQL_ROWS_CAP = 25
    }
}
