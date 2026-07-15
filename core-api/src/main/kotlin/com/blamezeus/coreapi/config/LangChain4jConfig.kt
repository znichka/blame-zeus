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
 */
@Configuration
class LangChain4jConfig(
    @Value("\${app.llm.chat-api-key}") private val chatApiKey: String,
    @Value("\${app.llm.chat-model}") private val chatModelName: String,
    @Value("\${app.llm.embedding-api-key}") private val embeddingApiKey: String,
    @Value("\${app.llm.embedding-model}") private val embeddingModelName: String,
) {

    @Bean
    fun routingModel(): ChatModel =
        AnthropicChatModel.builder()
            .apiKey(chatApiKey)
            .modelName(chatModelName)
            .temperature(0.0)
            .build()

    @Bean
    fun synthesisModel(): ChatModel =
        AnthropicChatModel.builder()
            .apiKey(chatApiKey)
            .modelName(chatModelName)
            .temperature(0.3)
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
