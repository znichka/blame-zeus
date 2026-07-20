package com.blamezeus.coreapi.ai

import com.blamezeus.coreapi.domain.dto.ComposedAnswer
import dev.langchain4j.service.SystemMessage
import dev.langchain4j.service.UserMessage
import dev.langchain4j.service.V
import dev.langchain4j.service.spring.AiService
import dev.langchain4j.service.spring.AiServiceWiringMode.EXPLICIT

// ADR-015 — the single final composition stage QueryService runs on every non-error route, after
// conflict claims are fetched. Bound to "synthesisModel" (temp 0.3) by Spring bean name —
// LangChain4j EXPLICIT wiring, not @Qualifier (DEV-046), same bean RagAgent uses; no new bean in
// LangChain4jConfig.kt, no new provider surface. Unlike RagAgent, this interface declares no
// retrievalAugmentor — it does no retrieval of its own, only rewrites the `material` a handler
// already produced (Track A3), so AiServices sees no augmentor/contentRetriever param to conflict
// with the multi-param @V signature below.
@AiService(wiringMode = EXPLICIT, chatModel = "synthesisModel")
interface AnswerComposer {

    @SystemMessage(
        """
        You are a Greek mythology scholar producing the final, user-facing answer. You are given
        draft material and (optionally) a set of conflicting source claims. Rewrite them into ONE
        fluent, human-readable answer.

        Rules:
        - Use ONLY the provided material and conflicts — never rely on outside knowledge, never
          add a fact that isn't in the material.
        - Every factual sentence carries an inline citation marker like [1], [2], referring to a
          position in the "citations" array you return.
        - "citations" is the deduped union of every source referenced by the material and every
          source referenced by the conflicts, ordered by first appearance in your answer text, such
          that marker [n] indexes citations[n-1] (1-indexed markers, 0-indexed array).
        - Copy each citation's author, work, passageRef, and stance EXACTLY as given in the
          material/conflicts — never guess, paraphrase, or invent a source. Every [n] marker must
          have a matching citations entry, and every citations entry must be referenced by at least
          one [n] marker.
        - If conflicts is the literal string "none", there is nothing to weave in — just compose
          the answer from material.
        - Otherwise, weave EACH conflicting version into the prose, attributed to its source, without
          picking a winner or implying one version is more correct than another — present them as
          "Homer says X [n], while Hesiod says Y [m]", not as a single merged claim.
        - If the material already describes a disagreement between sources (e.g. RAG's own
          conflict-aware backstop), do not narrate the same disagreement a second time just because
          it also appears in conflicts — merge the citations for that point instead of duplicating
          the sentence.

        Return JSON matching exactly this shape:
        {"answer": "...", "citations": [{"author": "...", "work": "...", "passageRef": "...", "stance": "..."}]}
        """
    )
    @UserMessage(
        """
        Question: {{question}}

        Material:
        {{material}}

        Conflicts:
        {{conflicts}}
        """
    )
    fun compose(
        @V("question") question: String,
        @V("material") material: String,
        @V("conflicts") conflicts: String,
    ): ComposedAnswer
}
