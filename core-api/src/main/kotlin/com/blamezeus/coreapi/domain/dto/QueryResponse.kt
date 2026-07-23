package com.blamezeus.coreapi.domain.dto

import com.blamezeus.coreapi.routing.RouteDecision
import com.fasterxml.jackson.annotation.JsonInclude

data class QueryResponse(
    val answer: String,
    val routeDecision: RouteDecision?,
    val citations: List<Citation>,
    val conflicts: List<ConflictEntry>,
    val sqlGenerated: String?,
    val serviceError: Boolean = false,
    // ADR-015 Track D0/E1: whether AnswerComposer successfully wove `conflicts` into `answer`.
    // Defaults false so every pre-existing construction site (handlers, the serviceError branch)
    // compiles unchanged and defaults to the safe "not woven" state.
    val conflictsInProse: Boolean = false,
    // Stage P2 Track A3 [DEVIATED - see DEVIATIONS.md #DEV-064]: trailing + nullable + NON_NULL so
    // the wire contract is byte-for-byte unchanged whenever `debug` was absent/false on the request.
    @field:JsonInclude(JsonInclude.Include.NON_NULL)
    val debug: DebugInfo? = null,
)
