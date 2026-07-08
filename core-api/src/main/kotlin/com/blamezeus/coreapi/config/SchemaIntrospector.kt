package com.blamezeus.coreapi.config

import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.stereotype.Component

@Component
class SchemaIntrospector(private val jdbcTemplate: JdbcTemplate) {

    private val schemaPrompt: String by lazy { buildSchemaPrompt() }

    fun get(): String = schemaPrompt

    private fun buildSchemaPrompt(): String {
        val tables = listOf(
            "entities", "relationships", "myths", "myth_participants",
            "sources", "variant_claims", "narrative_chunks"
        )
        return tables.joinToString("\n") { table ->
            val columns = jdbcTemplate.queryForList(
                """SELECT column_name
                   FROM information_schema.columns
                   WHERE table_name = ? AND table_schema = 'public'
                   ORDER BY ordinal_position""",
                String::class.java,
                table
            )
            "$table(${columns.joinToString(", ")})"
        }
    }
}
