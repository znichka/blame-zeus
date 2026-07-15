package com.blamezeus.coreapi.routing

import dev.langchain4j.service.SystemMessage
import dev.langchain4j.service.spring.AiService
import dev.langchain4j.service.spring.AiServiceWiringMode.EXPLICIT

// Bound to the "routingModel" bean by Spring bean name (LangChain4j EXPLICIT wiring, not
// @Qualifier — DEV-046), since LangChain4jConfig also exposes a "synthesisModel" ChatModel bean.
@AiService(wiringMode = EXPLICIT, chatModel = "routingModel")
interface QueryRouter {

    @SystemMessage(
        """
        You classify a question about Greek mythology into exactly one retrieval strategy.
        Answer with exactly one of: SQL, RAG, MIXED.

        SQL — the question asks for structured facts answerable from relational tables of
        entities and relationships (parentage, type, generation, domain, lineage lookups).
        Example: "Which Olympians are children of Cronus?"

        RAG — the question asks about narrative, motivation, or "why"/"how" a myth unfolds,
        answerable from source text passages.
        Example: "Why did Athena turn Arachne into a spider?"

        MIXED — the question requires filtering entities by structured criteria and then
        narrating the result from source text (a multi-hop filter-then-narrate question).
        Example: "Which heroes had a divine parent and died at Troy?"

        Do not answer the question itself. Answer only with the route.
        """
    )
    fun classify(question: String): RouteDecision
}
