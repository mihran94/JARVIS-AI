pluginManagement {
    repositories {
        google {
            content {
                includeGroupByRegex("com\\.android.*")
                includeGroupByRegex("com\\.google.*")
                includeGroupByRegex("androidx.*")
            }
        }
        mavenCentral()
        gradlePluginPortal()
    }
}

dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}

rootProject.name = "JARVIS BLUE MOBILE"

include(":app")

// ---- Core (platform-independent + platform layers) ----
include(":core:model")        // pure Kotlin: domain models, tool contracts, risk model
include(":core:common")       // pure Kotlin: dispatchers, Result, logging, time
include(":core:security")     // Android: Keystore, secret vault, biometrics, audit trail
include(":core:database")     // Android: Room + SQLCipher, DAOs, mappers
include(":core:ai")           // Android: multi-provider AI clients + router
include(":core:tools")        // Android: tool registry, schema validation, risk gate, device control
include(":core:voice")        // Android: wake word, STT/TTS, language detection
include(":core:windows")      // Android: JARVIS BLUE desktop bridge client
include(":core:ui")           // Android: Compose design system (blue/black command centre)

// ---- Features (thin UI + ViewModel layers) ----
include(":feature:chat")        // AI conversation + tool-call trace
include(":feature:assistant")   // voice assistant / dashboard
include(":feature:studio")      // coding studio + cyber lab + quantum lab
include(":feature:command")     // tasks, memory, permissions, windows dashboard, settings
