package com.blamezeus.coreapi.repository

import com.blamezeus.coreapi.AbstractContainerTest
import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired

// Track G2 (TODO-stage4.md): unblocked once V10 (Track C2) and EntityRecord (Track D2)
// both exist -- V10's real ~1,968 rows are already there, no fixture seeding needed.
class EntityRecordRepositoryTest : AbstractContainerTest() {

    @Autowired
    lateinit var entityRecordRepository: EntityRecordRepository

    @Test
    fun `findAll returns at least 60 seeded entities`() {
        assertThat(entityRecordRepository.findAll().size).isGreaterThanOrEqualTo(60)
    }

    @Test
    fun `findByNameIgnoreCase resolves aphrodite case-insensitively`() {
        val aphrodite = entityRecordRepository.findByNameIgnoreCase("aphrodite")
        assertThat(aphrodite).isNotNull
        assertThat(aphrodite!!.name).isEqualTo("Aphrodite")
        assertThat(aphrodite.type).isEqualTo("olympian")
    }

    @Test
    fun `findByNameIgnoreCase returns null for an unknown name`() {
        assertThat(entityRecordRepository.findByNameIgnoreCase("Definitely Not A Mythological Figure")).isNull()
    }
}
