package com.blamezeus.coreapi.domain.dto

import com.blamezeus.coreapi.routing.RouteDecision

data class QueryResponse(
    val answer: String,
    val routeDecision: RouteDecision?,
    val citations: List<Citation>,
    val conflicts: List<ConflictEntry>,
    val sqlGenerated: String?,
    val serviceError: Boolean = false,
)
