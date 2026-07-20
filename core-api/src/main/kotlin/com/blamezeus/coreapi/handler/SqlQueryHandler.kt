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
        val (sql, rows) = runSql(textToSqlAgent.generateSql(schemaIntrospector.get(), question), question)
        if (rows.isEmpty() || isAggregateZero(rows)) {
            // QueryService recognizes EMPTY_RESULT_ANSWER and falls back to RagQueryHandler
            // (ADR-005 §Decision.3, DEV-026) — this handler stays decoupled from RagQueryHandler;
            // QueryService is the only class that dispatches across handlers.
            log.info("Empty/aggregate-zero SQL result for '{}' — QueryService will fall back to RAG", question)
            return QueryResponse(
                answer = EMPTY_RESULT_ANSWER,
                routeDecision = RouteDecision.SQL,
                citations = emptyList(),
                conflicts = emptyList(),
                sqlGenerated = sql,
            )
        }

        var finalSql = sql
        var finalRows = rows
        var citations = extractCitations(rows)

        // [DEVIATED - see DEVIATIONS.md #DEV-057] Corrective regeneration: a query that read an
        // attribution-bearing table yet projected no source columns (the model tends to SELECT only
        // the names the question asked for) leaves the answer uncitable. Re-ask ONCE, forcing the
        // mandatory projection, and adopt the retry only if it actually yields citations — never
        // worse than the original result otherwise. Attribution-less entity-attribute queries
        // (entities has no source_id) legitimately don't match this regex and are left untouched.
        if (citations.isEmpty() && readsAttributionTable(sql)) {
            log.info("SQL for '{}' read an attribution-bearing table but projected no sources — regenerating once", question)
            val (retrySql, retryRows) = runSql(
                textToSqlAgent.generateSqlWithAttribution(schemaIntrospector.get(), question, sql),
                question,
            )
            val retryCitations = extractCitations(retryRows)
            if (retryRows.isNotEmpty() && !isAggregateZero(retryRows) && retryCitations.isNotEmpty()) {
                finalSql = retrySql
                finalRows = retryRows
                citations = retryCitations
            }
        }

        return QueryResponse(
            answer = formatAnswer(finalRows),
            routeDecision = RouteDecision.SQL,
            citations = citations,
            conflicts = emptyList(),
            sqlGenerated = finalSql,
        )
    }

    // Shared strip → validate → execute path, reused by the primary query and the DEV-057 retry so
    // both go through SqlSafetyValidator identically before touching the DB.
    private fun runSql(rawSql: String, question: String): Pair<String, List<Map<String, Any?>>> {
        val sql = stripMarkdownFence(rawSql)
        validator.validate(sql)
        log.debug("Generated SQL for '{}': {}", question, sql)
        return sql to jdbcTemplate.queryForList(sql)
    }

    // [DEVIATED - see DEVIATIONS.md #DEV-057] Only relationships/variant_claims carry source_id, so
    // only those queries can be repaired into carrying attribution; word-boundary match mirrors
    // SqlSafetyValidator's token-matching style.
    private fun readsAttributionTable(sql: String): Boolean = ATTRIBUTION_TABLE_REGEX.containsMatchIn(sql)

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

    // ADR-015 Track C: column-named so AnswerComposer's `material` carries field context
    // ("name=Zeus, type=olympian, generation=1") instead of a bare value-only join — the composer
    // is what turns this into user-facing prose now, not this handler.
    private fun formatAnswer(rows: List<Map<String, Any?>>): String =
        rows.joinToString("; ") { row ->
            row.entries.joinToString(", ") { (key, value) -> "$key=${value?.toString() ?: "unknown"}" }
        }

    private fun extractCitations(rows: List<Map<String, Any?>>): List<Citation> =
        rows.mapNotNull { row ->
            // [DEVIATED - see DEVIATIONS.md #DEV-057] accept `source_author`/`source_work` alias
            // drift in addition to the canonical `author`/`work` labels.
            val author = row.valueIgnoreCase("author", "source_author") as? String
            val work = row.valueIgnoreCase("work", "source_work") as? String
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

    // Returns the value of the first of `keys` that matches a column label (case-insensitive); a
    // single key preserves the original lookup, extra keys cover alias synonyms.
    private fun Map<String, Any?>.valueIgnoreCase(vararg keys: String): Any? {
        for (key in keys) {
            val entry = entries.firstOrNull { it.key.equals(key, ignoreCase = true) }
            if (entry != null) return entry.value
        }
        return null
    }

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

        // [DEVIATED - see DEVIATIONS.md #DEV-057] the only two source_id-bearing tables; a query
        // touching either can be regenerated to carry attribution.
        private val ATTRIBUTION_TABLE_REGEX = Regex("\\b(relationships|variant_claims)\\b", RegexOption.IGNORE_CASE)

        // Exposed so QueryService can recognize this specific placeholder and re-dispatch to RAG
        // (ADR-005 §Decision.3, DEV-026) without either handler depending on the other.
        const val EMPTY_RESULT_ANSWER = "The structured data has no answer for this question."
    }
}
