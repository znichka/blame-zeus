package com.blamezeus.coreapi.ai

import com.blamezeus.coreapi.domain.dto.RagResponse
import dev.langchain4j.service.SystemMessage
import dev.langchain4j.service.spring.AiService
import dev.langchain4j.service.spring.AiServiceWiringMode.EXPLICIT

// Bound to "synthesisModel" (temp 0.3) and config.RagConfig's "retrievalAugmentor" bean by Spring
// bean name — LangChain4j EXPLICIT wiring, not @Qualifier (DEV-046). Wired via retrievalAugmentor,
// NOT contentRetriever: AiServices throws if both are set, and only the RagConfig-wrapped augmentor
// actually forwards author/work/passage_ref/stance metadata into the prompt (found live at Track
// H6 — the plain contentRetriever wiring left RagAgent fabricating citations from background
// knowledge, since LangChain4j's default no-arg ContentInjector only ever injects raw chunk text).
// No @UserMessage needed on the single unannotated `question` param — AiServices treats it as the
// user message automatically, same as QueryRouter.classify (Track 0.3).
@AiService(
    wiringMode = EXPLICIT,
    chatModel = "synthesisModel",
    retrievalAugmentor = "retrievalAugmentor",
)
interface RagAgent {

    @SystemMessage(
        """
        You are a Greek mythology scholar. Answer the question using ONLY the provided context
        passages — never rely on outside knowledge, even if you know the answer.

        Each retrieved passage is followed by its own "author:", "work:", "passage_ref:", and
        "stance:" fields. Use those EXACT values verbatim in your citations — never guess,
        paraphrase, or invent an author, work, or passage reference, and never quote the passage's
        prose text itself as if it were a passage reference.

        Cite every factual claim: return JSON matching exactly this shape:
        {"answer": "...", "citations": [{"author": "...", "work": "...", "passageRef": "..."}]}

        If the retrieved context does not support an answer, set "citations" to an empty array
        and make "answer" an explanatory sentence saying the provided texts don't address the
        question — never fabricate a citation to a passage that doesn't actually address it.

        Conflict-aware backstop: if the retrieved passages give different accounts of the same
        point from different sources, present each version with its own attribution rather than
        merging them or silently picking one as correct.
        """
    )
    fun answer(question: String): RagResponse
}
