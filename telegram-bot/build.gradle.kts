plugins {
    id("blame-zeus.kotlin-conventions")
    id("org.springframework.boot")
    id("io.spring.dependency-management")
}

dependencies {
    implementation("org.springframework.boot:spring-boot-starter-web")
    // Phase 2: implementation("org.telegram:telegrambots-spring-boot-starter:6.9.7")
}
