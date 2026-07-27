package com.blamezeus.coreapi.config

import com.blamezeus.coreapi.service.DebugCapture
import dev.langchain4j.data.message.AiMessage
import dev.langchain4j.model.ModelProvider
import dev.langchain4j.model.anthropic.AnthropicTokenUsage
import dev.langchain4j.model.chat.listener.ChatModelResponseContext
import dev.langchain4j.model.chat.request.ChatRequest
import dev.langchain4j.model.chat.response.ChatResponse
import dev.langchain4j.model.chat.response.ChatResponseMetadata
import dev.langchain4j.model.output.TokenUsage
import org.assertj.core.api.Assertions.assertThat
import org.assertj.core.api.Assertions.assertThatCode
import org.junit.jupiter.api.Test

// ADR-021. Pure JVM, no Spring context, no DB, no live LLM call -- the listener is a plain
// ChatModelListener over a DebugCapture ThreadLocal (DEV-064 pattern).
class CacheTelemetryListenerTest {

    private val debugCapture = DebugCapture()
    private val listener = CacheTelemetryListener(debugCapture)

    @Test
    fun `reads Anthropic cache token counts into DebugCapture`() {
        listener.onResponse(
            responseContext(
                AnthropicTokenUsage.builder()
                    .inputTokenCount(3350)
                    .outputTokenCount(180)
                    .cacheCreationInputTokens(3200)
                    .cacheReadInputTokens(0)
                    .build()
            )
        )

        val snapshot = debugCapture.snapshot()
        assertThat(snapshot.inputTokens).isEqualTo(3350)
        assertThat(snapshot.cacheCreationTokens).isEqualTo(3200)
        assertThat(snapshot.cacheReadTokens).isZero()
    }

    // One question makes 3-5 chat calls; the useful figure is the per-request total, so repeated
    // onResponse calls must sum rather than overwrite.
    @Test
    fun `accumulates across the several chat calls a single question makes`() {
        listener.onResponse(responseContext(anthropicUsage(input = 300, creation = 0, read = 0)))
        listener.onResponse(responseContext(anthropicUsage(input = 3350, creation = 0, read = 3200)))
        listener.onResponse(responseContext(anthropicUsage(input = 520, creation = 0, read = 0)))

        val snapshot = debugCapture.snapshot()
        assertThat(snapshot.inputTokens).isEqualTo(4170)
        assertThat(snapshot.cacheReadTokens).isEqualTo(3200)
    }

    // The chat model is provider-agnostic outside LangChain4jConfig (TECH_GUARDRAILS), so a
    // non-Anthropic provider would hand us a plain TokenUsage with no cache fields at all.
    @Test
    fun `degrades to zero cache counts on a non-Anthropic TokenUsage without throwing`() {
        assertThatCode {
            listener.onResponse(responseContext(TokenUsage(1200, 90)))
        }.doesNotThrowAnyException()

        val snapshot = debugCapture.snapshot()
        assertThat(snapshot.inputTokens).isEqualTo(1200)
        assertThat(snapshot.cacheCreationTokens).isZero()
        assertThat(snapshot.cacheReadTokens).isZero()
    }

    // The listener runs inside the chat call: anything it throws would surface as a handler failure
    // and degrade a perfectly good answer to `serviceError`.
    @Test
    fun `a response carrying no token usage at all is swallowed, not thrown`() {
        assertThatCode {
            listener.onResponse(responseContext(tokenUsage = null))
        }.doesNotThrowAnyException()

        assertThat(debugCapture.snapshot().inputTokens).isZero()
    }

    private fun anthropicUsage(input: Int, creation: Int, read: Int): AnthropicTokenUsage =
        AnthropicTokenUsage.builder()
            .inputTokenCount(input)
            .outputTokenCount(0)
            .cacheCreationInputTokens(creation)
            .cacheReadInputTokens(read)
            .build()

    private fun responseContext(tokenUsage: TokenUsage?): ChatModelResponseContext =
        ChatModelResponseContext(
            ChatResponse.builder()
                .aiMessage(AiMessage.from("irrelevant"))
                .metadata(
                    ChatResponseMetadata.builder()
                        .modelName("claude-haiku-4-5-20251001")
                        .tokenUsage(tokenUsage)
                        .build()
                )
                .build(),
            ChatRequest.builder().messages(listOf(dev.langchain4j.data.message.UserMessage.from("q"))).build(),
            ModelProvider.ANTHROPIC,
            mutableMapOf<Any, Any>(),
        )
}
