package com.jarvisblue.core.ai

import com.jarvisblue.core.model.Language
import com.jarvisblue.core.model.ProviderId
import com.jarvisblue.core.model.ProviderHealth
import com.jarvisblue.core.model.TokenUsage
import kotlinx.serialization.SerialName
import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

@Serializable
data class AiMessage(
    val role: String,
    val content: String,
    @SerialName("tool_call_id") val toolCallId: String? = null,
    val name: String? = null,
)

@Serializable
data class AiToolCall(
    val id: String,
    val name: String,
    @SerialName("arguments_json") val argumentsJson: String,
)

@Serializable
data class AiRequest(
    val messages: List<AiMessage>,
    val modelId: String? = null,
    val temperature: Double? = null,
    val maxOutputTokens: Int? = null,
    val tools: List<JsonObject> = emptyList(),
    val responseLanguage: Language? = null,
    val userLocale: String = "en-US",
    val enableTools: Boolean = true,
)

@Serializable
data class AiResponse(
    val content: String,
    val toolCalls: List<AiToolCall> = emptyList(),
    val providerId: String,
    val modelId: String,
    val usage: TokenUsage = TokenUsage(),
    val finishReason: String = "stop",
    val latencyMs: Long = 0L,
    val rawError: String? = null,
    val health: ProviderHealth? = null,
)

enum class TaskKind {
    CHAT, CODING, VISION, DOCUMENT, QUICK_LOOKUP, LONG_REASONING, TRANSLATION, MATH,
}

/**
 * Holder for the configured provider implementations.
 *
 * A dedicated type is used instead of a raw `Map` because Dagger treats a
 * `Map<K, V>` dependency as a multibinding map, which cannot be satisfied by a
 * single `@Provides` method.
 */
class ProviderRegistry(val providers: Map<ProviderId, AiProvider>) {
    operator fun get(id: ProviderId): AiProvider? = providers[id]
    val ids: Set<ProviderId> get() = providers.keys
}

interface AiProvider {
    val providerId: com.jarvisblue.core.model.ProviderId
    suspend fun complete(request: AiRequest, config: ProviderSettings): AiResponse
    suspend fun healthCheck(config: ProviderSettings): ProviderHealth
}

@Serializable
data class ProviderSettings(
    val baseUrl: String? = null,
    val apiKey: String? = null,
    val defaultModelId: String? = null,
    val temperature: Double = 0.3,
    val maxOutputTokens: Int = 2048,
    val timeoutSeconds: Int = 60,
) {
    fun resolveBaseUrl(fallback: String): String =
        (baseUrl?.trim()?.takeIf { it.isNotEmpty() } ?: fallback).trimEnd('/')
}
