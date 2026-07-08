package com.blamezeus.coreapi

import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.jdbc.core.JdbcTemplate

class FlywayMigrationTest : AbstractContainerTest() {

    @Autowired
    lateinit var jdbcTemplate: JdbcTemplate

    private fun tables(): List<String> =
        jdbcTemplate.queryForList(
            "SELECT table_name FROM information_schema.tables WHERE table_schema = 'public' AND table_type = 'BASE TABLE'",
            String::class.java
        )

    private fun columns(table: String): List<String> =
        jdbcTemplate.queryForList(
            "SELECT column_name FROM information_schema.columns WHERE table_name = ? AND table_schema = 'public'",
            String::class.java,
            table
        )

    @Test
    fun `all expected tables exist`() {
        assertThat(tables()).containsAll(
            listOf("sources", "entities", "relationships", "myths", "myth_participants", "variant_claims", "narrative_chunks")
        )
    }

    @Test
    fun `variant_claims has required columns`() {
        assertThat(columns("variant_claims")).containsAll(
            listOf("subject_entity_id", "claim_type", "claim_value", "source_id", "trust_tier")
        )
    }

    @Test
    fun `narrative_chunks has content_hash and embedding`() {
        assertThat(columns("narrative_chunks")).containsAll(
            listOf("content", "content_hash", "embedding", "source_id", "passage_ref")
        )
    }

    @Test
    fun `sources has year_published and role`() {
        assertThat(columns("sources")).containsAll(
            listOf("author", "work", "translation", "stance", "year_published", "role")
        )
    }

    @Test
    fun `entity_aliases table does not exist yet`() {
        assertThat(tables()).doesNotContain("entity_aliases")
    }
}
