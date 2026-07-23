package com.blamezeus.coreapi.handler

import com.blamezeus.coreapi.ai.RagAgent
import com.blamezeus.coreapi.ai.TextToSqlAgent
import com.blamezeus.coreapi.config.SchemaIntrospector
import com.blamezeus.coreapi.domain.dto.QueryResponse
import com.blamezeus.coreapi.routing.RouteDecision
import com.blamezeus.coreapi.safety.SqlSafetyValidator
import com.blamezeus.coreapi.service.DebugCapture
import org.slf4j.LoggerFactory
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.stereotype.Component

// TODO(Stage 8, Track A1): the generateSql -> stripMarkdownFence -> validate -> queryForList
// sequence is intentionally duplicated from SqlQueryHandler rather than extracted into a shared
// component — the shared surface is small and a PoC-stage extraction of already-shipped Stage 5
// code isn't worth the refactor risk (see docs/TODO-stage8.md Track A1).
@Component
class MixedQueryHandler(
    private val textToSqlAgent: TextToSqlAgent,
    private val schemaIntrospector: SchemaIntrospector,
    private val validator: SqlSafetyValidator,
    private val jdbcTemplate: JdbcTemplate,
    private val ragAgent: RagAgent,
    private val debugCapture: DebugCapture,
) {

    fun handle(question: String): QueryResponse {
        val sql = stripMarkdownFence(textToSqlAgent.generateSql(schemaIntrospector.get(), question))
        validator.validate(sql)
        log.debug("Generated SQL for '{}': {}", question, sql)

        val rows = jdbcTemplate.queryForList(sql)
        if (rows.isEmpty()) {
            log.info("Empty SQL filter for '{}' — injecting a no-matching-rows note and continuing to RAG", question)
        }
        // Q12's SQL step (Stage P2 Track B2) — the origin of its serviceError when it fails.
        debugCapture.setFirstAttemptSql(sql)
        debugCapture.setSqlRows(rows.take(DebugCapture.SQL_ROWS_CAP))

        val augmentedQuestion = buildAugmentedQuestion(question, rows)
        val ragResponse = ragAgent.answer(augmentedQuestion)

        return QueryResponse(
            answer = ragResponse.answer,
            routeDecision = RouteDecision.MIXED,
            citations = ragResponse.citations,
            conflicts = emptyList(),
            sqlGenerated = sql,
        )
    }

    // Same defensive fence-stripping as SqlQueryHandler — same model (routingModel), same risk.
    private fun stripMarkdownFence(sql: String): String {
        val trimmed = sql.trim()
        if (!trimmed.startsWith("```")) {
            return trimmed
        }
        return trimmed
            .removePrefix("```sql")
            .removePrefix("```")
            .removeSuffix("```")
            .trim()
    }

    private fun buildAugmentedQuestion(question: String, rows: List<Map<String, Any?>>): String {
        val factsBlock = if (rows.isEmpty()) {
            "- No matching rows found in structured data."
        } else {
            rows.joinToString("\n") { row ->
                "- " + row.values.joinToString(", ") { it?.toString() ?: "unknown" }
            }
        }
        return "Relevant structured facts:\n$factsBlock\n\nQuestion: $question"
    }

    companion object {
        private val log = LoggerFactory.getLogger(MixedQueryHandler::class.java)
    }
}
