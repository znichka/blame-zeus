package com.blamezeus.coreapi.config

import dev.langchain4j.model.anthropic.AnthropicChatModel
import dev.langchain4j.model.chat.ChatModel
import org.springframework.beans.factory.annotation.Value
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration

/**
 * Chat model beans only — no embeddingModel/embeddingStore/contentRetriever beans here
 * (Stage 6; pgvector store beans dropped entirely per DEV-025).
 *
 * Bean method names ARE the wiring key: `@AiService(wiringMode = EXPLICIT, chatModel = "routingModel")`
 * resolves by Spring bean name, not by `@Qualifier` (DEV-046) — since two `ChatModel` beans exist here,
 * every `@AiService` interface must declare EXPLICIT wiring or startup fails with
 * IllegalConfigurationException.
 */
@Configuration
class LangChain4jConfig(
    @Value("\${app.llm.chat-api-key}") private val chatApiKey: String,
    @Value("\${app.llm.chat-model}") private val chatModelName: String,
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
}
