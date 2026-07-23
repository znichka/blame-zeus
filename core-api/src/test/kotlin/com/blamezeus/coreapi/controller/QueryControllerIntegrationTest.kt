package com.blamezeus.coreapi.controller

import com.blamezeus.coreapi.AbstractContainerTest
import com.blamezeus.coreapi.domain.dto.Citation
import com.blamezeus.coreapi.domain.dto.ConflictEntry
import com.blamezeus.coreapi.domain.dto.DebugInfo
import com.blamezeus.coreapi.domain.dto.QueryRequest
import com.blamezeus.coreapi.domain.dto.QueryResponse
import com.blamezeus.coreapi.routing.RouteDecision
import com.blamezeus.coreapi.service.QueryService
import com.fasterxml.jackson.databind.ObjectMapper
import com.ninjasquad.springmockk.MockkBean
import io.mockk.every
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.http.MediaType
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.status

// Stage 9 Track E1 — proves the POST /api/v1/query JSON contract at the controller layer.
// QueryService is mocked (springmockk @MockkBean, same DEV-055 rationale as WebControllerTest):
// its own dispatch/enrichment logic is already covered by QueryServiceTest, and a real call here
// would reach a live @AiService, which TECH_GUARDRAILS forbids in tests.
@AutoConfigureMockMvc
class QueryControllerIntegrationTest : AbstractContainerTest() {

    @Autowired
    lateinit var mockMvc: MockMvc

    @Autowired
    lateinit var objectMapper: ObjectMapper

    @MockkBean
    lateinit var queryService: QueryService

    @Test
    fun `POST query returns 200 with a routeDecision in SQL RAG or MIXED for a normal question`() {
        val response = QueryResponse(
            answer = "Zeus, Hera, Poseidon, Demeter, Hestia, and Hades are children of Cronus.",
            routeDecision = RouteDecision.SQL,
            citations = listOf(Citation("Hesiod", "Theogony", "453-467")),
            conflicts = emptyList(),
            sqlGenerated = "SELECT name FROM entities WHERE ...",
        )
        every { queryService.handle("Which Olympians are children of Cronus?") } returns response

        mockMvc.perform(
            post("/api/v1/query")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(QueryRequest("Which Olympians are children of Cronus?")))
        )
            .andExpect(status().isOk)
            .andExpect(jsonPath("$.routeDecision").value("SQL"))
            .andExpect(jsonPath("$.answer").value(response.answer))
            .andExpect(jsonPath("$.conflictsInProse").value(false))
    }

    // ADR-015 Track E3: the unified composition shape -- answer carries inline [n] markers,
    // citations is the composer's deduped/ordered reference list, and conflictsInProse is present
    // and true so API consumers know the disagreement was woven into `answer` rather than living
    // only in the (still-populated) `conflicts[]` field.
    @Test
    fun `POST query for a woven conflict-shaped question returns prose with inline markers and conflictsInProse true`() {
        val response = QueryResponse(
            answer = "Homer says Zeus fathered Aphrodite [1], while Hesiod says she was born from sea foam [2].",
            routeDecision = RouteDecision.RAG,
            citations = listOf(
                Citation("Homer", "Iliad", "5.334-5.380"),
                Citation("Hesiod", "Theogony", "176-232"),
            ),
            conflicts = listOf(
                ConflictEntry("child of Zeus and Dione", "Homer", "Iliad", "5.334-5.380"),
                ConflictEntry("born from sea foam", "Hesiod", "Theogony", "176-232"),
            ),
            sqlGenerated = null,
            conflictsInProse = true,
        )
        every { queryService.handle("Who were Aphrodite's parents?") } returns response

        mockMvc.perform(
            post("/api/v1/query")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(QueryRequest("Who were Aphrodite's parents?")))
        )
            .andExpect(status().isOk)
            .andExpect(jsonPath("$.answer").value(org.hamcrest.Matchers.containsString("[1]")))
            .andExpect(jsonPath("$.answer").value(org.hamcrest.Matchers.containsString("[2]")))
            .andExpect(jsonPath("$.citations.length()").value(2))
            .andExpect(jsonPath("$.citations[0].author").value("Homer"))
            .andExpect(jsonPath("$.citations[1].author").value("Hesiod"))
            .andExpect(jsonPath("$.conflictsInProse").value(true))
            .andExpect(jsonPath("$.conflicts.length()").value(2))
    }

    // DEV-014: a conflict-shaped question surfaces conflicts[] via route-independent enrichment,
    // not via a CONFLICT route -- asserted directly on conflicts[], never on routeDecision.
    @Test
    fun `POST query for a conflict-shaped question returns non-empty conflicts regardless of route`() {
        val response = QueryResponse(
            answer = "Sources differ on Aphrodite's parentage.",
            routeDecision = RouteDecision.RAG,
            citations = emptyList(),
            conflicts = listOf(
                ConflictEntry("child of Zeus and Dione", "Homer", "Iliad", "5.334-5.380"),
                ConflictEntry("born from sea foam", "Hesiod", "Theogony", "176-232"),
            ),
            sqlGenerated = null,
        )
        every { queryService.handle("Who were Aphrodite's parents?") } returns response

        mockMvc.perform(
            post("/api/v1/query")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(QueryRequest("Who were Aphrodite's parents?")))
        )
            .andExpect(status().isOk)
            .andExpect(jsonPath("$.conflicts.length()").value(2))
            .andExpect(jsonPath("$.conflicts[0].sourceAuthor").value("Homer"))
            .andExpect(jsonPath("$.conflicts[1].sourceAuthor").value("Hesiod"))
    }

    // ADR-005 §Decision.3 (DEV-026): an empty SQL result falls back to RAG inside QueryService, so
    // by the time it reaches the controller it's already a coherent RAG answer, not a 500 or a
    // raw "no rows" placeholder.
    @Test
    fun `POST query for a question whose SQL filter is empty still returns 200 with a coherent answer`() {
        val response = QueryResponse(
            answer = "The texts don't directly address this, but here's what they say...",
            routeDecision = RouteDecision.RAG,
            citations = emptyList(),
            conflicts = emptyList(),
            sqlGenerated = null,
        )
        every { queryService.handle("Which Olympians are children of Nobody?") } returns response

        mockMvc.perform(
            post("/api/v1/query")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(QueryRequest("Which Olympians are children of Nobody?")))
        )
            .andExpect(status().isOk)
            .andExpect(jsonPath("$.serviceError").value(false))
            .andExpect(jsonPath("$.answer").value(response.answer))
    }

    @Test
    fun `POST query surfaces a service error as 200 with serviceError true, not a 500`() {
        val response = QueryResponse(
            answer = "The service is temporarily unavailable. Please try again later.",
            routeDecision = RouteDecision.RAG,
            citations = emptyList(),
            conflicts = emptyList(),
            sqlGenerated = null,
            serviceError = true,
        )
        every { queryService.handle("Why did Athena turn Arachne into a spider?") } returns response

        mockMvc.perform(
            post("/api/v1/query")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(QueryRequest("Why did Athena turn Arachne into a spider?")))
        )
            .andExpect(status().isOk)
            .andExpect(jsonPath("$.serviceError").value(true))
    }

    // Stage P2 Track D3: proves the controller forwards `request.debug` through to
    // QueryService.handle and that the wire contract stays byte-for-byte unchanged when absent.
    @Test
    fun `POST query with debug true returns a response body containing a debug object`() {
        val response = QueryResponse(
            answer = "Zeus rules Olympus.",
            routeDecision = RouteDecision.RAG,
            citations = emptyList(),
            conflicts = emptyList(),
            sqlGenerated = null,
            debug = DebugInfo(probeSubject = "Zeus", probeClaimType = "parentage", claimRowCount = 1),
        )
        every { queryService.handle("Who is Zeus?", true) } returns response

        mockMvc.perform(
            post("/api/v1/query")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(QueryRequest("Who is Zeus?", debug = true)))
        )
            .andExpect(status().isOk)
            .andExpect(jsonPath("$.debug").exists())
            .andExpect(jsonPath("$.debug.probeSubject").value("Zeus"))
    }

    @Test
    fun `POST query without a debug field omits the debug key entirely from the response body`() {
        val response = QueryResponse(
            answer = "Zeus rules Olympus.",
            routeDecision = RouteDecision.RAG,
            citations = emptyList(),
            conflicts = emptyList(),
            sqlGenerated = null,
        )
        every { queryService.handle("Who is Zeus?") } returns response

        mockMvc.perform(
            post("/api/v1/query")
                .contentType(MediaType.APPLICATION_JSON)
                .content(objectMapper.writeValueAsString(QueryRequest("Who is Zeus?")))
        )
            .andExpect(status().isOk)
            .andExpect(jsonPath("$.debug").doesNotExist())
    }
}
