package com.blamezeus.coreapi.ai

import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.Test

// Stage P2 Track I5 (Rung 1) [DEVIATED - see DEVIATIONS.md #DEV-069]. `generateSql`'s actual
// steering effect on the live model is only verifiable via evaluation/runner (no live LLM calls in
// this suite, TECH_GUARDRAILS) -- this locks in the prompt *shape* itself so a future edit can't
// silently drop the bounding rule or its worked example.
class TextToSqlAgentPromptTest {

    private val prompt = TextToSqlAgent.GENERATE_SQL_SYSTEM_MESSAGE

    @Test
    fun `mandates a visited-id array bound for recursive traversals`() {
        assertThat(prompt).contains("visited")
        assertThat(prompt).contains("ARRAY[e.id]")
        assertThat(prompt).contains("NOT next.id = ANY(current.visited)")
    }

    @Test
    fun `mandates an independent depth cap for recursive traversals`() {
        assertThat(prompt).contains("depth < 20")
    }

    @Test
    fun `warns against mixing parent_of and child_of in one recursive join`() {
        assertThat(prompt).contains("never combine `parent_of` with")
        assertThat(prompt).contains("child_of")
    }

    @Test
    fun `carries a worked example demonstrating both bounds together on a real recursive query`() {
        assertThat(prompt).contains("WITH RECURSIVE lineage AS")
        assertThat(prompt).contains("lineage.visited || parent.id")
        assertThat(prompt).contains("lineage.depth < 20")
        assertThat(prompt).contains("r.relation = 'parent_of'")
    }

    @Test
    fun `the worked example still carries the mandatory attribution projection (DEV-057)`() {
        assertThat(prompt).contains("s.author AS author")
        assertThat(prompt).contains("s.work AS work")
        assertThat(prompt).contains("lineage.passage_ref AS passage_ref")
        assertThat(prompt).contains("s.stance AS stance")
    }

    @Test
    fun `pre-existing rules survive the edit unchanged`() {
        // A quick regression net for the surrounding, untouched rules -- catches an accidental
        // deletion during the edit, not a content assertion on them individually.
        assertThat(prompt).contains("Only SELECT or WITH (CTE) statements")
        assertThat(prompt).contains("Use ILIKE, not =")
        assertThat(prompt).contains("ATTRIBUTION IS MANDATORY")
        assertThat(prompt).contains("Which Olympians are children of Cronus?")
    }
}
