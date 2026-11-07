package com.jarvisblue.core.model

import kotlinx.serialization.Serializable

@Serializable
enum class ProviderId(val displayName: String, val supportsTools: Boolean, val supportsImages: Boolean) {
    OPENAI("OpenAI", true, true),
    GEMINI("Gemini", true, true),
    MINIMAX("minimax", true, true),
    OLLAMA("Ollama (self-hosted)", true, false),
    OPENAI_COMPATIBLE("OpenAI-compatible endpoint", true, false),
    OFFLINE_ECHO("Built-in offline fallback", false, false),
}

@Serializable
data class ModelDescriptor(
    val id: String,
    val displayName: String,
    val providerId: ProviderId,
    val contextWindow: Int = 8192,
    val supportsTools: Boolean = true,
    val supportsImages: Boolean = false,
    val inputCostPerMillionUsd: Double = 0.0,
    val outputCostPerMillionUsd: Double = 0.0,
    val local: Boolean = false,
)

@Serializable
enum class ProviderHealthState { UNKNOWN, HEALTHY, DEGRADED, UNAVAILABLE, UNCONFIGURED }

@Serializable
data class ProviderHealth(
    val providerId: ProviderId,
    val state: ProviderHealthState,
    val latencyMs: Long = 0L,
    val detail: String = "",
    val checkedAtEpochMs: Long = 0L,
) {
    val usable: Boolean get() = state == ProviderHealthState.HEALTHY || state == ProviderHealthState.DEGRADED
}

@Serializable
data class ProviderConfig(
    val providerId: ProviderId,
    val enabled: Boolean = false,
    val baseUrl: String? = null,
    val defaultModelId: String? = null,
    val priority: Int = 100,
    val temperature: Double = 0.3,
    val maxOutputTokens: Int = 2048,
    val dailyTokenBudget: Int = 200_000,
    val allowOfflineFallback: Boolean = true,
)
