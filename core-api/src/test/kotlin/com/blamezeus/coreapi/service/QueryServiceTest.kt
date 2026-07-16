package com.blamezeus.coreapi.service

import com.blamezeus.coreapi.ai.ConflictProbe
import com.blamezeus.coreapi.ai.ConflictSynthesizer
import com.blamezeus.coreapi.conflict.ConflictClaim
import com.blamezeus.coreapi.conflict.ConflictLookup
import com.blamezeus.coreapi.domain.dto.Citation
import com.blamezeus.coreapi.domain.dto.ConflictEntry
import com.blamezeus.coreapi.domain.dto.ProbeResult
import com.blamezeus.coreapi.domain.dto.QueryResponse
import com.blamezeus.coreapi.handler.MixedQueryHandler
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
    private val mixedQueryHandler = mockk<MixedQueryHandler>()
    private val conflictProbe = mockk<ConflictProbe>()
    private val conflictLookup = mockk<ConflictLookup>()
    private val conflictSynthesizer = mockk<ConflictSynthesizer>()

    private val service = QueryService(
        queryRouter,
        sqlQueryHandler,
        ragQueryHandler,
        mixedQueryHandler,
        conflictProbe,
        conflictLookup,
        conflictSynthesizer,
    )

    init {
        // Default: every pre-existing test below predates conflict enrichment and doesn't care
        // about it, so the probe defaults to the "none" sentinel -- enrichment short-circuits to
        // a no-op and the answer passes through byte-identical, exactly as before Stage 7. Tests
        // that exercise enrichment itself override this with their own `every {}` stub.
        every { conflictProbe.extract(any()) } returns ProbeResult(subject = "Unknown", claimType = "none")
    }

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
    fun `Track E3 -- the SQL-empty-result to RAG fallback answer still gets enriched, not skipped`() {
        every { queryRouter.classify(any()) } returns RouteDecision.SQL
        val emptySqlResponse = QueryResponse(
            answer = SqlQueryHandler.EMPTY_RESULT_ANSWER,
            routeDecision = RouteDecision.SQL,
            citations = emptyList(),
            conflicts = emptyList(),
            sqlGenerated = "SELECT name FROM entities WHERE name = 'Aphrodite''s parent'",
        )
        every { sqlQueryHandler.handle(any()) } returns emptySqlResponse
        val ragResponse = QueryResponse(
            answer = "Sources differ on Aphrodite's parentage.",
            routeDecision = RouteDecision.RAG,
            citations = emptyList(),
            conflicts = emptyList(),
            sqlGenerated = null,
        )
        every { ragQueryHandler.handle(any()) } returns ragResponse
        every { conflictProbe.extract(any()) } returns ProbeResult(subject = "Aphrodite", claimType = "parentage")
        val claims = listOf(ConflictClaim("child of Zeus", "Homer", "Iliad", "5.334-5.380"))
        every { conflictLookup.find("Aphrodite", "parentage") } returns claims
        val entries = listOf(ConflictEntry("child of Zeus", "Homer", "Iliad", "5.334-5.380"))
        every { conflictSynthesizer.synthesize(claims) } returns entries

        val response = service.handle("Who is Aphrodite's parent?")

        assertThat(response.routeDecision).isEqualTo(RouteDecision.RAG)
        assertThat(response.conflicts).isEqualTo(entries)
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
    fun `a MIXED decision dispatches to MixedQueryHandler and nowhere else`() {
        every { queryRouter.classify(any()) } returns RouteDecision.MIXED
        val mixedResponse = QueryResponse(
            answer = "Achilles, son of the sea-nymph Thetis, died at Troy.",
            routeDecision = RouteDecision.MIXED,
            citations = emptyList(),
            conflicts = emptyList(),
            sqlGenerated = "SELECT name FROM entities WHERE type = 'hero'",
        )
        every { mixedQueryHandler.handle("Which heroes had a divine parent and died at Troy?") } returns mixedResponse

        val response = service.handle("Which heroes had a divine parent and died at Troy?")

        assertThat(response).isEqualTo(mixedResponse)
        verify(exactly = 1) { mixedQueryHandler.handle("Which heroes had a divine parent and died at Troy?") }
        verify(exactly = 0) { sqlQueryHandler.handle(any()) }
        verify(exactly = 0) { ragQueryHandler.handle(any()) }
    }

    @Test
    fun `when the MIXED handler throws, the response has serviceError true and a non-empty answer`() {
        every { queryRouter.classify(any()) } returns RouteDecision.MIXED
        every { mixedQueryHandler.handle(any()) } throws RuntimeException("chat model unavailable")

        val response = service.handle("Which heroes had a divine parent and died at Troy?")

        assertThat(response.serviceError).isTrue()
        assertThat(response.answer).isNotBlank()
        assertThat(response.routeDecision).isEqualTo(RouteDecision.MIXED)
    }

    @Test
    fun `a MIXED-routed answer also gets enriched with conflicts, proving enrichment is genuinely route-independent`() {
        every { queryRouter.classify(any()) } returns RouteDecision.MIXED
        val mixedResponse = QueryResponse(
            answer = "Achilles' divine lineage traces through Thetis to the sea gods.",
            routeDecision = RouteDecision.MIXED,
            citations = emptyList(),
            conflicts = emptyList(),
            sqlGenerated = "SELECT name FROM entities WHERE name ILIKE 'Achilles'",
        )
        every { mixedQueryHandler.handle(any()) } returns mixedResponse
        every { conflictProbe.extract(any()) } returns ProbeResult(subject = "Zeus", claimType = "parentage")
        val claims = listOf(ConflictClaim("child of Cronus", "Hesiod", "Theogony", "450-500"))
        every { conflictLookup.find("Zeus", "parentage") } returns claims
        val entries = listOf(ConflictEntry("child of Cronus", "Hesiod", "Theogony", "450-500"))
        every { conflictSynthesizer.synthesize(claims) } returns entries

        val response = service.handle("What is the divine lineage connecting Achilles to Zeus?")

        assertThat(response.routeDecision).isEqualTo(RouteDecision.MIXED)
        assertThat(response.conflicts).isEqualTo(entries)
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

    // --- Stage 7 Track E1: conflict enrichment ---

    @Test
    fun `a SQL-routed conflict-shaped question gets enriched with conflicts after the SQL answer, not as a route`() {
        every { queryRouter.classify(any()) } returns RouteDecision.SQL
        val sqlResponse = QueryResponse(
            answer = "Zeus and Dione are both named as Aphrodite's parents across sources.",
            routeDecision = RouteDecision.SQL,
            citations = emptyList(),
            conflicts = emptyList(),
            sqlGenerated = "SELECT ...",
        )
        every { sqlQueryHandler.handle(any()) } returns sqlResponse
        every { conflictProbe.extract(any()) } returns ProbeResult(subject = "Aphrodite", claimType = "parentage")
        val claims = listOf(
            ConflictClaim("child of Zeus", "Homer", "Iliad", "5.334-5.380"),
            ConflictClaim("Born from sea foam", "Hesiod", "Theogony", "176-232"),
        )
        every { conflictLookup.find("Aphrodite", "parentage") } returns claims
        val entries = listOf(
            ConflictEntry("child of Zeus", "Homer", "Iliad", "5.334-5.380"),
            ConflictEntry("Born from sea foam", "Hesiod", "Theogony", "176-232"),
        )
        every { conflictSynthesizer.synthesize(claims) } returns entries

        val response = service.handle("Who were Aphrodite's parents?")

        assertThat(response.routeDecision).isEqualTo(RouteDecision.SQL)
        assertThat(response.conflicts).isEqualTo(entries)
    }

    @Test
    fun `a RAG-routed conflict-shaped question also gets enriched, proving router-independence`() {
        every { queryRouter.classify(any()) } returns RouteDecision.RAG
        val ragResponse = QueryResponse(
            answer = "Sources differ on Aphrodite's parentage.",
            routeDecision = RouteDecision.RAG,
            citations = emptyList(),
            conflicts = emptyList(),
            sqlGenerated = null,
        )
        every { ragQueryHandler.handle(any()) } returns ragResponse
        every { conflictProbe.extract(any()) } returns ProbeResult(subject = "Aphrodite", claimType = "parentage")
        val claims = listOf(
            ConflictClaim("child of Zeus", "Homer", "Iliad", "5.334-5.380"),
            ConflictClaim("Born from sea foam", "Hesiod", "Theogony", "176-232"),
        )
        every { conflictLookup.find("Aphrodite", "parentage") } returns claims
        val entries = listOf(
            ConflictEntry("child of Zeus", "Homer", "Iliad", "5.334-5.380"),
            ConflictEntry("Born from sea foam", "Hesiod", "Theogony", "176-232"),
        )
        every { conflictSynthesizer.synthesize(claims) } returns entries

        val response = service.handle("Who were Aphrodite's parents?")

        assertThat(response.routeDecision).isEqualTo(RouteDecision.RAG)
        assertThat(response.conflicts).isEqualTo(entries)
    }

    @Test
    fun `a claim-type mismatch yields empty conflicts and an unchanged answer, protecting grounded refusals`() {
        every { queryRouter.classify(any()) } returns RouteDecision.RAG
        val ragResponse = QueryResponse(
            answer = "Achilles was famously strong and swift-footed.",
            routeDecision = RouteDecision.RAG,
            citations = emptyList(),
            conflicts = emptyList(),
            sqlGenerated = null,
        )
        every { ragQueryHandler.handle(any()) } returns ragResponse
        every { conflictProbe.extract(any()) } returns ProbeResult(subject = "Achilles", claimType = "appearance")
        every { conflictLookup.find("Achilles", "appearance") } returns emptyList()

        val response = service.handle("What did Achilles look like?")

        assertThat(response).isEqualTo(ragResponse)
        assertThat(response.conflicts).isEmpty()
        verify(exactly = 0) { conflictSynthesizer.synthesize(any()) }
    }

    @Test
    fun `a probe returning the none sentinel skips the structured lookup entirely`() {
        every { queryRouter.classify(any()) } returns RouteDecision.RAG
        val ragResponse = QueryResponse(
            answer = "Athena turned Arachne into a spider out of jealousy over her weaving skill.",
            routeDecision = RouteDecision.RAG,
            citations = emptyList(),
            conflicts = emptyList(),
            sqlGenerated = null,
        )
        every { ragQueryHandler.handle(any()) } returns ragResponse
        every { conflictProbe.extract(any()) } returns ProbeResult(subject = "Athena", claimType = "none")

        val response = service.handle("Why did Athena turn Arachne into a spider?")

        assertThat(response).isEqualTo(ragResponse)
        verify(exactly = 0) { conflictLookup.find(any(), any()) }
        verify(exactly = 0) { conflictSynthesizer.synthesize(any()) }
    }

    @Test
    fun `conflictProbe throwing leaves the primary answer intact and does not flip serviceError`() {
        every { queryRouter.classify(any()) } returns RouteDecision.RAG
        val ragResponse = QueryResponse(
            answer = "Athena turned Arachne into a spider out of jealousy over her weaving skill.",
            routeDecision = RouteDecision.RAG,
            citations = emptyList(),
            conflicts = emptyList(),
            sqlGenerated = null,
        )
        every { ragQueryHandler.handle(any()) } returns ragResponse
        every { conflictProbe.extract(any()) } throws RuntimeException("probe LLM unavailable")

        val response = service.handle("Why did Athena turn Arachne into a spider?")

        assertThat(response).isEqualTo(ragResponse)
        assertThat(response.serviceError).isFalse()
    }

    @Test
    fun `conflictLookup throwing leaves the primary answer intact and does not flip serviceError`() {
        every { queryRouter.classify(any()) } returns RouteDecision.RAG
        val ragResponse = QueryResponse(
            answer = "Sources differ on Aphrodite's parentage.",
            routeDecision = RouteDecision.RAG,
            citations = emptyList(),
            conflicts = emptyList(),
            sqlGenerated = null,
        )
        every { ragQueryHandler.handle(any()) } returns ragResponse
        every { conflictProbe.extract(any()) } returns ProbeResult(subject = "Aphrodite", claimType = "parentage")
        every { conflictLookup.find(any(), any()) } throws RuntimeException("db unavailable")

        val response = service.handle("Who were Aphrodite's parents?")

        assertThat(response).isEqualTo(ragResponse)
        assertThat(response.serviceError).isFalse()
    }

    @Test
    fun `conflictSynthesizer throwing leaves the primary answer intact and does not flip serviceError`() {
        every { queryRouter.classify(any()) } returns RouteDecision.RAG
        val ragResponse = QueryResponse(
            answer = "Sources differ on Aphrodite's parentage.",
            routeDecision = RouteDecision.RAG,
            citations = emptyList(),
            conflicts = emptyList(),
            sqlGenerated = null,
        )
        every { ragQueryHandler.handle(any()) } returns ragResponse
        every { conflictProbe.extract(any()) } returns ProbeResult(subject = "Aphrodite", claimType = "parentage")
        val claims = listOf(ConflictClaim("child of Zeus", "Homer", "Iliad", "5.334-5.380"))
        every { conflictLookup.find(any(), any()) } returns claims
        every { conflictSynthesizer.synthesize(any()) } throws RuntimeException("mapper blew up")

        val response = service.handle("Who were Aphrodite's parents?")

        assertThat(response).isEqualTo(ragResponse)
        assertThat(response.serviceError).isFalse()
    }

    @Test
    fun `enrichment is skipped entirely when the primary answer already has serviceError true`() {
        every { queryRouter.classify(any()) } returns RouteDecision.SQL
        every { sqlQueryHandler.handle(any()) } throws RuntimeException("db unavailable")

        val response = service.handle("Which Olympians are children of Cronus?")

        assertThat(response.serviceError).isTrue()
        verify(exactly = 0) { conflictProbe.extract(any()) }
        verify(exactly = 0) { conflictLookup.find(any(), any()) }
        verify(exactly = 0) { conflictSynthesizer.synthesize(any()) }
    }

    @Test
    fun `enrichment writes only conflicts, leaving answer routeDecision citations and sqlGenerated untouched`() {
        every { queryRouter.classify(any()) } returns RouteDecision.SQL
        val sqlResponse = QueryResponse(
            answer = "Zeus, Hera",
            routeDecision = RouteDecision.SQL,
            citations = listOf(Citation("Homer", "Iliad", "1.1-1.10")),
            conflicts = emptyList(),
            sqlGenerated = "SELECT name FROM entities",
        )
        every { sqlQueryHandler.handle(any()) } returns sqlResponse
        every { conflictProbe.extract(any()) } returns ProbeResult(subject = "Zeus", claimType = "parentage")
        val claims = listOf(ConflictClaim("child of Cronus", "Hesiod", "Theogony", "450-500"))
        every { conflictLookup.find("Zeus", "parentage") } returns claims
        val entries = listOf(ConflictEntry("child of Cronus", "Hesiod", "Theogony", "450-500"))
        every { conflictSynthesizer.synthesize(claims) } returns entries

        val response = service.handle("Who are Zeus's parents?")

        assertThat(response.answer).isEqualTo(sqlResponse.answer)
        assertThat(response.routeDecision).isEqualTo(sqlResponse.routeDecision)
        assertThat(response.citations).isEqualTo(sqlResponse.citations)
        assertThat(response.sqlGenerated).isEqualTo(sqlResponse.sqlGenerated)
        assertThat(response.conflicts).isEqualTo(entries)
    }
}
