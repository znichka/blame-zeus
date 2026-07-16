package com.blamezeus.coreapi.handler

import com.blamezeus.coreapi.ai.RagAgent
import com.blamezeus.coreapi.config.SchemaIntrospector
import com.blamezeus.coreapi.domain.dto.Citation
import com.blamezeus.coreapi.domain.dto.RagResponse
import com.blamezeus.coreapi.ai.TextToSqlAgent
import com.blamezeus.coreapi.routing.RouteDecision
import com.blamezeus.coreapi.safety.SqlSafetyValidator
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import io.mockk.verifyOrder
import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.Test
import org.junit.jupiter.api.assertThrows
import org.springframework.jdbc.core.JdbcTemplate

class MixedQueryHandlerTest {

    private val textToSqlAgent = mockk<TextToSqlAgent>()
    private val schemaIntrospector = mockk<SchemaIntrospector>()
    private val validator = mockk<SqlSafetyValidator>()
    private val jdbcTemplate = mockk<JdbcTemplate>()
    private val ragAgent = mockk<RagAgent>()

    private val handler = MixedQueryHandler(textToSqlAgent, schemaIntrospector, validator, jdbcTemplate, ragAgent)

    @Test
    fun `injects SQL row values and the original question into the augmented string passed to RagAgent`() {
        every { schemaIntrospector.get() } returns "schema"
        every { textToSqlAgent.generateSql("schema", "Which heroes had a divine parent and died at Troy?") } returns
            "SELECT name FROM entities WHERE type = 'hero'"
        every { validator.validate(any()) } returns Unit
        every { jdbcTemplate.queryForList(any<String>()) } returns
            listOf(mapOf("name" to "Achilles"), mapOf("name" to "Sarpedon"))
        every { ragAgent.answer(any()) } returns RagResponse(answer = "answer", citations = emptyList())

        handler.handle("Which heroes had a divine parent and died at Troy?")

        verify {
            ragAgent.answer(match { augmented ->
                augmented.contains("Achilles") &&
                    augmented.contains("Sarpedon") &&
                    augmented.contains("Which heroes had a divine parent and died at Troy?")
            })
        }
    }

    @Test
    fun `validates and executes the generated SQL before calling RagAgent`() {
        every { schemaIntrospector.get() } returns "schema"
        every { textToSqlAgent.generateSql(any(), any()) } returns "SELECT name FROM entities"
        every { validator.validate("SELECT name FROM entities") } returns Unit
        every { jdbcTemplate.queryForList("SELECT name FROM entities") } returns listOf(mapOf("name" to "Zeus"))
        every { ragAgent.answer(any()) } returns RagResponse(answer = "answer", citations = emptyList())

        handler.handle("question")

        verifyOrder {
            validator.validate("SELECT name FROM entities")
            jdbcTemplate.queryForList("SELECT name FROM entities")
            ragAgent.answer(any())
        }
    }

    @Test
    fun `maps the RagResponse into a MIXED QueryResponse with the generated SQL and no conflicts`() {
        every { schemaIntrospector.get() } returns "schema"
        every { textToSqlAgent.generateSql(any(), any()) } returns "SELECT name FROM entities"
        every { validator.validate(any()) } returns Unit
        every { jdbcTemplate.queryForList(any<String>()) } returns listOf(mapOf("name" to "Achilles"))
        every { ragAgent.answer(any()) } returns RagResponse(
            answer = "Achilles died at Troy.",
            citations = listOf(Citation(author = "Homer", work = "Iliad", passageRef = "22.359")),
        )

        val response = handler.handle("question")

        assertThat(response.answer).isEqualTo("Achilles died at Troy.")
        assertThat(response.routeDecision).isEqualTo(RouteDecision.MIXED)
        assertThat(response.citations).containsExactly(
            Citation(author = "Homer", work = "Iliad", passageRef = "22.359")
        )
        assertThat(response.sqlGenerated).isEqualTo("SELECT name FROM entities")
        assertThat(response.conflicts).isEmpty()
        assertThat(response.serviceError).isFalse()
    }

    @Test
    fun `an empty SQL filter injects a no-matching-rows note and still calls RagAgent exactly once`() {
        every { schemaIntrospector.get() } returns "schema"
        every { textToSqlAgent.generateSql(any(), any()) } returns "SELECT name FROM entities WHERE name = 'Nobody'"
        every { validator.validate(any()) } returns Unit
        every { jdbcTemplate.queryForList(any<String>()) } returns emptyList()
        every { ragAgent.answer(any()) } returns RagResponse(answer = "answer", citations = emptyList())

        val response = handler.handle("question")

        verify(exactly = 1) {
            ragAgent.answer(match { it.contains("No matching rows found in structured data") })
        }
        assertThat(response.routeDecision).isEqualTo(RouteDecision.MIXED)
    }

    @Test
    fun `a markdown-fenced SQL response is stripped before validation and execution`() {
        every { schemaIntrospector.get() } returns "schema"
        every { textToSqlAgent.generateSql(any(), any()) } returns "```sql\nSELECT name FROM entities\n```"
        every { validator.validate("SELECT name FROM entities") } returns Unit
        every { jdbcTemplate.queryForList("SELECT name FROM entities") } returns listOf(mapOf("name" to "Zeus"))
        every { ragAgent.answer(any()) } returns RagResponse(answer = "answer", citations = emptyList())

        val response = handler.handle("question")

        verify(exactly = 1) { validator.validate("SELECT name FROM entities") }
        assertThat(response.sqlGenerated).isEqualTo("SELECT name FROM entities")
    }

    @Test
    fun `a SqlSafetyValidator rejection propagates and RagAgent is never called`() {
        every { schemaIntrospector.get() } returns "schema"
        every { textToSqlAgent.generateSql(any(), any()) } returns "DROP TABLE entities"
        every { validator.validate("DROP TABLE entities") } throws IllegalArgumentException("nope")

        assertThrows<IllegalArgumentException> { handler.handle("question") }

        verify(exactly = 0) { jdbcTemplate.queryForList(any<String>()) }
        verify(exactly = 0) { ragAgent.answer(any()) }
    }
}
