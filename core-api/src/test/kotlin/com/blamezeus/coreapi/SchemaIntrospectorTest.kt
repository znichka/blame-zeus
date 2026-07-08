package com.blamezeus.coreapi

import com.blamezeus.coreapi.config.SchemaIntrospector
import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired

class SchemaIntrospectorTest : AbstractContainerTest() {

    @Autowired
    lateinit var schemaIntrospector: SchemaIntrospector

    @Test
    fun `prompt contains all application tables`() {
        val prompt = schemaIntrospector.get()
        assertThat(prompt)
            .contains("entities")
            .contains("relationships")
            .contains("sources")
            .contains("variant_claims")
            .contains("narrative_chunks")
    }

    @Test
    fun `prompt contains known columns from critical tables`() {
        val prompt = schemaIntrospector.get()
        assertThat(prompt)
            .contains("subject_entity_id")
            .contains("trust_tier")
            .contains("year_published")
            .contains("content_hash")
    }
}
