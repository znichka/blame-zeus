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
        // [DEVIATED - see DEVIATIONS.md #DEV-090] ADR-020's joint-parentage carve-out lets
        // `WITH RECURSIVE` lineage legitimately branch (2 parents/generation), so a bounded-depth
        // traversal can return far more rows than before — a real gold-question regression (Q12,
        // "Achilles's divine lineage to Zeus") blew past the LLM's 300k-token request limit because
        // the FULL row set was being dumped into buildAugmentedQuestion's prompt text; only the
        // DebugCapture view was ever capped. Capping the actual prompt input to the same
        // SQL_ROWS_CAP the debug view already uses fixes both at once.
        // [DEVIATED - see DEVIATIONS.md #DEV-092] a flat row-count cap alone isn't enough: a
        // lineage traversal returns one row PER (ancestor, corroborating citation) pair, so a
        // heavily-corroborated ancestor (e.g. Cronus, cited by 5 sources) can exhaust the cap
        // before a later-sorted, still-uncited entity (e.g. Ouranos, alphabetically after Earth)
        // is ever reached — live-verified on Q9 after Track J5's entity merge. Deduplicating by
        // `name` first (no other field is used to build the prose material) fixes it.
        val cappedRows = dedupeByName(rows).take(DebugCapture.SQL_ROWS_CAP)
        debugCapture.setSqlRows(cappedRows)

        val augmentedQuestion = buildAugmentedQuestion(question, cappedRows)
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

    // [DEVIATED - see DEVIATIONS.md #DEV-092] keeps the FIRST row for each distinct `name` value,
    // dropping later rows that only differ by citation (source/passage) — those citations still
    // reach the user via RagAgent's own retrieval, not through this row set. A row without a
    // `name` column (case-insensitive) is never deduplicated against anything.
    private fun dedupeByName(rows: List<Map<String, Any?>>): List<Map<String, Any?>> {
        val seenNames = mutableSetOf<Any?>()
        return rows.filter { row ->
            val name = row.entries.firstOrNull { it.key.equals("name", ignoreCase = true) }?.value
            name == null || seenNames.add(name)
        }
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
