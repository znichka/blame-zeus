package com.blamezeus.coreapi.handler

import com.blamezeus.coreapi.ai.TextToSqlAgent
import com.blamezeus.coreapi.config.SchemaIntrospector
import com.blamezeus.coreapi.domain.dto.Citation
import com.blamezeus.coreapi.domain.dto.QueryResponse
import com.blamezeus.coreapi.routing.RouteDecision
import com.blamezeus.coreapi.safety.SqlSafetyValidator
import org.slf4j.LoggerFactory
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.stereotype.Component

@Component
class SqlQueryHandler(
    private val textToSqlAgent: TextToSqlAgent,
    private val schemaIntrospector: SchemaIntrospector,
    private val validator: SqlSafetyValidator,
    private val jdbcTemplate: JdbcTemplate,
) {

    fun handle(question: String): QueryResponse {
        val sql = stripMarkdownFence(textToSqlAgent.generateSql(schemaIntrospector.get(), question))
        validator.validate(sql)
        log.debug("Generated SQL for '{}': {}", question, sql)

        val rows = jdbcTemplate.queryForList(sql)
        if (rows.isEmpty() || isAggregateZero(rows)) {
            // TODO(Stage 6): wire real RAG fallback via RagQueryHandler (ADR-005 §Decision.3, DEV-026).
            // RagQueryHandler doesn't exist until Stage 6, so Stage 5 returns this placeholder instead.
            log.warn("Empty/aggregate-zero SQL result for '{}' — no RAG fallback until Stage 6", question)
            return QueryResponse(
                answer = "The structured data has no answer for this question.",
                routeDecision = RouteDecision.SQL,
                citations = emptyList(),
                conflicts = emptyList(),
                sqlGenerated = sql,
            )
        }

        return QueryResponse(
            answer = formatAnswer(rows),
            routeDecision = RouteDecision.SQL,
            citations = extractCitations(rows),
            conflicts = emptyList(),
            sqlGenerated = sql,
        )
    }

    // Despite the "no markdown fences" prompt instruction, the model occasionally wraps its
    // answer in ```sql ... ``` (or a bare ``` ... ```) anyway — strip defensively rather than
    // let SqlSafetyValidator reject an otherwise-valid query over a formatting slip.
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

    private fun formatAnswer(rows: List<Map<String, Any?>>): String =
        rows.joinToString("; ") { row -> row.values.joinToString(", ") { it?.toString() ?: "unknown" } }

    private fun extractCitations(rows: List<Map<String, Any?>>): List<Citation> =
        rows.mapNotNull { row ->
            val author = row.valueIgnoreCase("author") as? String
            val work = row.valueIgnoreCase("work") as? String
            if (author == null || work == null) {
                return@mapNotNull null
            }
            Citation(
                author = author,
                work = work,
                passageRef = row.valueIgnoreCase("passage_ref") as? String ?: "",
                stance = row.valueIgnoreCase("stance") as? String,
            )
        }.distinct()

    private fun Map<String, Any?>.valueIgnoreCase(key: String): Any? =
        entries.firstOrNull { it.key.equals(key, ignoreCase = true) }?.value

    // ADR-005 §Decision.3 amended by DEV-026: a single row whose values are all 0/NULL is an
    // aggregate-zero result (COUNT=0, SUM=NULL) — aggregations never return zero rows, so this
    // check catches what the rows.isEmpty() check above cannot.
    private fun isAggregateZero(rows: List<Map<String, Any?>>): Boolean =
        rows.size == 1 && rows[0].values.all(::isZeroOrNull)

    private fun isZeroOrNull(value: Any?): Boolean = when (value) {
        null -> true
        is Number -> value.toDouble() == 0.0
        else -> false
    }

    companion object {
        private val log = LoggerFactory.getLogger(SqlQueryHandler::class.java)
    }
}
