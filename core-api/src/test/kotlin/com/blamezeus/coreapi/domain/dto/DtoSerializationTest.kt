package com.blamezeus.coreapi.domain.dto

import com.blamezeus.coreapi.routing.RouteDecision
import com.fasterxml.jackson.module.kotlin.jacksonObjectMapper
import com.fasterxml.jackson.module.kotlin.readValue
import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.Test

// Locks in the wire contract from IMPLEMENTATION_PLAN.md §5/§7 (camelCase field names,
// e.g. "routeDecision"/"sqlGenerated"/"serviceError", not snake_case) — RagAgent (Stage 6)
// relies on LangChain4j/Jackson deserializing an LLM-produced JSON blob into RagResponse,
// so this contract has to hold before any @AiService is wired up.
class DtoSerializationTest {

    private val mapper = jacksonObjectMapper()

    @Test
    fun `QueryResponse serializes with the documented camelCase field names`() {
        val response = QueryResponse(
            answer = "Hesiod and Homer disagree on Aphrodite's parentage.",
            routeDecision = RouteDecision.RAG,
            citations = listOf(Citation("Hesiod", "Theogony", "188-200", "cosmological")),
            conflicts = listOf(ConflictEntry("Born from sea foam...", "Hesiod", "Theogony", "188-200")),
            sqlGenerated = null,
            serviceError = false,
        )

        val json = mapper.readTree(mapper.writeValueAsString(response))

        assertThat(json["answer"].asText()).isEqualTo(response.answer)
        assertThat(json["routeDecision"].asText()).isEqualTo("RAG")
        assertThat(json["citations"][0]["passageRef"].asText()).isEqualTo("188-200")
        assertThat(json["conflicts"][0]["sourceAuthor"].asText()).isEqualTo("Hesiod")
        assertThat(json["conflicts"][0]["passageRef"].asText()).isEqualTo("188-200")
        assertThat(json.has("sqlGenerated")).isTrue()
        assertThat(json["serviceError"].asBoolean()).isFalse()
    }

    @Test
    fun `ConflictEntry deserializes without a passageRef when the row predates provenance tracking`() {
        // Stage 7 Track A1/DEV-051: passageRef is nullable — some hand-authored variant_claims
        // rows may not carry it, and the enrichment fetch must not choke on its absence.
        val parsed: ConflictEntry = mapper.readValue(
            """{"claimValue": "Born from sea foam...", "sourceAuthor": "Hesiod", "sourceWork": "Theogony"}"""
        )

        assertThat(parsed.passageRef).isNull()
    }

    @Test
    fun `RagResponse deserializes from an LLM-shaped JSON blob missing optional fields`() {
        // Mirrors the exact shape RagAgent's @SystemMessage instructs the model to
        // return (IMPLEMENTATION_PLAN.md §5) — no "stance" key at all.
        val json = """
            {"answer": "Zeus turned Lycaon into a wolf.",
             "citations": [{"author": "Ovid", "work": "Metamorphoses", "passageRef": "1.230"}]}
        """.trimIndent()

        val parsed: RagResponse = mapper.readValue(json)

        assertThat(parsed.answer).isEqualTo("Zeus turned Lycaon into a wolf.")
        assertThat(parsed.citations).hasSize(1)
        assertThat(parsed.citations[0].stance).isNull()
    }

    @Test
    fun `QueryRequest deserializes from a bare question field`() {
        val parsed: QueryRequest = mapper.readValue("""{"question": "Who is Zeus?"}""")
        assertThat(parsed.question).isEqualTo("Who is Zeus?")
    }

    @Test
    fun `QueryResponse with a null routeDecision and sqlGenerated round-trips`() {
        val response = QueryResponse(
            answer = "No answer available.",
            routeDecision = null,
            citations = emptyList(),
            conflicts = emptyList(),
            sqlGenerated = null,
            serviceError = true,
        )

        val roundTripped: QueryResponse = mapper.readValue(mapper.writeValueAsString(response))

        assertThat(roundTripped).isEqualTo(response)
    }
}
