plugins {
    id("blame-zeus.kotlin-conventions")
    id("org.springframework.boot")
    id("io.spring.dependency-management")
}

// Spring Boot 3.3.x BOM manages Testcontainers 1.19.x, whose bundled docker-java falls back to
// Docker API 1.32 when negotiation fails. Docker Engine 29+ (pulled in by recent Colima releases)
// hard-rejects clients below API 1.40. Testcontainers 1.21.4 backports the fix for this to the 1.x
// line. DEV-008 — see DEVIATIONS.md.
extra["testcontainers.version"] = "1.21.4"

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
    implementation("org.springframework.boot:spring-boot-starter-thymeleaf")
    implementation("org.flywaydb:flyway-core")
    runtimeOnly("org.flywaydb:flyway-database-postgresql")
    runtimeOnly("org.postgresql:postgresql")
    implementation("dev.langchain4j:langchain4j-spring-boot-starter:1.0.0-beta5")
    implementation("dev.langchain4j:langchain4j-open-ai-spring-boot-starter:1.0.0-beta5")
    // Chat model is Anthropic since ADR-008 (DEV-015); OpenAI starter is kept for the Stage 6 embedding bean.
    implementation("dev.langchain4j:langchain4j-anthropic-spring-boot-starter:1.0.0-beta5")
    // langchain4j-pgvector dropped (DEV-025): its EmbeddingStore hardcodes an embedding_id UUID/text
    // schema incompatible with narrative_chunks; Stage 6 uses a custom ContentRetriever over JdbcTemplate.
    // 2.6.0, not 2.8.3 (DEV-006) — 2.7.0+ requires Spring Boot 3.4.x. DEV-009 — see DEVIATIONS.md.
    implementation("org.springdoc:springdoc-openapi-starter-webmvc-ui:2.6.0")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("com.ninja-squad:springmockk:4.0.2")
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:postgresql")
    testRuntimeOnly("org.junit.platform:junit-platform-launcher")
}
