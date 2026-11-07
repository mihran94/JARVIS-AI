package com.jarvisblue.core.ai

import com.jarvisblue.core.common.AppError
import com.jarvisblue.core.common.Outcome
import com.jarvisblue.core.model.ProviderHealth
import com.jarvisblue.core.model.ProviderHealthState
import com.jarvisblue.core.model.ProviderId
import com.jarvisblue.core.model.TokenUsage
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonNull
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put

/**
 * OpenAI Chat Completions client.
 *
 * The same implementation backs OpenAI, minimax and any OpenAI-compatible
 * endpoint (LM Studio, vLLM, llama.cpp server, OpenRouter…) because they all
 * expose `/v1/chat/completions` with the same tool-calling contract.
 */
open class OpenAiCompatibleProvider(
    override val providerId: ProviderId,
    private val httpClient: AiHttpClient,
    private val defaultBaseUrl: String,
    private val defaultModel: String,
    private val authStyle: AuthStyle = AuthStyle.BEARER,
    private val apiKeyHeader: String = "Authorization",
) : AiProvider {

    enum class AuthStyle { BEARER, RAW_HEADER, QUERY_PARAM_KEY, NONE }

    override suspend fun complete(request: AiRequest, config: ProviderSettings): AiResponse {
        val model = request.modelId ?: config.defaultModelId ?: defaultModel
        val base = config.resolveBaseUrl(defaultBaseUrl)
        val url = if (authStyle == AuthStyle.QUERY_PARAM_KEY) {
            "$base/chat/completions?key=${config.apiKey.orEmpty()}"
        } else {
            "$base/chat/completions"
        }

        val payload = buildJsonObject {
            put("model", model)
            put("temperature", request.temperature ?: config.temperature)
            put("max_tokens", request.maxOutputTokens ?: config.maxOutputTokens)
            put("stream", false)
            put("messages", buildJsonArray {
                request.messages.forEach { msg ->
                    add(
                        buildJsonObject {
                            put("role", msg.role)
                            put("content", msg.content)
                            msg.toolCallId?.let { put("tool_call_id", it) }
                            msg.name?.let { put("name", it) }
                        },
                    )
                }
            })
            if (request.enableTools && request.tools.isNotEmpty()) {
                put("tools", buildJsonArray { request.tools.forEach { add(it) } })
                put("tool_choice", "auto")
            }
        }

        val outcome = httpClient.postJson(url, payload, buildHeaders(config), config.timeoutSeconds)
        val body = outcome.valueOrNull
            ?: throw (outcome.errorOrNull ?: AppError.Network("Request to $providerId failed"))
        return parseOpenAiResponse(body, model)
    }

    private fun buildHeaders(config: ProviderSettings): Map<String, String> {
        val key = config.apiKey?.takeIf { it.isNotBlank() } ?: return emptyMap()
        return when (authStyle) {
            AuthStyle.BEARER -> mapOf(apiKeyHeader to "Bearer $key")
            AuthStyle.RAW_HEADER -> mapOf(apiKeyHeader to key)
            AuthStyle.QUERY_PARAM_KEY -> emptyMap()
            AuthStyle.NONE -> emptyMap()
        }
    }

    private fun parseOpenAiResponse(body: JsonObject, model: String): AiResponse {
        val choice = body["choices"]?.jsonArray?.firstOrNull()?.jsonObject
            ?: throw AppError.Network("Provider response contained no choices")
        val message = choice["message"]?.jsonObject
            ?: throw AppError.Network("Provider response contained no message")

        val content = message["content"].asString().orEmpty()

        val toolCalls = message["tool_calls"]?.jsonArray.orEmpty().mapNotNull { element ->
            val obj = element.jsonObject
            val fn = obj["function"]?.jsonObject ?: return@mapNotNull null
            val name = fn["name"].asString() ?: return@mapNotNull null
            AiToolCall(
                id = obj["id"].asString() ?: "call_$name",
                name = name,
                argumentsJson = fn["arguments"].asString() ?: "{}",
            )
        }

        val usageObj = body["usage"]?.jsonObject
        val promptTokens = usageObj?.get("prompt_tokens").asInt() ?: 0
        val completionTokens = usageObj?.get("completion_tokens").asInt() ?: 0

        return AiResponse(
            content = content,
            toolCalls = toolCalls,
            providerId = providerId.name,
            modelId = body["model"].asString() ?: model,
            usage = TokenUsage(promptTokens = promptTokens, completionTokens = completionTokens),
            finishReason = choice["finish_reason"].asString() ?: "stop",
        )
    }

    override suspend fun healthCheck(config: ProviderSettings): ProviderHealth {
        val started = System.currentTimeMillis()
        val base = config.resolveBaseUrl(defaultBaseUrl)
        val url = if (authStyle == AuthStyle.QUERY_PARAM_KEY) {
            "$base/models?key=${config.apiKey.orEmpty()}"
        } else {
            "$base/models"
        }
        val outcome = httpClient.get(url, buildHeaders(config), 15)
        val elapsed = System.currentTimeMillis() - started
        return when (outcome) {
            is Outcome.Success -> ProviderHealth(
                providerId = providerId,
                state = ProviderHealthState.HEALTHY,
                latencyMs = elapsed,
                detail = "Endpoint reachable",
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
}

/** OpenAI proper. */
class OpenAiProvider(httpClient: AiHttpClient) :
    OpenAiCompatibleProvider(
        providerId = ProviderId.OPENAI,
        httpClient = httpClient,
        defaultBaseUrl = DEFAULT_BASE_URL,
        defaultModel = DEFAULT_MODEL,
    )

/**
 * minimax exposes an OpenAI-compatible surface; the base URL is user-configurable
 * because the regional endpoints differ.
 */
class MiniMaxProvider(httpClient: AiHttpClient) :
    OpenAiCompatibleProvider(
        providerId = ProviderId.MINIMAX,
        httpClient = httpClient,
        defaultBaseUrl = DEFAULT_BASE_URL,
        defaultModel = DEFAULT_MODEL,
    )

/** Any user-supplied OpenAI-compatible gateway (LM Studio, vLLM, OpenRouter…). */
class GenericOpenAiProvider(httpClient: AiHttpClient) :
    OpenAiCompatibleProvider(
        providerId = ProviderId.OPENAI_COMPATIBLE,
        httpClient = httpClient,
        defaultBaseUrl = DEFAULT_BASE_URL,
        defaultModel = DEFAULT_MODEL,
    )

const val DEFAULT_BASE_URL = "https://api.openai.com/v1"
const val DEFAULT_MODEL = "gpt-4o-mini"

internal fun JsonElement?.asString(): String? = when (this) {
    null, JsonNull -> null
    is JsonPrimitive -> if (isString) content else content
    else -> null
}

internal fun JsonElement?.asInt(): Int? = asString()?.trim()?.toIntOrNull()
