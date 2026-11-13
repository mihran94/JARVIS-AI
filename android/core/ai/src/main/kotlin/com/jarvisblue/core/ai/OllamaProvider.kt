package com.jarvisblue.core.ai

import com.jarvisblue.core.common.AppError
import com.jarvisblue.core.common.Outcome
import com.jarvisblue.core.model.ProviderHealth
import com.jarvisblue.core.model.ProviderHealthState
import com.jarvisblue.core.model.ProviderId
import com.jarvisblue.core.model.TokenUsage
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put

/**
 * Ollama client for a self-hosted model server on the user's own machine.
 *
 * The server is expected to sit behind a VPN or private tunnel — the app never
 * talks to a publicly reachable Ollama instance, and the shared secret is stored
 * in the Keystore-backed vault.
 */
class OllamaProvider(private val httpClient: AiHttpClient) : AiProvider {

    override val providerId: ProviderId = ProviderId.OLLAMA

    override suspend fun complete(request: AiRequest, config: ProviderSettings): AiResponse {
        val model = request.modelId ?: config.defaultModelId ?: DEFAULT_MODEL
        val base = config.resolveBaseUrl(DEFAULT_BASE_URL)
        val url = "$base/api/chat"

        val payload = buildJsonObject {
            put("model", model)
            put("stream", false)
            put("messages", buildJsonArray {
                request.messages.forEach { msg ->
                    add(
                        buildJsonObject {
                            put("role", msg.role)
                            put("content", msg.content)
                        },
                    )
                }
            })
            put("options", buildJsonObject {
                put("temperature", request.temperature ?: config.temperature)
                put("num_predict", request.maxOutputTokens ?: config.maxOutputTokens)
            })
            if (request.enableTools && request.tools.isNotEmpty()) {
                put("tools", buildJsonArray { request.tools.forEach { add(it) } })
            }
        }

        val headers = config.apiKey?.takeIf { it.isNotBlank() }
            ?.let { mapOf("Authorization" to "Bearer $it") }
            ?: emptyMap()

        val outcome = httpClient.postJson(url, payload, headers, config.timeoutSeconds)
        val body = outcome.valueOrNull
            ?: throw (outcome.errorOrNull ?: AppError.Network("Ollama request failed"))
        return parseOllamaResponse(body, model)
    }

    private fun parseOllamaResponse(body: kotlinx.serialization.json.JsonObject, model: String): AiResponse {
        val message = body["message"]?.jsonObject
            ?: throw AppError.Network("Ollama response contained no message")

        val content = message["content"]?.let { (it as? kotlinx.serialization.json.JsonPrimitive)?.content }.orEmpty()

        val toolCalls = message["tool_calls"]?.jsonArray.orEmpty().mapNotNull { element ->
            val fn = element.jsonObject["function"]?.jsonObject ?: return@mapNotNull null
            val name = fn["name"]?.let { (it as? kotlinx.serialization.json.JsonPrimitive)?.content }
                ?: return@mapNotNull null
            val args = fn["arguments"]?.let { (it as? kotlinx.serialization.json.JsonPrimitive)?.content } ?: "{}"
            AiToolCall(id = "call_$name", name = name, argumentsJson = args)
        }

        val promptTokens = body["prompt_eval_count"]?.let {
            (it as? kotlinx.serialization.json.JsonPrimitive)?.content?.toIntOrNull()
        } ?: 0
        val completionTokens = body["eval_count"]?.let {
            (it as? kotlinx.serialization.json.JsonPrimitive)?.content?.toIntOrNull()
        } ?: 0

        return AiResponse(
            content = content,
            toolCalls = toolCalls,
            providerId = providerId.name,
            modelId = body["model"]?.let { (it as? kotlinx.serialization.json.JsonPrimitive)?.content } ?: model,
            usage = TokenUsage(promptTokens = promptTokens, completionTokens = completionTokens),
            finishReason = body["done_reason"]?.let {
                (it as? kotlinx.serialization.json.JsonPrimitive)?.content
            } ?: "stop",
        )
    }

    override suspend fun healthCheck(config: ProviderSettings): ProviderHealth {
        val started = System.currentTimeMillis()
        val base = config.resolveBaseUrl(DEFAULT_BASE_URL)
        val outcome = httpClient.get("$base/api/tags", emptyMap(), 10)
        val elapsed = System.currentTimeMillis() - started
        return when (outcome) {
            is Outcome.Success -> ProviderHealth(
                providerId = providerId,
                state = ProviderHealthState.HEALTHY,
                latencyMs = elapsed,
                detail = "Ollama server reachable",
                checkedAtEpochMs = System.currentTimeMillis(),
            )
            is Outcome.Failure -> ProviderHealth(
                providerId = providerId,
                state = ProviderHealthState.UNAVAILABLE,
                latencyMs = elapsed,
                detail = outcome.error.message,
                checkedAtEpochMs = System.currentTimeMillis(),
            )
        }
    }

    companion object {
        const val DEFAULT_BASE_URL = "http://127.0.0.1:11434"
        const val DEFAULT_MODEL = "llama3.1"
    }
}
