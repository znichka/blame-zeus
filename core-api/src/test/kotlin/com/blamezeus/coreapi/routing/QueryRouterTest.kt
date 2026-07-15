package com.blamezeus.coreapi.routing

import io.mockk.every
import io.mockk.mockk
import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.Test

class QueryRouterTest {

    // [DEV-014] RouteDecision must stay exactly SQL/RAG/MIXED — no CONFLICT value.
    // Conflict surfacing is a router-independent enrichment step (Stage 7), not a route.
    @Test
    fun `RouteDecision has exactly SQL RAG MIXED and no CONFLICT`() {
        val names = RouteDecision.entries.map { it.name }.toSet()
        assertThat(RouteDecision.entries).hasSize(3)
        assertThat(names).containsExactlyInAnyOrder("SQL", "RAG", "MIXED")
        assertThat(names).doesNotContain("CONFLICT")
    }

    @Test
    fun `a consumer only ever acts on the three known route decisions`() {
        val router = mockk<QueryRouter>()
        every { router.classify(any()) } returns RouteDecision.SQL

        val decision = router.classify("Which Olympians are children of Cronus?")

        val handled = when (decision) {
            RouteDecision.SQL -> "sql"
            RouteDecision.RAG -> "rag"
            RouteDecision.MIXED -> "mixed"
        }

        assertThat(handled).isEqualTo("sql")
    }
}
