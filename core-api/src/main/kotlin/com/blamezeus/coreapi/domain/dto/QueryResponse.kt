package com.blamezeus.coreapi.domain.dto

import com.blamezeus.coreapi.routing.RouteDecision

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
)
