package com.blamezeus.coreapi.service

import com.blamezeus.coreapi.ai.ConflictProbe
import com.blamezeus.coreapi.ai.ConflictSynthesizer
import com.blamezeus.coreapi.conflict.ConflictLookup
import com.blamezeus.coreapi.domain.dto.QueryResponse
import com.blamezeus.coreapi.handler.MixedQueryHandler
import com.blamezeus.coreapi.handler.RagQueryHandler
import com.blamezeus.coreapi.handler.SqlQueryHandler
import com.blamezeus.coreapi.routing.QueryRouter
import com.blamezeus.coreapi.routing.RouteDecision
import org.slf4j.LoggerFactory
import org.springframework.stereotype.Service

// Central orchestrator — the only class that knows about all three handlers (SqlQueryHandler,
// RagQueryHandler, MixedQueryHandler) *plus* the router-independent conflict enrichment step
// (ADR-007 §5, Stage 7 Track E): after any handler answers, `enrich()` runs ConflictProbe ->
// ConflictLookup -> ConflictSynthesizer on top of the answer, writing only `conflicts[]` — never
// `answer`, `routeDecision`, `citations`, or `sqlGenerated` — and never letting an enrichment
// failure break the primary answer. Any router failure degrades to RAG (Stage 6 gave RAG a real
// handler, so that path now yields a genuine answer, not a placeholder).
@Service
class QueryService(
    private val queryRouter: QueryRouter,
    private val sqlQueryHandler: SqlQueryHandler,
    private val ragQueryHandler: RagQueryHandler,
    private val mixedQueryHandler: MixedQueryHandler,
    private val conflictProbe: ConflictProbe,
    private val conflictLookup: ConflictLookup,
    private val conflictSynthesizer: ConflictSynthesizer,
) {

    fun handle(question: String): QueryResponse {
        val route = try {
            queryRouter.classify(question)
        } catch (e: Exception) {
            log.warn("Router failed for '{}', defaulting to RAG: {}", question, e.message)
            RouteDecision.RAG
        }

        val answer = try {
            when (route) {
                RouteDecision.SQL -> handleSql(question)
                RouteDecision.RAG -> ragQueryHandler.handle(question)
                RouteDecision.MIXED -> mixedQueryHandler.handle(question)
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

        return enrich(answer, question)
    }

    // ADR-007 §5. Wraps the FINAL answer `handle()` is about to return — including the SQL-empty
    // -> RAG fallback (Track E3) — rather than each dispatch branch individually, so no path can
    // accidentally skip enrichment. Skips entirely when the primary answer already failed
    // (`serviceError`, since that's not a conflict to surface); otherwise runs the probe -> lookup
    // -> synthesize chain and copies only `conflicts[]` onto the existing answer. Any exception
    // anywhere in the chain is logged and swallowed — enrichment must never turn a good answer
    // into a failed one.
    private fun enrich(answer: QueryResponse, question: String): QueryResponse {
        if (answer.serviceError) return answer

        return try {
            val probe = conflictProbe.extract(question)
            log.debug("Conflict probe for '{}': subject='{}', claimType='{}'", question, probe.subject, probe.claimType)
            if (probe.claimType == NO_CLAIM_TYPE) return answer

            val claims = conflictLookup.find(probe.subject, probe.claimType)
            log.debug("Conflict lookup for subject='{}', claimType='{}': {} rows", probe.subject, probe.claimType, claims.size)
            if (claims.isEmpty()) return answer

            answer.copy(conflicts = conflictSynthesizer.synthesize(claims))
        } catch (e: Exception) {
            log.warn("Conflict enrichment failed for '{}': {}", question, e.message)
            answer
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

    companion object {
        private val log = LoggerFactory.getLogger(QueryService::class.java)

        // Stage 7 Track 0.2: the literal sentinel ConflictProbe emits when a question maps to no
        // modeled claim dimension — a plain string, never null (DEV: no null-vs-missing branch).
        private const val NO_CLAIM_TYPE = "none"
    }
}
