pluginManagement {
    plugins {
        kotlin("jvm") version "2.3.21"
        kotlin("plugin.spring") version "2.3.21"
        id("org.springframework.boot") version "3.3.13"
        id("io.spring.dependency-management") version "1.1.7"
    }
    repositories {
        gradlePluginPortal()
        mavenCentral()
    }
}

dependencyResolutionManagement {
    repositories {
        mavenCentral()
    }
}

rootProject.name = "blame-zeus"

// ingestion/ is a standalone Python offline job — excluded from Gradle scanning
// to prevent IDE/Gradle from picking up .venv artifacts
include("core-api")
