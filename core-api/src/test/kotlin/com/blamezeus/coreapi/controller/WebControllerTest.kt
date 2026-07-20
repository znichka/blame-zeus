package com.blamezeus.coreapi.controller

import com.blamezeus.coreapi.AbstractContainerTest
import com.blamezeus.coreapi.domain.dto.Citation
import com.blamezeus.coreapi.domain.dto.ConflictEntry
import com.blamezeus.coreapi.domain.dto.QueryResponse
import com.blamezeus.coreapi.routing.RouteDecision
import com.blamezeus.coreapi.service.QueryService
import com.ninjasquad.springmockk.MockkBean
import io.mockk.every
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.content
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.model
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.status

// QueryService is mocked (springmockk @MockkBean) rather than exercised for real: TECH_GUARDRAILS
// forbids live LLM calls in tests, and QueryService's own dispatch/enrichment logic is already
// covered by QueryServiceTest. This test only proves WebController's wiring and index.html's
// rendering of a real QueryResponse shape.
@AutoConfigureMockMvc
class WebControllerTest : AbstractContainerTest() {

    @Autowired
    lateinit var mockMvc: MockMvc

    @MockkBean
    lateinit var queryService: QueryService

    @Test
    fun `GET root renders the empty query form with no response attribute`() {
        mockMvc.perform(get("/"))
            .andExpect(status().isOk)
            .andExpect(content().contentTypeCompatibleWith("text/html"))
            .andExpect(content().string(org.hamcrest.Matchers.containsString("<form")))
            .andExpect(content().string(org.hamcrest.Matchers.containsString("name=\"question\"")))
            .andExpect(model().attributeDoesNotExist("response"))
    }

    @Test
    fun `POST web query renders the answer and route badge for a real QueryResponse`() {
        val response = QueryResponse(
            answer = "Zeus, Hera, Poseidon, Demeter, Hestia, and Hades are children of Cronus.",
            routeDecision = RouteDecision.SQL,
            citations = listOf(Citation("Hesiod", "Theogony", "453-467")),
            conflicts = emptyList(),
            sqlGenerated = "SELECT name FROM entities WHERE ...",
        )
        every { queryService.handle("Which Olympians are children of Cronus?") } returns response

        mockMvc.perform(
            post("/web/query").param("question", "Which Olympians are children of Cronus?")
        )
            .andExpect(status().isOk)
            .andExpect(content().contentTypeCompatibleWith("text/html"))
            .andExpect(model().attributeExists("response"))
            .andExpect(content().string(org.hamcrest.Matchers.containsString("SQL")))
            .andExpect(content().string(org.hamcrest.Matchers.containsString("Zeus")))
            .andExpect(content().string(org.hamcrest.Matchers.containsString("Hesiod, Theogony")))
            .andExpect(content().string(org.hamcrest.Matchers.containsString("Show generated SQL")))
    }

    @Test
    fun `POST web query shows the error banner and hides the answer when serviceError is true`() {
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
            post("/web/query").param("question", "Why did Athena turn Arachne into a spider?")
        )
            .andExpect(status().isOk)
            .andExpect(content().string(org.hamcrest.Matchers.containsString("Something went wrong")))
            .andExpect(content().string(org.hamcrest.Matchers.not(org.hamcrest.Matchers.containsString(response.answer))))
    }

    @Test
    fun `ADR-015 Track E -- POST web query shows the fallback Sources-disagree box when conflictsInProse is false`() {
        val response = QueryResponse(
            answer = "Sources differ on Aphrodite's parentage.",
            routeDecision = RouteDecision.RAG,
            citations = emptyList(),
            conflicts = listOf(
                ConflictEntry("child of Zeus and Dione", "Homer", "Iliad", "5.334-5.380"),
                ConflictEntry("born from sea foam", "Hesiod", "Theogony", "176-232"),
            ),
            sqlGenerated = null,
            conflictsInProse = false,
        )
        every { queryService.handle("Who were Aphrodite's parents?") } returns response

        mockMvc.perform(post("/web/query").param("question", "Who were Aphrodite's parents?"))
            .andExpect(status().isOk)
            .andExpect(content().string(org.hamcrest.Matchers.containsString("Sources disagree")))
            .andExpect(content().string(org.hamcrest.Matchers.containsString("Homer, Iliad: child of Zeus and Dione")))
            .andExpect(content().string(org.hamcrest.Matchers.containsString("Hesiod, Theogony: born from sea foam")))
    }

    @Test
    fun `ADR-015 Track E -- POST web query hides the Sources-disagree box when conflictsInProse is true`() {
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

        mockMvc.perform(post("/web/query").param("question", "Who were Aphrodite's parents?"))
            .andExpect(status().isOk)
            .andExpect(content().string(org.hamcrest.Matchers.containsString("Homer says Zeus fathered Aphrodite [1]")))
            .andExpect(content().string(org.hamcrest.Matchers.not(org.hamcrest.Matchers.containsString("Sources disagree"))))
    }
}
