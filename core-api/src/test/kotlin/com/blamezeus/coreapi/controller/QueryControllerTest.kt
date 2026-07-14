package com.blamezeus.coreapi.controller

import com.blamezeus.coreapi.AbstractContainerTest
import com.blamezeus.coreapi.domain.entity.EntityRecord
import com.blamezeus.coreapi.repository.EntityRecordRepository
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
}
