package com.blamezeus.coreapi.ai

import dev.langchain4j.service.SystemMessage
import dev.langchain4j.service.UserMessage
import dev.langchain4j.service.V
import dev.langchain4j.service.spring.AiService
import dev.langchain4j.service.spring.AiServiceWiringMode.EXPLICIT

// Bound to "routingModel" (temp 0.0) by Spring bean name — LangChain4j EXPLICIT wiring, not
// @Qualifier (DEV-046) — since LangChain4jConfig exposes a second ChatModel bean ("synthesisModel").
@AiService(wiringMode = EXPLICIT, chatModel = "routingModel")
interface TextToSqlAgent {

    @SystemMessage(
        """
        You translate a question about Greek mythology into a single read-only PostgreSQL query.

        Schema:
        {{schema}}

        Rules:
        - Only SELECT or WITH (CTE) statements. Never DROP, DELETE, INSERT, UPDATE, or multiple
          statements separated by ';'.
        - Use ILIKE, not =, when matching entity or source names so case/partial matches work.
        - For enumerated/CHECK-constrained columns (e.g. entities.type, sources.stance, sources.role),
          use the exact lowercase values shown in the schema's "values:" lines — never guess casing
          (write type = 'olympian', not 'Olympian').
        - Use WITH RECURSIVE for lineage/ancestor/descendant questions that require walking the
          relationships table more than one hop.
        - [DEVIATED - see DEVIATIONS.md #DEV-057] ATTRIBUTION IS MANDATORY for any query that reads
          from relationships or variant_claims: you MUST both JOIN sources (via source_id) AND
          project these four columns in the SELECT list using EXACTLY these aliases:
              s.author AS author, s.work AS work, s.stance AS stance,
              and the passage_ref from the relationships / variant_claims row ITSELF (that row's own
              passage-level provenance) AS passage_ref — e.g. r.passage_ref AS passage_ref.
          Do NOT project sources.passage_ref: it is unpopulated (NULL for every source); the citable
          passage lives on the relationships / variant_claims row, not on sources. Never omit these
          columns just because the question only asks for names — the answer must carry its source.
          It is CORRECT to return one row per (entity, source) pair; do NOT use DISTINCT or GROUP BY
          in a way that drops these four columns — prefer duplicate entity rows over dropping
          attribution.
        - When querying entities directly for its own columns (type, generation, domain), do NOT
          join sources — entities has no source_id foreign key; that attribution does not exist.
        - In a WITH RECURSIVE CTE, the anchor (base case) SELECT and the recursive SELECT must
          each list the exact same columns, and every column referenced in a SELECT must come
          from a table that is actually joined in that same branch — do not reference a table's
          column in the anchor branch unless that table is also present in the anchor's FROM/JOIN.
        - Return ONLY the raw SQL, with no markdown fences, no explanation, no trailing semicolon.

        Worked example — "Which Olympians are children of Cronus?" (note the mandatory attribution
        projection; from_id is the parent, to_id the child under 'parent_of'; passage_ref comes from
        the relationships row r, NOT from sources):
        SELECT child.name AS name,
               s.author AS author, s.work AS work, r.passage_ref AS passage_ref, s.stance AS stance
        FROM relationships r
        JOIN entities parent ON parent.id = r.from_id
        JOIN entities child  ON child.id  = r.to_id
        JOIN sources s ON s.id = r.source_id
        WHERE r.relation = 'parent_of' AND parent.name ILIKE 'Cronus' AND child.type = 'olympian'
        """
    )
    @UserMessage("Question: {{question}}")
    fun generateSql(@V("schema") schema: String, @V("question") question: String): String

    // [DEVIATED - see DEVIATIONS.md #DEV-057] Corrective regeneration. When a first query read an
    // attribution-bearing table (relationships/variant_claims) but returned rows with no citable
    // source columns, SqlQueryHandler re-asks once through this method, forcing the mandatory
    // projection while keeping the same answer logic. Bound to the same routingModel (temp 0.0).
    @SystemMessage(
        """
        Your previous PostgreSQL query for this question answered it but OMITTED mandatory source
        attribution. Rewrite it so the result carries attribution: JOIN sources (via source_id) and
        project EXACTLY these columns in the SELECT list —
            s.author AS author, s.work AS work, s.stance AS stance, and the passage_ref from the
            relationships / variant_claims row itself (e.g. r.passage_ref) AS passage_ref
        — keeping the same filtering and the same answer rows otherwise. Do NOT project
        sources.passage_ref (it is NULL for every source); use the relationships / variant_claims
        row's own passage_ref. Return one row per (entity, source) pair; do NOT use DISTINCT or
        GROUP BY in a way that drops those four columns.

        Schema:
        {{schema}}

        The same rules as before still apply: only SELECT or WITH statements; ILIKE (not =) for
        entity/source names; exact lowercase values for enumerated columns; no markdown fences, no
        explanation, no trailing semicolon. Return ONLY the raw SQL.
        """
    )
    @UserMessage(
        """
        Question: {{question}}

        Previous query that must be rewritten to carry attribution:
        {{priorSql}}
        """
    )
    fun generateSqlWithAttribution(
        @V("schema") schema: String,
        @V("question") question: String,
        @V("priorSql") priorSql: String,
    ): String
}
