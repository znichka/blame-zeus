package com.blamezeus.coreapi.handler

import com.blamezeus.coreapi.ai.RagAgent
import com.blamezeus.coreapi.domain.dto.Citation
import com.blamezeus.coreapi.domain.dto.RagResponse
import com.blamezeus.coreapi.routing.RouteDecision
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.Test

class RagQueryHandlerTest {

    private val ragAgent = mockk<RagAgent>()

    private val handler = RagQueryHandler(ragAgent)

    @Test
    fun `maps RagResponse straight into QueryResponse without any text or prose parsing`() {
        val citations = listOf(Citation(author = "Ovid", work = "Metamorphoses", passageRef = "6.129-6.145"))
        every { ragAgent.answer("question") } returns RagResponse(answer = "Athena turned Arachne into a spider.", citations = citations)

        val response = handler.handle("question")

        assertThat(response.answer).isEqualTo("Athena turned Arachne into a spider.")
        assertThat(response.citations).isEqualTo(citations)
        assertThat(response.routeDecision).isEqualTo(RouteDecision.RAG)
        assertThat(response.sqlGenerated).isNull()
        assertThat(response.conflicts).isEmpty()
        assertThat(response.serviceError).isFalse()
    }

    @Test
    fun `a no-context RagResponse (empty citations) passes through intact rather than erroring`() {
        every { ragAgent.answer("question") } returns
            RagResponse(answer = "The provided texts do not address this question.", citations = emptyList())

        val response = handler.handle("question")

        assertThat(response.answer).isEqualTo("The provided texts do not address this question.")
        assertThat(response.citations).isEmpty()
        assertThat(response.serviceError).isFalse()
    }

    @Test
    fun `calls RagAgent answer exactly once with the raw question`() {
        every { ragAgent.answer(any()) } returns RagResponse(answer = "answer", citations = emptyList())

        handler.handle("Why did Athena turn Arachne into a spider?")

        verify(exactly = 1) { ragAgent.answer("Why did Athena turn Arachne into a spider?") }
    }
}
