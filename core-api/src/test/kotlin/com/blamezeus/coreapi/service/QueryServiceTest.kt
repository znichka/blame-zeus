package com.blamezeus.coreapi.service

import com.blamezeus.coreapi.domain.dto.QueryResponse
import com.blamezeus.coreapi.handler.RagQueryHandler
import com.blamezeus.coreapi.handler.SqlQueryHandler
import com.blamezeus.coreapi.routing.QueryRouter
import com.blamezeus.coreapi.routing.RouteDecision
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.Test

class QueryServiceTest {

    private val queryRouter = mockk<QueryRouter>()
    private val sqlQueryHandler = mockk<SqlQueryHandler>()
    private val ragQueryHandler = mockk<RagQueryHandler>()

    private val service = QueryService(queryRouter, sqlQueryHandler, ragQueryHandler)

    @Test
    fun `a SQL decision dispatches to SqlQueryHandler and nowhere else`() {
        every { queryRouter.classify("Which Olympians are children of Cronus?") } returns RouteDecision.SQL
        val sqlResponse = QueryResponse(
            answer = "Zeus, Hera",
            routeDecision = RouteDecision.SQL,
            citations = emptyList(),
            conflicts = emptyList(),
            sqlGenerated = "SELECT name FROM entities",
        )
        every { sqlQueryHandler.handle("Which Olympians are children of Cronus?") } returns sqlResponse

        val response = service.handle("Which Olympians are children of Cronus?")

        assertThat(response).isEqualTo(sqlResponse)
        verify(exactly = 1) { sqlQueryHandler.handle("Which Olympians are children of Cronus?") }
        verify(exactly = 0) { ragQueryHandler.handle(any()) }
    }

    @Test
    fun `a RAG decision dispatches to RagQueryHandler and nowhere else`() {
        every { queryRouter.classify("Why did Athena turn Arachne into a spider?") } returns RouteDecision.RAG
        val ragResponse = QueryResponse(
            answer = "Athena turned Arachne into a spider out of jealousy over her weaving skill.",
            routeDecision = RouteDecision.RAG,
            citations = emptyList(),
            conflicts = emptyList(),
            sqlGenerated = null,
        )
        every { ragQueryHandler.handle("Why did Athena turn Arachne into a spider?") } returns ragResponse

        val response = service.handle("Why did Athena turn Arachne into a spider?")

        assertThat(response).isEqualTo(ragResponse)
        verify(exactly = 1) { ragQueryHandler.handle("Why did Athena turn Arachne into a spider?") }
        verify(exactly = 0) { sqlQueryHandler.handle(any()) }
    }

    @Test
    fun `a router exception defaults to RAG and dispatches to RagQueryHandler for a real answer`() {
        every { queryRouter.classify(any()) } throws RuntimeException("router LLM unavailable")
        val ragResponse = QueryResponse(
            answer = "Athena turned Arachne into a spider out of jealousy over her weaving skill.",
            routeDecision = RouteDecision.RAG,
            citations = emptyList(),
            conflicts = emptyList(),
            sqlGenerated = null,
        )
        every { ragQueryHandler.handle(any()) } returns ragResponse

        val response = service.handle("Why did Athena turn Arachne into a spider?")

        assertThat(response).isEqualTo(ragResponse)
        verify(exactly = 1) { ragQueryHandler.handle("Why did Athena turn Arachne into a spider?") }
        verify(exactly = 0) { sqlQueryHandler.handle(any()) }
    }

    @Test
    fun `an empty SQL result falls back to RagQueryHandler (ADR-005 §Decision-3)`() {
        every { queryRouter.classify(any()) } returns RouteDecision.SQL
        val emptySqlResponse = QueryResponse(
            answer = SqlQueryHandler.EMPTY_RESULT_ANSWER,
            routeDecision = RouteDecision.SQL,
            citations = emptyList(),
            conflicts = emptyList(),
            sqlGenerated = "SELECT name FROM entities WHERE name = 'Nobody'",
        )
        every { sqlQueryHandler.handle(any()) } returns emptySqlResponse
        val ragResponse = QueryResponse(
            answer = "The texts don't directly address this, but here's what they say...",
            routeDecision = RouteDecision.RAG,
            citations = emptyList(),
            conflicts = emptyList(),
            sqlGenerated = null,
        )
        every { ragQueryHandler.handle(any()) } returns ragResponse

        val response = service.handle("Which Olympians are children of Nobody?")

        assertThat(response).isEqualTo(ragResponse)
        verify(exactly = 1) { sqlQueryHandler.handle("Which Olympians are children of Nobody?") }
        verify(exactly = 1) { ragQueryHandler.handle("Which Olympians are children of Nobody?") }
    }

    @Test
    fun `a genuine (non-empty) SQL answer does not trigger the RAG fallback`() {
        every { queryRouter.classify(any()) } returns RouteDecision.SQL
        val sqlResponse = QueryResponse(
            answer = "Zeus, Hera",
            routeDecision = RouteDecision.SQL,
            citations = emptyList(),
            conflicts = emptyList(),
            sqlGenerated = "SELECT name FROM entities",
        )
        every { sqlQueryHandler.handle(any()) } returns sqlResponse

        val response = service.handle("Which Olympians are children of Cronus?")

        assertThat(response).isEqualTo(sqlResponse)
        verify(exactly = 0) { ragQueryHandler.handle(any()) }
    }

    @Test
    fun `a MIXED decision gets a Stage 5 placeholder response, not an exception`() {
        every { queryRouter.classify(any()) } returns RouteDecision.MIXED

        val response = service.handle("Which heroes had a divine parent and died at Troy?")

        assertThat(response.routeDecision).isEqualTo(RouteDecision.MIXED)
        assertThat(response.serviceError).isFalse()
        assertThat(response.answer).isNotBlank()
        verify(exactly = 0) { sqlQueryHandler.handle(any()) }
        verify(exactly = 0) { ragQueryHandler.handle(any()) }
    }

    @Test
    fun `when the SQL handler throws, the response has serviceError true and a non-empty answer`() {
        every { queryRouter.classify(any()) } returns RouteDecision.SQL
        every { sqlQueryHandler.handle(any()) } throws RuntimeException("db unavailable")

        val response = service.handle("Which Olympians are children of Cronus?")

        assertThat(response.serviceError).isTrue()
        assertThat(response.answer).isNotBlank()
        assertThat(response.routeDecision).isEqualTo(RouteDecision.SQL)
    }

    @Test
    fun `when the RAG handler throws, the response has serviceError true and a non-empty answer`() {
        every { queryRouter.classify(any()) } returns RouteDecision.RAG
        every { ragQueryHandler.handle(any()) } throws RuntimeException("chat model unavailable")

        val response = service.handle("Why did Athena turn Arachne into a spider?")

        assertThat(response.serviceError).isTrue()
        assertThat(response.answer).isNotBlank()
        assertThat(response.routeDecision).isEqualTo(RouteDecision.RAG)
    }

    @Test
    fun `when both router and the resulting RagQueryHandler fail, the response still has serviceError true and a non-empty answer`() {
        every { queryRouter.classify(any()) } throws RuntimeException("router LLM unavailable")
        every { ragQueryHandler.handle(any()) } throws RuntimeException("chat model unavailable")

        val response = service.handle("Which Olympians are children of Cronus?")

        assertThat(response.serviceError).isTrue()
        assertThat(response.answer).isNotBlank()
        assertThat(response.routeDecision).isEqualTo(RouteDecision.RAG)
    }
}
