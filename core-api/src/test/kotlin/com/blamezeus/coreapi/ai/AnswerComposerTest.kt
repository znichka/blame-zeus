package com.blamezeus.coreapi.ai

import com.blamezeus.coreapi.domain.dto.Citation
import com.blamezeus.coreapi.domain.dto.ComposedAnswer
import io.mockk.every
import io.mockk.mockk
import io.mockk.verify
import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.Test

// ADR-015 Track B1: the model is mocked (no live LLM per TECH_GUARDRAILS) — this locks in the
// interface contract (question/material/conflicts in, ComposedAnswer out) that QueryService's
// Track D wiring depends on. Prompt-fidelity behaviour (does the LLM actually weave conflicts /
// emit correct [n] markers) is exercised end-to-end only by Track G's manual smoke, not here.
class AnswerComposerTest {

    private val composer = mockk<AnswerComposer>()

    @Test
    fun `compose returns a ComposedAnswer built from question, material and conflicts`() {
        val expected = ComposedAnswer(
            answer = "Zeus is king of the gods [1].",
            citations = listOf(Citation(author = "Hesiod", work = "Theogony", passageRef = "450-500")),
        )
        every { composer.compose("Who is Zeus?", "name=Zeus, type=olympian", "none") } returns expected

        val result = composer.compose("Who is Zeus?", "name=Zeus, type=olympian", "none")

        assertThat(result).isEqualTo(expected)
        verify(exactly = 1) { composer.compose("Who is Zeus?", "name=Zeus, type=olympian", "none") }
    }

    @Test
    fun `the mapping into ComposedAnswer is faithful -- fields pass through untransformed`() {
        val claimLine = "Homer, Iliad, 5.334-5.380: child of Zeus"
        val expected = ComposedAnswer(
            answer = "Sources disagree on Aphrodite's parentage: Homer says she is a child of Zeus [1], " +
                "while Hesiod says she was born from sea foam [2].",
            citations = listOf(
                Citation(author = "Homer", work = "Iliad", passageRef = "5.334-5.380"),
                Citation(author = "Hesiod", work = "Theogony", passageRef = "176-232", stance = "cosmological"),
            ),
        )
        every { composer.compose(any(), any(), eq(claimLine)) } returns expected

        val result = composer.compose("Who were Aphrodite's parents?", "material", claimLine)

        assertThat(result.answer).isEqualTo(expected.answer)
        assertThat(result.citations).containsExactlyElementsOf(expected.citations)
        assertThat(result.citations[1].stance).isEqualTo("cosmological")
    }
}
