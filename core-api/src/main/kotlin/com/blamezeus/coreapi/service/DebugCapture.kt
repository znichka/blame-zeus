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
}
