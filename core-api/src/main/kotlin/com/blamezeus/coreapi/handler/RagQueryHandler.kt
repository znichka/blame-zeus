package com.blamezeus.coreapi.handler

import com.blamezeus.coreapi.ai.RagAgent
import com.blamezeus.coreapi.domain.dto.QueryResponse
import com.blamezeus.coreapi.routing.RouteDecision
import org.springframework.stereotype.Component

@Component
class RagQueryHandler(private val ragAgent: RagAgent) {

    fun handle(question: String): QueryResponse {
        val response = ragAgent.answer(question)

        return QueryResponse(
            answer = response.answer,
            routeDecision = RouteDecision.RAG,
            citations = response.citations,
            conflicts = emptyList(),
            sqlGenerated = null,
        )
    }
}
