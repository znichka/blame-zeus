package com.blamezeus.coreapi.ai

import com.blamezeus.coreapi.conflict.ConflictClaim
import com.blamezeus.coreapi.domain.dto.ConflictEntry
import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.Test

// Stage 7 Track C3. Plain fixtures, no Testcontainers -- ConflictSynthesizer is a deterministic
// mapper (Track A2/DEV-051), not an @AiService.
class ConflictSynthesizerTest {

    private val synthesizer = ConflictSynthesizer()

    @Test
    fun `every fetched version appears in the output, none dropped or reordered`() {
        val claims = listOf(
            ConflictClaim("child of Zeus", "Homer", "Iliad", "5.334-5.380"),
            ConflictClaim("child of Dione", "Apollodorus", "Bibliotheca", "1.3.1-1.3.5"),
            ConflictClaim("Born from sea foam", "Hesiod", "Theogony", "176-232"),
        )

        val result = synthesizer.synthesize(claims)

        assertThat(result).hasSize(3)
        assertThat(result.map { it.claimValue })
            .containsExactly("child of Zeus", "child of Dione", "Born from sea foam")
        assertThat(result[0]).isEqualTo(
            ConflictEntry("child of Zeus", "Homer", "Iliad", "5.334-5.380")
        )
    }

    @Test
    fun `complementary claims -- one naming a killer, another a manner of death -- both survive with no contradiction asserted`() {
        // ADR-007 §1: a "killed by X" claim and a "died of Y" claim about the same subject may be
        // complementary, not contradictory. The synthesizer must not drop either, rank one over
        // the other, or synthesize any new text implying they conflict -- it only structures.
        val claims = listOf(
            ConflictClaim("killed by Paris and Apollo with arrows", "Ovid", "Metamorphoses", "13.481-13.507"),
            ConflictClaim("wounded in the heel", "Apollodorus", "Bibliotheca", "E.5.3"),
        )

        val result = synthesizer.synthesize(claims)

        assertThat(result).hasSize(2)
        assertThat(result.map { it.claimValue })
            .containsExactly("killed by Paris and Apollo with arrows", "wounded in the heel")
        assertThat(result.map { it.sourceAuthor }).containsExactly("Ovid", "Apollodorus")
    }

    @Test
    fun `empty input yields empty output without throwing`() {
        assertThat(synthesizer.synthesize(emptyList())).isEmpty()
    }

    @Test
    fun `a claim with a null passageRef maps through unchanged`() {
        val claims = listOf(ConflictClaim("child of Inachus", "Apollodorus", "Bibliotheca", null))

        val result = synthesizer.synthesize(claims)

        assertThat(result[0].passageRef).isNull()
    }
}
