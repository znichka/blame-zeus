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

        SQL — the question asks only for the bare structured facts or a list/chain, answerable
        from relational tables of entities and relationships (parentage, type, domain, or tracing
        an ancestor/descendant chain). Example: "Which Olympians are children of Cronus?"
        Example: "Trace Zeus's lineage back to Chaos."

        RAG — the question asks about narrative, motivation, or "why"/"how" a myth unfolds,
        answerable from source text passages.
        Example: "Why did Athena turn Arachne into a spider?"

        MIXED — the question requires filtering or connecting entities by structured criteria and
        then explaining or narrating the result from the source texts (a multi-hop
        filter-then-narrate question). Choose MIXED over SQL whenever the question asks to explain,
        describe, or narrate a filtered set or a connection, not just list it.
        Example: "Which heroes had a divine parent and died at Troy?"
        Example: "Explain the divine lineage that connects Achilles to Zeus, as the sources tell it."

        Do not answer the question itself. Answer only with the route.
        """
    )
    fun classify(question: String): RouteDecision
}
