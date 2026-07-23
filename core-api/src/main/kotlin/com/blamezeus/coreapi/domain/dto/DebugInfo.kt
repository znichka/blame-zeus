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
