package com.blamezeus.coreapi.config

import dev.langchain4j.model.anthropic.AnthropicChatModel
import dev.langchain4j.model.chat.ChatModel
import dev.langchain4j.model.embedding.EmbeddingModel
import dev.langchain4j.model.openai.OpenAiEmbeddingModel
import org.springframework.beans.factory.annotation.Value
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration

/**
 * Chat model beans + the single embeddingModel bean (Stage 6). No embeddingStore/contentRetriever
 * beans here — pgvector store beans dropped entirely per DEV-025; Stage 6 retrieval uses a custom
 * ContentRetriever over JdbcTemplate (see ai/ package) instead.
 *
 * Bean method names ARE the wiring key: `@AiService(wiringMode = EXPLICIT, chatModel = "routingModel")`
 * resolves by Spring bean name, not by `@Qualifier` (DEV-046) — since two `ChatModel` beans exist here,
 * every `@AiService` interface must declare EXPLICIT wiring or startup fails with
 * IllegalConfigurationException. Only one `EmbeddingModel` bean exists, so no EXPLICIT-wiring dance
 * is needed for it.
 *
 * ADR-021 — prompt caching. `cacheSystemMessages` makes LangChain4j attach
 * `cache_control: {"type": "ephemeral"}` to the system block, so Anthropic bills a repeat of the
 * same system prefix at ~0.1x instead of full price. Two things a future reader needs to know:
 *
 *  1. It must be set on BOTH beans. They are separate `AnthropicChatModel` instances that differ
 *     only by temperature; the flag does not carry across.
 *  2. **It saves nothing today, by design.** Anthropic enforces a model-specific *minimum cacheable
 *     prefix*, and Claude Haiku 4.5 (the current `LLM_CHAT_MODEL`) has the highest of any current
 *     model at 4,096 tokens. Every system prompt here is below it — the largest,
 *     `TextToSqlAgent.GENERATE_SQL_SYSTEM_MESSAGE` plus the injected schema, measures ~3,350 tokens.
 *     Below the minimum, `cache_control` is a silent no-op: no cache entry, no error, no charge, no
 *     saving. The flag is wired anyway because it is free, and it starts paying the moment the
 *     prefix clears the bar (a larger schema, or a chat model with a lower minimum). Verify with
 *     [CacheTelemetryListener], never by assumption. Full reasoning in
 *     `docs/adr/adr-021-prompt-caching.md`.
 *
 * This is provider-side prompt caching — a builder flag, no new dependency and no stored responses.
 * It is NOT the "Redis or any caching layer" on the TECH_GUARDRAILS Do-Not-Add list, which is about
 * a response cache.
 */
@Configuration
class LangChain4jConfig(
    @Value("\${app.llm.chat-api-key}") private val chatApiKey: String,
    @Value("\${app.llm.chat-model}") private val chatModelName: String,
    @Value("\${app.llm.prompt-cache-enabled}") private val promptCacheEnabled: Boolean,
    @Value("\${app.llm.embedding-api-key}") private val embeddingApiKey: String,
    @Value("\${app.llm.embedding-model}") private val embeddingModelName: String,
    private val cacheTelemetryListener: CacheTelemetryListener,
) {

    @Bean
    fun routingModel(): ChatModel =
        AnthropicChatModel.builder()
            .apiKey(chatApiKey)
            .modelName(chatModelName)
            .temperature(0.0)
            .cacheSystemMessages(promptCacheEnabled)
            .listeners(listOf(cacheTelemetryListener))
            .build()

    @Bean
    fun synthesisModel(): ChatModel =
        AnthropicChatModel.builder()
            .apiKey(chatApiKey)
            .modelName(chatModelName)
            .temperature(0.3)
            .cacheSystemMessages(promptCacheEnabled)
            .listeners(listOf(cacheTelemetryListener))
            .build()

    // text-embedding-3-large returns 3072-dim vectors natively (ADR-013) — dimensions() left unset
    // deliberately; OpenAiEmbeddingModelName.knownDimension() already resolves 3072 for this model.
    @Bean
    fun embeddingModel(): EmbeddingModel =
        OpenAiEmbeddingModel.builder()
            .apiKey(embeddingApiKey)
            .modelName(embeddingModelName)
            .build()
}
