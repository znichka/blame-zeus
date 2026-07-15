package com.blamezeus.coreapi.safety

import org.springframework.stereotype.Component

/**
 * Gates LLM-generated SQL before it reaches `JdbcTemplate`. Read-only by construction:
 * only `SELECT`/`WITH` statements are allowed, and any embedded `;` is rejected outright
 * (blocks statement stacking regardless of what precedes it).
 */
@Component
class SqlSafetyValidator {

    fun validate(sql: String) {
        val trimmed = sql.trim()
        require(trimmed.isNotEmpty()) { "SQL must not be blank" }
        require(!trimmed.contains(';')) { "SQL must not contain ';': $sql" }

        val firstKeyword = trimmed.substringBefore(' ').trim()
        require(firstKeyword.equalsIgnoreCase("SELECT") || firstKeyword.equalsIgnoreCase("WITH")) {
            "Only SELECT/WITH statements are allowed, got: $sql"
        }

        DENIED_KEYWORDS.forEach { keyword ->
            require(!containsKeyword(trimmed, keyword)) { "SQL contains denied keyword '$keyword': $sql" }
        }
    }

    private fun containsKeyword(sql: String, keyword: String): Boolean =
        KEYWORD_BOUNDARY_REGEX.format(keyword).toRegex(RegexOption.IGNORE_CASE).containsMatchIn(sql)

    private fun String.equalsIgnoreCase(other: String): Boolean = this.equals(other, ignoreCase = true)

    companion object {
        private val DENIED_KEYWORDS = listOf("DROP", "DELETE", "INSERT", "UPDATE")
        private const val KEYWORD_BOUNDARY_REGEX = "\\b%s\\b"
    }
}
