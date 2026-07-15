package com.blamezeus.coreapi.conflict

import org.springframework.jdbc.core.JdbcTemplate
import org.springframework.stereotype.Component

/**
 * Shared entity resolution + `variant_claims` fetch (Stage 7 Track D, ADR-007 §5) — deliberately
 * **not** an `@AiService`; a plain data-access component.
 *
 * Entity resolution is a single three-step short-circuit chain, exact -> `entity_aliases` ->
 * trigram (`idx_entities_name_trgm`), so an exact match never falls through to a same-named alias
 * of a *different* entity, and an alias never falls through to a trigram near-miss.
 *
 * Exposes two fetches over that one resolution: [find] (claim-type-filtered, used by
 * `QueryService`'s enrichment step) and [findAllForEntity] (subject-only, used only by the
 * `GET /api/v1/conflicts/{entityName}` browse endpoint). Neither gates on `trust_tier` or on
 * distinct-source count — the >=2-source rule is the *offline detection* heuristic only
 * (CLAUDE.md); every row for the resolved subject+claim_type is returned.
 */
@Component
class ConflictLookup(private val jdbcTemplate: JdbcTemplate) {

    fun find(subjectName: String, claimType: String): List<ConflictClaim> {
        val entityId = resolveEntityId(subjectName) ?: return emptyList()
        val canonicalClaimType = normalize(claimType)
        return jdbcTemplate.query(CLAIM_TYPE_FILTERED_SQL, ROW_MAPPER, entityId, canonicalClaimType)
    }

    fun findAllForEntity(entityName: String): List<ConflictClaim> {
        val entityId = resolveEntityId(entityName) ?: return emptyList()
        return jdbcTemplate.query(SUBJECT_ONLY_SQL, ROW_MAPPER, entityId)
    }

    private fun resolveEntityId(name: String): Int? {
        jdbcTemplate.query(EXACT_MATCH_SQL, { rs, _ -> rs.getInt("id") }, name).firstOrNull()?.let { return it }
        jdbcTemplate.query(ALIAS_MATCH_SQL, { rs, _ -> rs.getInt("id") }, name).firstOrNull()?.let { return it }
        return jdbcTemplate.query(TRIGRAM_MATCH_SQL, { rs, _ -> rs.getInt("id") }, name, TRIGRAM_THRESHOLD, name)
            .firstOrNull()
    }

    // DEV-022: normalize() reads the shared claim_type_aliases table (never a code-side copy of
    // the map), applied only to the probe input -- identity fallback when no alias row matches
    // (canonicals such as 'parentage'/'death' have no self-row).
    private fun normalize(claimType: String): String =
        jdbcTemplate.query(NORMALIZE_SQL, { rs, _ -> rs.getString("canonical") }, claimType)
            .firstOrNull() ?: claimType

    companion object {
        // pg_trgm's own default GUC (pg_trgm.similarity_threshold) is 0.3; matched here explicitly
        // rather than relying on the session default. Confirmed (Track D1c) to resolve a one-letter
        // substitution typo of a real seeded entity name while still rejecting an unrelated string.
        private const val TRIGRAM_THRESHOLD = 0.3

        private val ROW_MAPPER = { rs: java.sql.ResultSet, _: Int ->
            ConflictClaim(
                claimValue = rs.getString("claim_value"),
                sourceAuthor = rs.getString("author"),
                sourceWork = rs.getString("work"),
                passageRef = rs.getString("passage_ref"),
            )
        }

        private const val EXACT_MATCH_SQL = "SELECT id FROM entities WHERE LOWER(name) = LOWER(?)"

        private const val ALIAS_MATCH_SQL = """
            SELECT e.id
            FROM entity_aliases ea
            JOIN entities e ON e.id = ea.entity_id
            WHERE LOWER(ea.alias) = LOWER(?)
        """

        private const val TRIGRAM_MATCH_SQL = """
            SELECT id
            FROM entities
            WHERE similarity(name, ?) > ?
            ORDER BY similarity(name, ?) DESC
            LIMIT 1
        """

        private const val NORMALIZE_SQL =
            "SELECT canonical FROM claim_type_aliases WHERE alias = lower(trim(?))"

        private const val CLAIM_TYPE_FILTERED_SQL = """
            SELECT vc.claim_value, s.author, s.work, vc.passage_ref
            FROM variant_claims vc
            JOIN sources s ON s.id = vc.source_id
            WHERE vc.subject_entity_id = ? AND vc.claim_type = ?
        """

        private const val SUBJECT_ONLY_SQL = """
            SELECT vc.claim_value, s.author, s.work, vc.passage_ref
            FROM variant_claims vc
            JOIN sources s ON s.id = vc.source_id
            WHERE vc.subject_entity_id = ?
        """
    }
}
