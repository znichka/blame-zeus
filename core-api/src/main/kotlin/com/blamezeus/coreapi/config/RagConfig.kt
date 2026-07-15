package com.blamezeus.coreapi.config

import com.blamezeus.coreapi.ai.NarrativeChunkContentRetriever
import dev.langchain4j.rag.DefaultRetrievalAugmentor
import dev.langchain4j.rag.RetrievalAugmentor
import dev.langchain4j.rag.content.injector.DefaultContentInjector
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration

/**
 * Wraps the Track B [NarrativeChunkContentRetriever] in a [RetrievalAugmentor] whose
 * [DefaultContentInjector] is configured with `metadataKeysToInclude` — the no-arg
 * `DefaultContentInjector()` that `@AiService(contentRetriever = ...)` wires automatically only
 * ever injects raw chunk text into the prompt, never [TextSegment][dev.langchain4j.data.segment.TextSegment]
 * metadata. Without this, `RagAgent` has no real `author`/`work`/`passage_ref` to draw from and
 * fabricates citations from its own background knowledge — found live at Stage 6 Track H6.
 * `RagAgent` must bind via `retrievalAugmentor = "retrievalAugmentor"`, not `contentRetriever`
 * (LangChain4j's `AiServices` throws if both are set — only one of the two is allowed).
 */
@Configuration
class RagConfig(private val narrativeChunkContentRetriever: NarrativeChunkContentRetriever) {

    @Bean
    fun retrievalAugmentor(): RetrievalAugmentor =
        DefaultRetrievalAugmentor.builder()
            .contentRetriever(narrativeChunkContentRetriever)
            .contentInjector(
                DefaultContentInjector.builder()
                    .metadataKeysToInclude(listOf("author", "work", "passage_ref", "stance"))
                    .build()
            )
            .build()
}
