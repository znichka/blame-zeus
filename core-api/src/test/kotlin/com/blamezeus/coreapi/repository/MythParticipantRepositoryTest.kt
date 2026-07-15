package com.blamezeus.coreapi.repository

import com.blamezeus.coreapi.AbstractContainerTest
import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired

// Track G5 (TODO-stage4.md): unblocked once V13 (Track C5) and Myth/MythParticipant (Track D4)
// both exist -- V13's seeded myths + participants are already there, no fixture seeding needed.
class MythParticipantRepositoryTest : AbstractContainerTest() {

    @Autowired
    lateinit var mythParticipantRepository: MythParticipantRepository

    @Autowired
    lateinit var mythRepository: MythRepository

    @Test
    fun `at least one seeded myth has two or more participants`() {
        val participantsPerMyth = mythParticipantRepository.findAll().groupBy { it.id.mythId }
        assertThat(participantsPerMyth.values.map { it.size }.maxOrNull())
            .isNotNull
            .isGreaterThanOrEqualTo(2)
    }

    @Test
    fun `every participant references a seeded myth`() {
        val mythIds = mythRepository.findAll().map { it.id }.toSet()
        val participantMythIds = mythParticipantRepository.findAll().map { it.id.mythId }.toSet()
        assertThat(mythIds).containsAll(participantMythIds)
    }
}
