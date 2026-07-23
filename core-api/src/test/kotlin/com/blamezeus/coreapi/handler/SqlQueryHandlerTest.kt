package com.blamezeus.coreapi.handler

import com.blamezeus.coreapi.ai.TextToSqlAgent
import com.blamezeus.coreapi.config.SchemaIntrospector
import com.blamezeus.coreapi.domain.dto.Citation
import com.blamezeus.coreapi.routing.RouteDecision
import com.blamezeus.coreapi.safety.SqlSafetyValidator
import com.blamezeus.coreapi.service.DebugCapture
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import io.mockk.verifyOrder
import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import org.springframework.jdbc.core.JdbcTemplate

class SqlQueryHandlerTest {

    private val textToSqlAgent = mockk<TextToSqlAgent>()
    private val schemaIntrospector = mockk<SchemaIntrospector>()
    private val validator = mockk<SqlSafetyValidator>()
    private val jdbcTemplate = mockk<JdbcTemplate>()
    private val debugCapture = DebugCapture()

    private val handler = SqlQueryHandler(textToSqlAgent, schemaIntrospector, validator, jdbcTemplate, debugCapture)

    @Test
    fun `validates the exact generated SQL before executing it`() {
        every { schemaIntrospector.get() } returns "schema"
        every { textToSqlAgent.generateSql("schema", "question") } returns "SELECT name FROM entities"
        every { validator.validate("SELECT name FROM entities") } returns Unit
        every { jdbcTemplate.queryForList("SELECT name FROM entities") } returns listOf(mapOf("name" to "Zeus"))

        handler.handle("question")

        verifyOrder {
            validator.validate("SELECT name FROM entities")
            jdbcTemplate.queryForList("SELECT name FROM entities")
        }
    }

    @Test
    fun `a markdown-fenced SQL response is stripped before validation and execution`() {
        every { schemaIntrospector.get() } returns "schema"
        every { textToSqlAgent.generateSql(any(), any()) } returns "```sql\nSELECT name FROM entities\n```"
        every { validator.validate("SELECT name FROM entities") } returns Unit
        every { jdbcTemplate.queryForList("SELECT name FROM entities") } returns listOf(mapOf("name" to "Zeus"))

        val response = handler.handle("question")

        verify(exactly = 1) { validator.validate("SELECT name FROM entities") }
        verify(exactly = 1) { jdbcTemplate.queryForList("SELECT name FROM entities") }
        assertThat(response.sqlGenerated).isEqualTo("SELECT name FROM entities")
    }

    @Test
    fun `a bare (unlabelled) markdown fence around SQL is also stripped`() {
        every { schemaIntrospector.get() } returns "schema"
        every { textToSqlAgent.generateSql(any(), any()) } returns "```\nSELECT name FROM entities\n```"
        every { validator.validate("SELECT name FROM entities") } returns Unit
        every { jdbcTemplate.queryForList("SELECT name FROM entities") } returns listOf(mapOf("name" to "Zeus"))

        handler.handle("question")

        verify(exactly = 1) { validator.validate("SELECT name FROM entities") }
    }

    @Test
    fun `rejected SQL never reaches JdbcTemplate`() {
        every { schemaIntrospector.get() } returns "schema"
        every { textToSqlAgent.generateSql(any(), any()) } returns "DROP TABLE entities"
        every { validator.validate("DROP TABLE entities") } throws IllegalArgumentException("nope")

        assertThrows<IllegalArgumentException> { handler.handle("question") }

        verify(exactly = 0) { jdbcTemplate.queryForList(any<String>()) }
    }

    @Test
    fun `formats rows into an answer for the SQL route with sqlGenerated populated`() {
        every { schemaIntrospector.get() } returns "schema"
        every { textToSqlAgent.generateSql(any(), any()) } returns "SELECT name FROM entities"
        every { validator.validate(any()) } returns Unit
        every { jdbcTemplate.queryForList("SELECT name FROM entities") } returns
            listOf(mapOf("name" to "Zeus"), mapOf("name" to "Hera"))

        val response = handler.handle("Which Olympians are children of Cronus?")

        assertThat(response.routeDecision).isEqualTo(RouteDecision.SQL)
        assertThat(response.sqlGenerated).isEqualTo("SELECT name FROM entities")
        assertThat(response.answer).contains("Zeus").contains("Hera")
        assertThat(response.serviceError).isFalse()
    }

    @Test
    fun `formatAnswer emits column-named pairs, not a bare value join (ADR-015 Track C)`() {
        every { schemaIntrospector.get() } returns "schema"
        every { textToSqlAgent.generateSql(any(), any()) } returns "SELECT name, type, generation FROM entities"
        every { validator.validate(any()) } returns Unit
        every { jdbcTemplate.queryForList("SELECT name, type, generation FROM entities") } returns
            listOf(
                mapOf("name" to "Zeus", "type" to "olympian", "generation" to 1),
                mapOf("name" to "Hera", "type" to "olympian", "generation" to 1),
            )

        val response = handler.handle("Which Olympians are children of Cronus?")

        assertThat(response.answer).isEqualTo(
            "name=Zeus, type=olympian, generation=1; name=Hera, type=olympian, generation=1"
        )
    }

    @Test
    fun `extracts citations from rows carrying author, work and passage_ref columns`() {
        every { schemaIntrospector.get() } returns "schema"
        every { textToSqlAgent.generateSql(any(), any()) } returns
            "SELECT r.relation, s.author, s.work, s.passage_ref FROM relationships r JOIN sources s ON s.id = r.source_id"
        every { validator.validate(any()) } returns Unit
        every { jdbcTemplate.queryForList(any<String>()) } returns
            listOf(mapOf("relation" to "parent_of", "author" to "Apollodorus", "work" to "Bibliotheca", "passage_ref" to "1.1.1"))

        val response = handler.handle("question")

        assertThat(response.citations).containsExactly(
            Citation(author = "Apollodorus", work = "Bibliotheca", passageRef = "1.1.1")
        )
    }

    @Test
    fun `rows with no author or work columns produce no citations`() {
        every { schemaIntrospector.get() } returns "schema"
        every { textToSqlAgent.generateSql(any(), any()) } returns "SELECT type FROM entities WHERE name ILIKE 'Zeus'"
        every { validator.validate(any()) } returns Unit
        every { jdbcTemplate.queryForList(any<String>()) } returns listOf(mapOf("type" to "olympian"))

        val response = handler.handle("question")

        assertThat(response.citations).isEmpty()
        // An entities-only query has no source_id to recover — must NOT trigger a corrective retry.
        verify(exactly = 0) { textToSqlAgent.generateSqlWithAttribution(any(), any(), any()) }
    }

    @Test
    fun `DEV-057 -- extractCitations recognizes source_author and source_work aliases`() {
        every { schemaIntrospector.get() } returns "schema"
        val sql =
            "SELECT r.relation, s.author AS source_author, s.work AS source_work, s.passage_ref " +
                "FROM relationships r JOIN sources s ON s.id = r.source_id"
        every { textToSqlAgent.generateSql(any(), any()) } returns sql
        every { validator.validate(any()) } returns Unit
        every { jdbcTemplate.queryForList(sql) } returns
            listOf(mapOf("relation" to "parent_of", "source_author" to "Hesiod", "source_work" to "Theogony", "passage_ref" to "453"))

        val response = handler.handle("question")

        assertThat(response.citations).containsExactly(
            Citation(author = "Hesiod", work = "Theogony", passageRef = "453")
        )
        // Attribution was found on the first pass — no retry.
        verify(exactly = 0) { textToSqlAgent.generateSqlWithAttribution(any(), any(), any()) }
    }

    @Test
    fun `DEV-057 -- a relationships query returning no attribution triggers exactly one corrective regeneration`() {
        every { schemaIntrospector.get() } returns "schema"
        val firstSql = "SELECT child.name FROM relationships r JOIN entities child ON child.id = r.to_id WHERE r.relation = 'parent_of'"
        every { textToSqlAgent.generateSql("schema", "Which Olympians are children of Cronus?") } returns firstSql
        val retrySql =
            "SELECT child.name AS name, s.author AS author, s.work AS work, s.passage_ref AS passage_ref, s.stance AS stance " +
                "FROM relationships r JOIN entities child ON child.id = r.to_id JOIN sources s ON s.id = r.source_id"
        every {
            textToSqlAgent.generateSqlWithAttribution("schema", "Which Olympians are children of Cronus?", firstSql)
        } returns retrySql
        every { validator.validate(any()) } returns Unit
        every { jdbcTemplate.queryForList(firstSql) } returns
            listOf(mapOf("name" to "Zeus"), mapOf("name" to "Hera"))
        every { jdbcTemplate.queryForList(retrySql) } returns listOf(
            mapOf("name" to "Zeus", "author" to "Hesiod", "work" to "Theogony", "passage_ref" to "453", "stance" to "cosmological"),
            mapOf("name" to "Hera", "author" to "Hesiod", "work" to "Theogony", "passage_ref" to "453", "stance" to "cosmological"),
        )

        val response = handler.handle("Which Olympians are children of Cronus?")

        verify(exactly = 1) {
            textToSqlAgent.generateSqlWithAttribution("schema", "Which Olympians are children of Cronus?", firstSql)
        }
        assertThat(response.citations).containsExactly(
            Citation(author = "Hesiod", work = "Theogony", passageRef = "453", stance = "cosmological")
        )
        assertThat(response.sqlGenerated).isEqualTo(retrySql)
        assertThat(response.answer).contains("author=Hesiod")
    }

    @Test
    fun `DEV-057 -- a corrective regeneration that still yields no attribution falls back to the original result`() {
        every { schemaIntrospector.get() } returns "schema"
        val firstSql = "SELECT child.name FROM relationships r JOIN entities child ON child.id = r.to_id"
        every { textToSqlAgent.generateSql(any(), any()) } returns firstSql
        val retrySql = "SELECT child.name AS name FROM relationships r JOIN entities child ON child.id = r.to_id"
        every { textToSqlAgent.generateSqlWithAttribution(any(), any(), any()) } returns retrySql
        every { validator.validate(any()) } returns Unit
        every { jdbcTemplate.queryForList(firstSql) } returns listOf(mapOf("name" to "Zeus"))
        every { jdbcTemplate.queryForList(retrySql) } returns listOf(mapOf("name" to "Zeus"))

        val response = handler.handle("question")

        verify(exactly = 1) { textToSqlAgent.generateSqlWithAttribution(any(), any(), any()) }
        assertThat(response.citations).isEmpty()
        assertThat(response.sqlGenerated).isEqualTo(firstSql)
        assertThat(response.answer).isEqualTo("name=Zeus")
    }

    @Test
    fun `empty result falls back to a Stage 5 placeholder response, not a SQL error`() {
        every { schemaIntrospector.get() } returns "schema"
        every { textToSqlAgent.generateSql(any(), any()) } returns "SELECT name FROM entities WHERE name = 'Nobody'"
        every { validator.validate(any()) } returns Unit
        every { jdbcTemplate.queryForList(any<String>()) } returns emptyList()

        val response = handler.handle("question")

        assertThat(response.serviceError).isFalse()
        assertThat(response.answer).isNotBlank()
        assertThat(response.citations).isEmpty()
    }

    @Test
    fun `aggregate-zero single row (COUNT of zero) is treated as empty, not a real zero answer`() {
        every { schemaIntrospector.get() } returns "schema"
        every { textToSqlAgent.generateSql(any(), any()) } returns
            "SELECT COUNT(*) AS count FROM entities WHERE name = 'Nobody'"
        every { validator.validate(any()) } returns Unit
        every { jdbcTemplate.queryForList(any<String>()) } returns listOf(mapOf("count" to 0L))

        val response = handler.handle("question")

        assertThat(response.serviceError).isFalse()
        assertThat(response.answer).isNotBlank()
        assertThat(response.answer).doesNotContain("0")
    }

    @Test
    fun `aggregate-zero also covers a single all-null row (SUM over no matches)`() {
        every { schemaIntrospector.get() } returns "schema"
        every { textToSqlAgent.generateSql(any(), any()) } returns "SELECT SUM(1) AS total FROM entities WHERE name = 'Nobody'"
        every { validator.validate(any()) } returns Unit
        every { jdbcTemplate.queryForList(any<String>()) } returns listOf(mapOf("total" to null))

        val response = handler.handle("question")

        assertThat(response.answer).isNotBlank()
    }

    @Test
    fun `captures firstAttemptSql and sqlRows into DebugCapture on a normal SQL response (Stage P2 Track B1)`() {
        every { schemaIntrospector.get() } returns "schema"
        every { textToSqlAgent.generateSql(any(), any()) } returns "SELECT name FROM entities"
        every { validator.validate(any()) } returns Unit
        every { jdbcTemplate.queryForList("SELECT name FROM entities") } returns
            listOf(mapOf("name" to "Zeus"), mapOf("name" to "Hera"))

        val response = handler.handle("question")

        val snapshot = debugCapture.snapshot()
        assertThat(snapshot.firstAttemptSql).isEqualTo("SELECT name FROM entities")
        assertThat(snapshot.sqlRows).containsExactly(mapOf("name" to "Zeus"), mapOf("name" to "Hera"))
        // No behavior change: the response is unaffected by whether DebugCapture was populated.
        assertThat(response.answer).contains("Zeus").contains("Hera")
    }

    @Test
    fun `captures firstAttemptSql into DebugCapture even on the EMPTY_RESULT_ANSWER early return`() {
        every { schemaIntrospector.get() } returns "schema"
        every { textToSqlAgent.generateSql(any(), any()) } returns "SELECT name FROM entities WHERE name = 'Nobody'"
        every { validator.validate(any()) } returns Unit
        every { jdbcTemplate.queryForList(any<String>()) } returns emptyList()

        handler.handle("question")

        val snapshot = debugCapture.snapshot()
        assertThat(snapshot.firstAttemptSql).isEqualTo("SELECT name FROM entities WHERE name = 'Nobody'")
        assertThat(snapshot.sqlRows).isEmpty()
    }

    @Test
    fun `firstAttemptSql captured is the pre-retry SQL, not the DEV-057 attribution retry`() {
        every { schemaIntrospector.get() } returns "schema"
        val firstSql = "SELECT child.name FROM relationships r JOIN entities child ON child.id = r.to_id WHERE r.relation = 'parent_of'"
        every { textToSqlAgent.generateSql("schema", "Which Olympians are children of Cronus?") } returns firstSql
        val retrySql =
            "SELECT child.name AS name, s.author AS author, s.work AS work, s.passage_ref AS passage_ref, s.stance AS stance " +
                "FROM relationships r JOIN entities child ON child.id = r.to_id JOIN sources s ON s.id = r.source_id"
        every {
            textToSqlAgent.generateSqlWithAttribution("schema", "Which Olympians are children of Cronus?", firstSql)
        } returns retrySql
        every { validator.validate(any()) } returns Unit
        every { jdbcTemplate.queryForList(firstSql) } returns listOf(mapOf("name" to "Zeus"))
        every { jdbcTemplate.queryForList(retrySql) } returns listOf(
            mapOf("name" to "Zeus", "author" to "Hesiod", "work" to "Theogony", "passage_ref" to "453", "stance" to "cosmological"),
        )

        handler.handle("Which Olympians are children of Cronus?")

        assertThat(debugCapture.snapshot().firstAttemptSql).isEqualTo(firstSql)
    }

    @Test
    fun `a genuine single non-zero-value row is not treated as empty`() {
        every { schemaIntrospector.get() } returns "schema"
        every { textToSqlAgent.generateSql(any(), any()) } returns "SELECT COUNT(*) AS count FROM entities WHERE type = 'olympian'"
        every { validator.validate(any()) } returns Unit
        every { jdbcTemplate.queryForList(any<String>()) } returns listOf(mapOf("count" to 12L))

        val response = handler.handle("question")

        assertThat(response.answer).contains("12")
    }
}
