package com.blamezeus.coreapi.config

import org.slf4j.LoggerFactory
import org.springframework.beans.factory.annotation.Value
import org.springframework.boot.context.event.ApplicationReadyEvent
import org.springframework.context.event.EventListener
import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.stereotype.Component

/**
 * Startup guard for ADR-006: compares the configured embedding model against what's actually
 * stamped on `narrative_chunks` rows (V8_4/DEV-028). A mismatch means retrieval is silently
 * comparing incompatible vector spaces — logged as an error, but this never blocks startup
 * (drift is a data problem, not a boot failure; deferred to Stage 6 per DEV-015).
 */
@Component
class EmbeddingConsistencyChecker(
    private val jdbcTemplate: JdbcTemplate,
    @Value("\${app.llm.embedding-model}") private val configuredEmbeddingModel: String,
) {

    @EventListener(ApplicationReadyEvent::class)
    fun checkOnStartup() {
        val storedModels = jdbcTemplate.queryForList(
            "SELECT DISTINCT embedding_model FROM narrative_chunks",
            String::class.java
        )

        if (storedModels.isEmpty()) {
            log.info("narrative_chunks is empty — skipping embedding model consistency check")
            return
        }

        val mismatches = storedModels.filterNot { it == configuredEmbeddingModel }
        if (mismatches.isNotEmpty()) {
            log.error(
                "Embedding model drift detected: app.llm.embedding-model='{}' but narrative_chunks " +
                    "contains rows stamped with {}. Retrieval will compare incompatible vector spaces " +
                    "for the mismatched rows.",
                configuredEmbeddingModel,
                mismatches
            )
        } else {
            log.info("Embedding model consistency check passed: '{}' matches all narrative_chunks rows", configuredEmbeddingModel)
        }
    }

    companion object {
        private val log = LoggerFactory.getLogger(EmbeddingConsistencyChecker::class.java)
    }
}
