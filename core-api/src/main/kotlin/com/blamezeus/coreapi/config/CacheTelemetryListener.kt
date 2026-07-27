package com.blamezeus.coreapi.config

import com.blamezeus.coreapi.service.DebugCapture
import dev.langchain4j.model.anthropic.AnthropicTokenUsage
import dev.langchain4j.model.chat.listener.ChatModelListener
import dev.langchain4j.model.chat.listener.ChatModelResponseContext
import org.slf4j.LoggerFactory
import org.springframework.stereotype.Component

/**
 * ADR-021 — prompt-caching telemetry. Reports, per chat call, how many input tokens were billed at
 * full price, how many were written to Anthropic's prompt cache (~1.25x base input price), and how
 * many were read back from it (~0.1x).
 *
 * This exists because prompt caching fails **silently**. Anthropic enforces a model-specific minimum
 * cacheable prefix — 4,096 tokens on Claude Haiku 4.5, the current `LLM_CHAT_MODEL` — and a system
 * prompt shorter than that produces no cache entry, no error, and no saving. Without these numbers
 * "caching is enabled" is an unfalsifiable claim. `cacheCreation` and `cacheRead` both staying 0
 * across two identical questions issued inside the 5-minute ephemeral TTL is the empirical proof the
 * prefix is under the minimum; `inputTokens` is then the measured prefix size, which is the evidence
 * a future chat-model decision needs (Sonnet 5 minimum 1,024; Opus 5 minimum 512).
 *
 * Wired via `AnthropicChatModel.builder().listeners(...)` in [LangChain4jConfig] rather than by
 * changing the `@AiService` return types to `Result<T>`: the latter would ripple through all three
 * handlers, QueryService, and their tests purely to read a token count.
 *
 * Writes into [DebugCapture]'s ThreadLocal — the listener runs synchronously on the request thread
 * inside the model call, the same cross-boundary reach DEV-064 established for
 * NarrativeChunkContentRetriever, which sits equally deep under LangChain4j's own machinery.
 */
@Component
class CacheTelemetryListener(private val debugCapture: DebugCapture) : ChatModelListener {

    override fun onResponse(responseContext: ChatModelResponseContext) {
        // Telemetry must never break a query: this runs inside the chat call, so anything thrown
        // here would surface as a handler failure and degrade a good answer to `serviceError`.
        try {
            val response = responseContext.chatResponse()
            val usage = response.metadata().tokenUsage()
            // Cast is defensive rather than expected-to-fail: AnthropicChatModel builds an
            // AnthropicTokenUsage and InternalAnthropicHelper.createListenerResponse passes it
            // through unwrapped, but a provider swap (the chat model is provider-agnostic outside
            // LangChain4jConfig, per TECH_GUARDRAILS) would hand us a plain TokenUsage instead.
            val anthropicUsage = usage as? AnthropicTokenUsage
            val inputTokens = usage?.inputTokenCount() ?: 0
            val cacheCreation = anthropicUsage?.cacheCreationInputTokens() ?: 0
            val cacheRead = anthropicUsage?.cacheReadInputTokens() ?: 0

            debugCapture.addTokenUsage(inputTokens, cacheCreation, cacheRead)

            log.debug(
                "Chat call to {}: inputTokens={}, cacheCreationInputTokens={}, cacheReadInputTokens={}",
                response.metadata().modelName(),
                inputTokens,
                cacheCreation,
                cacheRead,
            )
        } catch (e: Exception) {
            log.warn("Cache telemetry failed (query unaffected): {}", e.message)
        }
    }

    companion object {
        private val log = LoggerFactory.getLogger(CacheTelemetryListener::class.java)
    }
}
