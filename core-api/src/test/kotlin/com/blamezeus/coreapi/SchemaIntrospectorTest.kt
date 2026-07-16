package com.blamezeus.coreapi

import com.blamezeus.coreapi.config.SchemaIntrospector
import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.transaction.annotation.Transactional

class SchemaIntrospectorTest : AbstractContainerTest() {

    @Autowired
    lateinit var schemaIntrospector: SchemaIntrospector

    @Autowired
    lateinit var jdbcTemplate: JdbcTemplate

    @Test
    fun `prompt contains every application table without hand registration`() {
        val allTables = jdbcTemplate.queryForList(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'",
            String::class.java
        )
        assertThat(allTables).contains("entities", "claim_type_aliases")

        val prompt = schemaIntrospector.get()
        (allTables - "flyway_schema_history").forEach { table ->
            assertThat(prompt).contains("$table(")
        }
        assertThat(prompt).doesNotContain("flyway_schema_history")
    }

    @Test
    fun `prompt contains known columns from critical tables`() {
        val prompt = schemaIntrospector.get()
        assertThat(prompt)
            .contains("subject_entity_id")
            .contains("trust_tier")
            .contains("year_published")
            .contains("content_hash")
            .contains("passage_ref")
    }

    @Test
    fun `prompt contains column types and foreign keys`() {
        val prompt = schemaIntrospector.get()
        assertThat(prompt)
            .contains("embedding vector")
            .contains("name text")
            .contains("subject_entity_id references entities(id)")
            .contains("source_id references sources(id)")
    }

    @Test
    fun `prompt contains check constraint value vocabularies`() {
        val prompt = schemaIntrospector.get()
        assertThat(prompt)
            .contains("olympian")
            .contains("spine")
    }

    @Test
    fun `prompt contains schema comments`() {
        val prompt = schemaIntrospector.get()
        assertThat(prompt)
            .contains("NO source attribution")
            .contains("Normalization map")
    }

    @Test
    @Transactional
    fun `prompt emits live distinct values for vocabulary columns`() {
        jdbcTemplate.update(
            "INSERT INTO sources (id, author, work, stance, year_published, role) " +
                "VALUES ('test-source', 'Tester', 'Test Work', 'poetic-myth', 1900, 'spine')"
        )
        jdbcTemplate.update("INSERT INTO entities (name, type) VALUES ('TestParent', 'titan'), ('TestChild', 'olympian')")
        jdbcTemplate.update(
            "INSERT INTO relationships (from_id, relation, to_id, source_id) " +
                "SELECT p.id, 'parent_of', c.id, 'test-source' " +
                "FROM entities p, entities c WHERE p.name = 'TestParent' AND c.name = 'TestChild'"
        )

        // fresh instance: the shared bean's prompt is cached from before this data existed
        val prompt = SchemaIntrospector(jdbcTemplate).get()
        assertThat(prompt).contains("relation values: 'parent_of'")
        // Enum columns surfaced as live values (DEV-054) so the model uses exact stored casing.
        // Order-independent (values are frequency-ordered): assert the vocabulary line is emitted.
        assertThat(prompt).contains("type values:")
        assertThat(prompt).contains("stance values:")
        assertThat(prompt).contains("role values:")
    }
}
