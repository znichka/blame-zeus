plugins {
    id("blame-zeus.kotlin-conventions")
    id("org.springframework.boot")
    id("io.spring.dependency-management")
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    implementation("org.springframework.boot:spring-boot-starter-data-jpa")
    implementation("org.springframework.boot:spring-boot-starter-thymeleaf")
    implementation("org.flywaydb:flyway-core")
    runtimeOnly("org.flywaydb:flyway-database-postgresql")
    runtimeOnly("org.postgresql:postgresql")
    implementation("dev.langchain4j:langchain4j-spring-boot-starter:1.0.0-beta5")
    implementation("dev.langchain4j:langchain4j-open-ai-spring-boot-starter:1.0.0-beta5")
    implementation("dev.langchain4j:langchain4j-pgvector:1.0.0-beta5")
    implementation("org.springdoc:springdoc-openapi-starter-webmvc-ui:2.8.3")

    testImplementation("org.springframework.boot:spring-boot-starter-test")
    testImplementation("com.ninja-squad:springmockk:4.0.2")
    testImplementation("org.testcontainers:junit-jupiter")
    testImplementation("org.testcontainers:postgresql")
}
