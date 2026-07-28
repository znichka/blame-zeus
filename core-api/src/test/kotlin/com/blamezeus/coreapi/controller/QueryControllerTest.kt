package com.blamezeus.coreapi.controller

import com.blamezeus.coreapi.AbstractContainerTest
import com.blamezeus.coreapi.domain.entity.EntityRecord
import com.blamezeus.coreapi.repository.EntityRecordRepository
import com.fasterxml.jackson.databind.ObjectMapper
import org.assertj.core.api.Assertions.assertThat
import org.hamcrest.Matchers.greaterThanOrEqualTo
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.status

@AutoConfigureMockMvc
class QueryControllerTest : AbstractContainerTest() {

    @Autowired
    lateinit var mockMvc: MockMvc

    @Autowired
    lateinit var entityRecordRepository: EntityRecordRepository

    @Autowired
    lateinit var objectMapper: ObjectMapper

    @Test
    fun `GET entities returns entities from the repository`() {
        entityRecordRepository.save(EntityRecord(name = "TestControllerZeus", type = "olympian"))

        mockMvc.perform(get("/api/v1/entities"))
            .andExpect(status().isOk)
            .andExpect(jsonPath("$[?(@.name == 'TestControllerZeus')].type").value("olympian"))
    }

    @Test
    fun `GET sources returns exactly the 6 seeded sources`() {
        mockMvc.perform(get("/api/v1/sources"))
            .andExpect(status().isOk)
            .andExpect(jsonPath("$.length()").value(6))
            .andExpect(jsonPath("$[?(@.id == 'apollodorus-bibliotheca')].role").value("spine"))
    }

    // Stage 7 Track F1. ConflictLookup's resolution chain and multi-claim-type behavior are
    // already exercised directly in ConflictLookupTest -- this only proves the endpoint's wiring
    // (path variable -> real seeded data -> JSON shape), against the real V10-V14 seed, no mocks.
    //
    // Stage P4 Track F1 (DEV-110): this endpoint fetches ALL claim_types for the subject (not
    // claim-type-filtered, per CLAUDE.md's ConflictLookup docs), so promoting a second genuine
    // Hesiod/Theogony-sourced claim for Aphrodite (an epithet, alongside the pre-existing birth
    // claim) made the old `jsonPath(...).value("Theogony")` assertion fail -- not because
    // anything broke, but because Spring's jsonPath returns a *list* once 2+ filter matches
    // exist, and `.value(String)` only accepts a single scalar. Asserting "every Hesiod-authored
    // entry cites Theogony" (Hesiod's only seeded work) is the actual invariant under test, and
    // holds regardless of how many such entries exist.
    @Test
    fun `GET conflicts Aphrodite returns her real seeded parentage claims with author and work`() {
        val response = mockMvc.perform(get("/api/v1/conflicts/Aphrodite"))
            .andExpect(status().isOk)
            .andExpect(jsonPath("$.length()").value(greaterThanOrEqualTo(2)))
            .andReturn().response.contentAsString

        val entries: List<Map<String, Any?>> = objectMapper.readValue(
            response, objectMapper.typeFactory.constructCollectionType(List::class.java, Map::class.java)
        )
        val hesiodEntries = entries.filter { it["sourceAuthor"] == "Hesiod" }
        assertThat(hesiodEntries).isNotEmpty
        assertThat(hesiodEntries.map { it["sourceWork"] }).allMatch { it == "Theogony" }
    }

    @Test
    fun `GET conflicts Venus resolves via entity_aliases to the same claims as Aphrodite`() {
        val aphrodite = mockMvc.perform(get("/api/v1/conflicts/Aphrodite")).andReturn().response.contentAsString
        val venus = mockMvc.perform(get("/api/v1/conflicts/Venus")).andReturn().response.contentAsString

        assertThat(venus).isEqualTo(aphrodite)
    }

    @Test
    fun `GET conflicts for an unknown entity returns 200 with an empty list, not 404`() {
        mockMvc.perform(get("/api/v1/conflicts/DefinitelyNotARealEntityXyz123"))
            .andExpect(status().isOk)
            .andExpect(jsonPath("$.length()").value(0))
    }
}
