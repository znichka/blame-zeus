package com.blamezeus.coreapi.config

import com.blamezeus.coreapi.AbstractContainerTest
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc
import org.springframework.test.web.servlet.MockMvc
import org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath
import org.springframework.test.web.servlet.result.MockMvcResultMatchers.status

@AutoConfigureMockMvc
class OpenApiConfigTest : AbstractContainerTest() {

    @Autowired
    lateinit var mockMvc: MockMvc

    @Test
    fun `v3 api-docs reflects the custom OpenAPI title and version`() {
        mockMvc.perform(get("/v3/api-docs"))
            .andExpect(status().isOk)
            .andExpect(jsonPath("$.info.title").value("blame-zeus Core API"))
            .andExpect(jsonPath("$.info.version").value("1.0"))
    }

    @Test
    fun `swagger-ui html loads`() {
        mockMvc.perform(get("/swagger-ui/index.html"))
            .andExpect(status().isOk)
    }
}
