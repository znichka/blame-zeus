package com.blamezeus.coreapi.config

import io.swagger.v3.oas.models.OpenAPI
import io.swagger.v3.oas.models.info.Info
import org.springframework.context.annotation.Bean
import org.springframework.context.annotation.Configuration

// Stage 9 Track D — springdoc 2.6.0 (DEV-009) already autoconfigures Swagger UI / /v3/api-docs with
// zero config; this bean only customizes the title/description shown there.
@Configuration
class OpenApiConfig {

    @Bean
    fun customOpenAPI(): OpenAPI =
        OpenAPI().info(
            Info()
                .title("blame-zeus Core API")
                .version("1.0")
                .description("Greek Mythology Lore Assistant — source-attributed Q&A with conflict awareness")
        )
}
