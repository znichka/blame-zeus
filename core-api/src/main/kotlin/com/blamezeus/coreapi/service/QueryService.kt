package com.blamezeus.coreapi.service

import com.blamezeus.coreapi.domain.dto.QueryResponse
import com.blamezeus.coreapi.handler.SqlQueryHandler
import com.blamezeus.coreapi.routing.QueryRouter
import com.blamezeus.coreapi.routing.RouteDecision
import org.slf4j.LoggerFactory
import org.springframework.stereotype.Service

// Central orchestrator. RAG/MIXED handlers land in Stages 6/8 — until then those routes
// (and any router failure, which degrades to RAG) get a clearly-marked placeholder response.
@Service
class QueryService(
    private val queryRouter: QueryRouter,
    private val sqlQueryHandler: SqlQueryHandler,
) {

    fun handle(question: String): QueryResponse {
        val route = try {
            queryRouter.classify(question)
        } catch (e: Exception) {
            log.warn("Router failed for '{}', defaulting to RAG: {}", question, e.message)
            RouteDecision.RAG
        }

        return try {
            when (route) {
                RouteDecision.SQL -> sqlQueryHandler.handle(question)
                // TODO(Stage 6/8): wire RagQueryHandler / MixedQueryHandler once they exist.
                RouteDecision.RAG, RouteDecision.MIXED -> placeholderResponse(route)
            }
        } catch (e: Exception) {
            log.error("Handler failed for route {} on '{}': {}", route, question, e.message)
            QueryResponse(
                answer = "The service is temporarily unavailable. Please try again later.",
                routeDecision = route,
                citations = emptyList(),
                conflicts = emptyList(),
                sqlGenerated = null,
                serviceError = true,
            )
        }
    }

    private fun placeholderResponse(route: RouteDecision): QueryResponse = QueryResponse(
        answer = "The $route route is not yet implemented.",
        routeDecision = route,
        citations = emptyList(),
        conflicts = emptyList(),
        sqlGenerated = null,
    )

    companion object {
        private val log = LoggerFactory.getLogger(QueryService::class.java)
    }
}
