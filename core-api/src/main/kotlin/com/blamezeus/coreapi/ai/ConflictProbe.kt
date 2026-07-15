package com.blamezeus.coreapi.ai

import com.blamezeus.coreapi.domain.dto.ProbeResult
import dev.langchain4j.service.SystemMessage
import dev.langchain4j.service.spring.AiService
import dev.langchain4j.service.spring.AiServiceWiringMode.EXPLICIT

// Stage 7 Track B1: one interface serves both the enrichment probe ({subject, claimType}) and any
// future entity-only lookup (Stage 8's MixedQueryHandler can inject this same bean and read only
// .subject) — keeps enrichment to a single LLM call rather than a second EntityExtractor interface,
// per ADR-007 §5's "may be folded into EntityExtractor" allowance. Bound to "routingModel" (temp
// 0.0) by Spring bean name — LangChain4j EXPLICIT wiring, not @Qualifier (DEV-046).
@AiService(wiringMode = EXPLICIT, chatModel = "routingModel")
interface ConflictProbe {

    @SystemMessage(
        """
        You extract two things from a question about Greek mythology:

        1. "subject" — the canonical mythological entity the question is about (e.g. "Zeus",
           "Aphrodite", "Achilles"). Use the standard English name, not an epithet or alias.

        2. "claimType" — which ONE of these modeled claim dimensions the question asks about:
           - parentage (who someone's parents or origin are)
           - marriage (who someone is married to)
           - death (how, or by whom, someone died)
           If the question does not ask about any of these — e.g. it asks about motivation,
           appearance, a narrative event, or "why"/"how" something happened outside these three
           dimensions — return the literal string "none" for claimType. Never force a fit into
           one of the three dimensions just because the subject has stories about it.

        Return JSON matching exactly this shape: {"subject": "...", "claimType": "..."}
        """
    )
    fun extract(question: String): ProbeResult
}
