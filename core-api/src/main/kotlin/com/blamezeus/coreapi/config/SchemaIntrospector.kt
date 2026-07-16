package com.blamezeus.coreapi.config

import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.stereotype.Component

/**
 * Builds the schema description injected into the text-to-SQL system prompt.
 *
 * Tables are enumerated from information_schema rather than hand-registered, so a table
 * added by a future migration is visible to the prompt without touching this class
 * (only [EXCLUDED_TABLES] is maintained by hand). Each table is described with column
 * types, foreign keys, CHECK constraints, and COMMENT ON text from the migrations;
 * [VOCABULARY_COLUMNS] additionally get their live DISTINCT values so the model uses
 * exact stored strings (e.g. 'married_to') instead of guessing synonyms.
 */
@Component
class SchemaIntrospector(private val jdbcTemplate: JdbcTemplate) {

    private val schemaPrompt: String by lazy { buildSchemaPrompt() }

    fun get(): String = schemaPrompt

    private fun buildSchemaPrompt(): String =
        applicationTables().joinToString("\n") { describeTable(it) }

    private fun applicationTables(): List<String> =
        jdbcTemplate.queryForList(
            """SELECT table_name
               FROM information_schema.tables
               WHERE table_schema = 'public' AND table_type = 'BASE TABLE'
               ORDER BY table_name""",
            String::class.java
        ).filterNot { it in EXCLUDED_TABLES }

    private fun describeTable(table: String): String {
        val lines = mutableListOf("$table(${columnList(table)})")
        tableComment(table)?.let { lines += "  -- $it" }
        columnComments(table).forEach { (column, comment) -> lines += "  -- $column: $comment" }
        checkClauses(table).forEach { lines += "  -- CHECK $it" }
        foreignKeys(table).forEach { lines += "  -- $it" }
        vocabularies(table).forEach { (column, values) ->
            lines += "  -- $column values: ${values.joinToString(", ") { "'$it'" }}"
        }
        return lines.joinToString("\n")
    }

    private fun columnList(table: String): String =
        jdbcTemplate.queryForList(
            """SELECT column_name || ' ' || COALESCE(NULLIF(data_type, 'USER-DEFINED'), udt_name)
               FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = ?
               ORDER BY ordinal_position""",
            String::class.java,
            table
        ).joinToString(", ")

    private fun tableComment(table: String): String? =
        jdbcTemplate.queryForObject(
            "SELECT obj_description(format('public.%I', ?::text)::regclass, 'pg_class')",
            String::class.java,
            table
        )

    private fun columnComments(table: String): List<Pair<String, String>> =
        jdbcTemplate.query(
            """SELECT column_name,
                      col_description(format('public.%I', table_name)::regclass, ordinal_position) AS comment
               FROM information_schema.columns
               WHERE table_schema = 'public' AND table_name = ?
               ORDER BY ordinal_position""",
            { rs, _ -> rs.getString("column_name") to rs.getString("comment") },
            table
        ).mapNotNull { (column, comment) -> comment?.let { column to it } }

    private fun checkClauses(table: String): List<String> =
        jdbcTemplate.queryForList(
            """SELECT cc.check_clause
               FROM information_schema.table_constraints tc
               JOIN information_schema.check_constraints cc
                 ON cc.constraint_schema = tc.constraint_schema AND cc.constraint_name = tc.constraint_name
               WHERE tc.table_schema = 'public' AND tc.table_name = ? AND tc.constraint_type = 'CHECK'
               ORDER BY cc.check_clause""",
            String::class.java,
            table
        ).filterNot { it.endsWith("IS NOT NULL") }

    private fun foreignKeys(table: String): List<String> =
        jdbcTemplate.queryForList(
            """SELECT kcu.column_name || ' references ' || ccu.table_name || '(' || ccu.column_name || ')'
               FROM information_schema.table_constraints tc
               JOIN information_schema.key_column_usage kcu
                 ON kcu.constraint_schema = tc.constraint_schema AND kcu.constraint_name = tc.constraint_name
               JOIN information_schema.constraint_column_usage ccu
                 ON ccu.constraint_schema = tc.constraint_schema AND ccu.constraint_name = tc.constraint_name
               WHERE tc.table_schema = 'public' AND tc.table_name = ? AND tc.constraint_type = 'FOREIGN KEY'
               ORDER BY kcu.column_name""",
            String::class.java,
            table
        )

    private fun vocabularies(table: String): List<Pair<String, List<String>>> =
        VOCABULARY_COLUMNS.filter { it.table == table }.mapNotNull { vocab ->
            // table/column come from the compile-time constant below, never from input.
            // Ordered by frequency (most common first), not alphabetically: extraction
            // produces a long tail of rare free-text values (e.g. relationships.relation
            // has 131 distinct strings post-DEV-040, most one-offs), so an alphabetical
            // LIMIT can silently drop the load-bearing canonical values (parent_of,
            // married_to, killed_by) in favor of alphabetically-earlier noise. Frequency
            // ordering keeps the values the model actually needs within any limit.
            val values = jdbcTemplate.queryForList(
                """SELECT ${vocab.column} FROM ${vocab.table}
                   GROUP BY ${vocab.column} ORDER BY count(*) DESC LIMIT $VOCABULARY_LIMIT""",
                String::class.java
            )
            if (values.isEmpty()) null else vocab.column to values
        }

    private data class VocabularyColumn(val table: String, val column: String)

    companion object {
        private val EXCLUDED_TABLES = setOf("flyway_schema_history")

        private val VOCABULARY_COLUMNS = listOf(
            VocabularyColumn("relationships", "relation"),
            VocabularyColumn("variant_claims", "claim_type"),
            // Small bounded enums surfaced as live values so the model uses exact stored casing
            // (e.g. 'olympian', not 'Olympian') instead of guessing — DEV-054.
            VocabularyColumn("entities", "type"),
            VocabularyColumn("sources", "stance"),
            VocabularyColumn("sources", "role"),
        )

        private const val VOCABULARY_LIMIT = 50
    }
}
