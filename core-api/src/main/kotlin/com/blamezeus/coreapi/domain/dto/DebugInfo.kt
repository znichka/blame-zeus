package com.blamezeus.coreapi.domain.dto

// Stage P2 Track A1 [DEVIATED - see DEVIATIONS.md #DEV-064]: opt-in debug surface attached to
// QueryResponse only when the request carries `debug: true`. Every field is defaulted so a
// partially-filled DebugCapture.snapshot() (a route that never touches SQL, a composer that never
// ran) still serializes cleanly instead of requiring every producer to populate every field.
data class DebugInfo(
    val probeSubject: String? = null,
    val probeClaimType: String? = null,
    val claimRowCount: Int = 0,
    val firstAttemptSql: String? = null,
    val sqlRows: List<Map<String, Any?>> = emptyList(),
    val retrievedChunks: List<ChunkRef> = emptyList(),
    val fallbackFromSqlToRag: Boolean = false,
    val composerSucceeded: Boolean = false,
    val draftAnswer: String? = null,
    // ADR-021 prompt-caching telemetry, summed across every chat call this request made (3-5 per
    // question). `cacheCreationTokens` is what a cache WRITE cost (~1.25x base input price);
    // `cacheReadTokens` is what was served FROM cache (~0.1x). Both staying 0 across repeated
    // identical questions is the empirical signal that the system prompt is below the chat model's
    // minimum cacheable prefix (4,096 tokens on Claude Haiku 4.5) — see ADR-021.
    val inputTokens: Int = 0,
    val cacheCreationTokens: Int = 0,
    val cacheReadTokens: Int = 0,
) {
    // Stage P2 Track B3 decision: `nc.id` was added to RETRIEVAL_SQL + the Row mapper, so `id` is
    // always populated by NarrativeChunkContentRetriever. Stays nullable for defensive
    // construction elsewhere (e.g. a partially-filled snapshot before any retrieval has run).
    data class ChunkRef(
        val id: Int? = null,
        val sourceId: String? = null,
        val passageRef: String? = null,
        val score: Double = 0.0,
    )
}
