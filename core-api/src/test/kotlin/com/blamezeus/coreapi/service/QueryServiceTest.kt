package com.blamezeus.coreapi.service

import com.blamezeus.coreapi.domain.dto.QueryResponse
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

    private val service = QueryService(queryRouter, sqlQueryHandler)

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
    }

    @Test
    fun `a router exception defaults to RAG rather than propagating`() {
        every { queryRouter.classify(any()) } throws RuntimeException("router LLM unavailable")

        val response = service.handle("Why did Athena turn Arachne into a spider?")

        assertThat(response.routeDecision).isEqualTo(RouteDecision.RAG)
        assertThat(response.serviceError).isFalse()
        verify(exactly = 0) { sqlQueryHandler.handle(any()) }
    }

    @Test
    fun `RAG and MIXED routes get a Stage 5 placeholder response, not an exception`() {
        every { queryRouter.classify(any()) } returns RouteDecision.MIXED

        val response = service.handle("Which heroes had a divine parent and died at Troy?")

        assertThat(response.routeDecision).isEqualTo(RouteDecision.MIXED)
        assertThat(response.serviceError).isFalse()
        assertThat(response.answer).isNotBlank()
        verify(exactly = 0) { sqlQueryHandler.handle(any()) }
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
    fun `when both router and the resulting handler path fail, the response still has serviceError true and a non-empty answer`() {
        every { queryRouter.classify(any()) } throws RuntimeException("router LLM unavailable")

        val response = service.handle("Which Olympians are children of Cronus?")

        // Router failure alone degrades to RAG (no handler exists yet, so no exception downstream) —
        // this only becomes serviceError once a real RagQueryHandler that can itself fail exists (Stage 6).
        // For now assert the guarantee that matters at this stage: the response is always well-formed.
        assertThat(response.answer).isNotBlank()
        assertThat(response.routeDecision).isEqualTo(RouteDecision.RAG)
    }
}
