package com.blamezeus.coreapi.repository

import com.blamezeus.coreapi.AbstractContainerTest
import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired

// Track G1 (TODO-stage4.md): unblocked as soon as V9 (Track C1) and Source (Track D1)
// both exist — no manual fixture seeding needed, V9's real rows are already there.
class SourceRepositoryTest : AbstractContainerTest() {

    @Autowired
    lateinit var sourceRepository: SourceRepository

    @Test
    fun `findAll returns exactly 6 seeded sources`() {
        assertThat(sourceRepository.findAll()).hasSize(6)
    }

    @Test
    fun `apollodorus row has the expected year_published and role`() {
        val apollodorus = sourceRepository.findById("apollodorus-bibliotheca").orElseThrow()
        assertThat(apollodorus.yearPublished).isEqualTo(1921)
        assertThat(apollodorus.role).isEqualTo("spine")
    }
}
