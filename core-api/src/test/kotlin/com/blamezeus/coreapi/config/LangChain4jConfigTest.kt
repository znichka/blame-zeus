package com.blamezeus.coreapi.config

import com.blamezeus.coreapi.AbstractContainerTest
import dev.langchain4j.model.anthropic.AnthropicChatModel
import dev.langchain4j.model.chat.ChatModel
import org.assertj.core.api.Assertions.assertThat
import org.junit.jupiter.api.Test
import org.springframework.beans.factory.annotation.Autowired
import org.springframework.beans.factory.annotation.Qualifier

/**
 * ADR-021. Pins the prompt-caching wiring by reflecting over the built models rather than by making
 * a call — TECH_GUARDRAILS forbids live LLM calls in tests, and `cacheSystemMessages` is a private
 * field with no getter, so reflection is the only way to assert it without hitting the API.
 *
 * The flag being set on BOTH beans is the thing worth pinning: `routingModel` and `synthesisModel`
 * are independent AnthropicChatModel instances differing only by temperature, so it is easy to add
 * the flag to one and silently leave the other paying full price on every RAG and composer call.
 */
class LangChain4jConfigTest : AbstractContainerTest() {

    @Autowired
    @Qualifier("routingModel")
    lateinit var routingModel: ChatModel

    @Autowired
    @Qualifier("synthesisModel")
    lateinit var synthesisModel: ChatModel

    @Autowired
    lateinit var cacheTelemetryListener: CacheTelemetryListener

    @Test
    fun `both chat model beans enable system-message caching`() {
        assertThat(cacheSystemMessagesOf(routingModel)).isTrue()
        assertThat(cacheSystemMessagesOf(synthesisModel)).isTrue()
    }

    // Without the listener attached, the cache token counts never reach DebugCapture and the
    // "caching is enabled" claim becomes unverifiable — which is the whole point of ADR-021.
    @Test
    fun `both chat model beans carry the cache telemetry listener`() {
        assertThat(listenersOf(routingModel)).contains(cacheTelemetryListener)
        assertThat(listenersOf(synthesisModel)).contains(cacheTelemetryListener)
    }

    // cacheTools is deliberately left at its default: no `tools` are ever sent (structured output
    // goes through LangChain4j's ServiceOutputParser on the user message), so enabling it would
    // attach cache_control to nothing.
    @Test
    fun `tool caching is left off, since no tools are sent`() {
        assertThat(booleanField(routingModel, "cacheTools")).isFalse()
        assertThat(booleanField(synthesisModel, "cacheTools")).isFalse()
    }

    private fun cacheSystemMessagesOf(model: ChatModel): Boolean =
        booleanField(model, "cacheSystemMessages")

    private fun booleanField(model: ChatModel, name: String): Boolean =
        AnthropicChatModel::class.java.getDeclaredField(name)
            .apply { isAccessible = true }
            .getBoolean(model)

    @Suppress("UNCHECKED_CAST")
    private fun listenersOf(model: ChatModel): List<Any> =
        AnthropicChatModel::class.java.getDeclaredField("listeners")
            .apply { isAccessible = true }
            .get(model) as List<Any>
}
