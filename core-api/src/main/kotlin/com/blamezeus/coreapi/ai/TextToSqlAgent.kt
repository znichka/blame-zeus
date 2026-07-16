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
        - When querying relationships or variant_claims, JOIN sources (via source_id) so the
          result carries attribution.
        - When querying entities directly for its own columns (type, generation, domain), do NOT
          join sources — entities has no source_id foreign key; that attribution does not exist.
        - In a WITH RECURSIVE CTE, the anchor (base case) SELECT and the recursive SELECT must
          each list the exact same columns, and every column referenced in a SELECT must come
          from a table that is actually joined in that same branch — do not reference a table's
          column in the anchor branch unless that table is also present in the anchor's FROM/JOIN.
        - Return ONLY the raw SQL, with no markdown fences, no explanation, no trailing semicolon.
        """
    )
    @UserMessage("Question: {{question}}")
    fun generateSql(@V("schema") schema: String, @V("question") question: String): String
}
