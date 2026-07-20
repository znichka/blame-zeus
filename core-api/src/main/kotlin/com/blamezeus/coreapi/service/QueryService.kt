package com.blamezeus.coreapi.service

import com.blamezeus.coreapi.ai.AnswerComposer
import com.blamezeus.coreapi.ai.ConflictProbe
import com.blamezeus.coreapi.ai.ConflictSynthesizer
import com.blamezeus.coreapi.conflict.ConflictClaim
import com.blamezeus.coreapi.conflict.ConflictLookup
import com.blamezeus.coreapi.domain.dto.ConflictEntry
import com.blamezeus.coreapi.domain.dto.QueryResponse
import com.blamezeus.coreapi.handler.MixedQueryHandler
import com.blamezeus.coreapi.handler.RagQueryHandler
import com.blamezeus.coreapi.handler.SqlQueryHandler
import com.blamezeus.coreapi.routing.QueryRouter
import com.blamezeus.coreapi.routing.RouteDecision
import org.slf4j.LoggerFactory
import org.springframework.stereotype.Service

// Central orchestrator — the only class that knows about all three handlers (SqlQueryHandler,
// RagQueryHandler, MixedQueryHandler) plus the conflict-claims fetch and the final composition
// stage (ADR-015): route -> dispatch (DRAFT) -> fetchClaims (CLAIMS) -> answerComposer.compose
// (FINAL). Composition runs on every non-error route, weaving `conflicts` into `answer`; on
// composer failure, or for a `serviceError` draft, the pre-composition draft is returned unchanged
// alongside structured `conflicts[]` (still populated via ConflictSynthesizer, ADR-007's
// guarantee preserved) and `conflictsInProse = false`. Any router failure degrades to RAG.
@Service
class QueryService(
    private val queryRouter: QueryRouter,
    private val sqlQueryHandler: SqlQueryHandler,
    private val ragQueryHandler: RagQueryHandler,
    private val mixedQueryHandler: MixedQueryHandler,
    private val conflictProbe: ConflictProbe,
    private val conflictLookup: ConflictLookup,
    private val conflictSynthesizer: ConflictSynthesizer,
    private val answerComposer: AnswerComposer,
) {

    fun handle(question: String): QueryResponse {
        val route = try {
            queryRouter.classify(question)
        } catch (e: Exception) {
            log.warn("Router failed for '{}', defaulting to RAG: {}", question, e.message)
            RouteDecision.RAG
        }

        val draft = try {
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

        // ADR-015 Track D3: the claims fetch runs *before* the serviceError check, so a
        // serviceError draft still carries structured `conflicts[]` — a deliberate behavior
        // change from the old enrich(), which early-returned before ever probing.
        val claims = fetchClaims(question)
        val conflictEntries = synthesizeSafely(claims)

        if (draft.serviceError) {
            return draft.copy(conflicts = conflictEntries, conflictsInProse = false)
        }

        return try {
            val composed = answerComposer.compose(question, renderMaterial(draft), renderConflicts(claims))
            draft.copy(
                answer = composed.answer,
                citations = composed.citations,
                conflicts = conflictEntries,
                conflictsInProse = claims.isNotEmpty(),
            )
        } catch (e: Exception) {
            log.warn("Answer composition failed for '{}': {}", question, e.message)
            draft.copy(conflicts = conflictEntries, conflictsInProse = false)
        }
    }

    // ADR-015 Track D2 (formerly `enrich()`'s probe -> lookup half, ADR-007 §5): returns the
    // structured claims for the question instead of writing them onto the answer — composition
    // consumes them. Any exception anywhere in the probe -> lookup chain is logged and swallowed
    // to an empty list; a claims-fetch failure must never turn a good draft into a failed one.
    private fun fetchClaims(question: String): List<ConflictClaim> = try {
        val probe = conflictProbe.extract(question)
        log.debug("Conflict probe for '{}': subject='{}', claimType='{}'", question, probe.subject, probe.claimType)
        if (probe.claimType == NO_CLAIM_TYPE) {
            emptyList()
        } else {
            val claims = conflictLookup.find(probe.subject, probe.claimType)
            log.debug("Conflict lookup for subject='{}', claimType='{}': {} rows", probe.subject, probe.claimType, claims.size)
            claims
        }
    } catch (e: Exception) {
        log.warn("Conflict claim fetch failed for '{}': {}", question, e.message)
        emptyList()
    }

    // Computed once, independent of the compose try/catch below, so a ConflictSynthesizer failure
    // (DEV-051: a deterministic pure mapper, so this should be rare) degrades to an empty
    // conflicts[] rather than ever being retried or breaking composition.
    private fun synthesizeSafely(claims: List<ConflictClaim>): List<ConflictEntry> = try {
        conflictSynthesizer.synthesize(claims)
    } catch (e: Exception) {
        log.warn("Conflict synthesis failed: {}", e.message)
        emptyList()
    }

    // ADR-015 Track A3: material is built uniformly from the draft's own answer + citations, so
    // RAG/MIXED prose keeps its provenance and the composer can re-map every source to an [n]
    // marker; only SqlQueryHandler.formatAnswer needed to change (Track C) to give this line field
    // context.
    private fun renderMaterial(draft: QueryResponse): String {
        if (draft.citations.isEmpty()) return draft.answer
        val citationLines = draft.citations.joinToString("\n") { "- ${it.author}, ${it.work}, ${it.passageRef}" }
        return "${draft.answer}\n\nSources:\n$citationLines"
    }

    // ADR-015 Track A4: attributed claim lines, or the literal "none" (not an empty string) so the
    // composer prompt reads unambiguously when there is nothing to weave in.
    private fun renderConflicts(claims: List<ConflictClaim>): String =
        if (claims.isEmpty()) {
            NO_CONFLICTS
        } else {
            claims.joinToString("\n") { "${it.sourceAuthor}, ${it.sourceWork}, ${it.passageRef}: ${it.claimValue}" }
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

        // ADR-015 Track A4: the literal string passed to AnswerComposer when there are no claims
        // to weave in, distinct from an empty string so the prompt reads unambiguously.
        private const val NO_CONFLICTS = "none"
    }
}
