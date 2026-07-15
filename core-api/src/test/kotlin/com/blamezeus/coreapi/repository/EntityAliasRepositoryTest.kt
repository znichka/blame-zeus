package com.blamezeus.coreapi.repository

import com.blamezeus.coreapi.AbstractContainerTest
import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired

// Track G4 (TODO-stage4.md): unblocked once V14 (Track C6) and EntityAlias (Track D7)
// both exist -- V14's seeded aliases are already there, no fixture seeding needed.
class EntityAliasRepositoryTest : AbstractContainerTest() {

    @Autowired
    lateinit var entityAliasRepository: EntityAliasRepository

    @Autowired
    lateinit var entityRecordRepository: EntityRecordRepository

    @Test
    fun `findByAliasIgnoreCase resolves Venus to the Aphrodite entity`() {
        val alias = entityAliasRepository.findByAliasIgnoreCase("venus")
        assertThat(alias).isNotNull
        val entity = entityRecordRepository.findById(alias!!.entityId).orElse(null)
        assertThat(entity).isNotNull
        assertThat(entity!!.name).isEqualTo("Aphrodite")
    }

    @Test
    fun `findByAliasIgnoreCase returns null for an unknown alias`() {
        assertThat(entityAliasRepository.findByAliasIgnoreCase("Definitely Not An Alias")).isNull()
    }
}
