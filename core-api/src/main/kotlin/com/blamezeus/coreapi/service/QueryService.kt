package com.blamezeus.coreapi.service

import com.blamezeus.coreapi.domain.dto.QueryResponse
import com.blamezeus.coreapi.handler.RagQueryHandler
import com.blamezeus.coreapi.handler.SqlQueryHandler
import com.blamezeus.coreapi.routing.QueryRouter
import com.blamezeus.coreapi.routing.RouteDecision
import org.slf4j.LoggerFactory
import org.springframework.stereotype.Service

// Central orchestrator. The MIXED handler lands in Stage 8 — until then that route gets a
// clearly-marked placeholder response. Any router failure degrades to RAG (Stage 6 gave RAG a
// real handler, so that path now yields a genuine answer, not a placeholder).
@Service
class QueryService(
    private val queryRouter: QueryRouter,
    private val sqlQueryHandler: SqlQueryHandler,
    private val ragQueryHandler: RagQueryHandler,
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
                RouteDecision.SQL -> handleSql(question)
                RouteDecision.RAG -> ragQueryHandler.handle(question)
                // TODO(Stage 8): wire MixedQueryHandler once it exists.
                RouteDecision.MIXED -> placeholderResponse(route)
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

    // ADR-005 §Decision.3 (DEV-026): SQL returning no rows falls back to RAG entirely, rather than
    // surfacing the "structured data has no answer" placeholder to the user. Recognizing the
    // placeholder by its exposed constant (rather than SqlQueryHandler calling RagQueryHandler
    // itself) keeps QueryService as the only class that dispatches across handlers.
    private fun handleSql(question: String): QueryResponse {
        val sqlResponse = sqlQueryHandler.handle(question)
        if (sqlResponse.answer != SqlQueryHandler.EMPTY_RESULT_ANSWER) {
            return sqlResponse
        }
        log.info("SQL returned no rows for '{}', falling back to RAG", question)
        return ragQueryHandler.handle(question)
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
