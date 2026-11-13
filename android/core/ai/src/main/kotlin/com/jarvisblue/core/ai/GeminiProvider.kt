package com.jarvisblue.core.ai

import com.jarvisblue.core.common.AppError
import com.jarvisblue.core.common.Outcome
import com.jarvisblue.core.model.ProviderHealth
import com.jarvisblue.core.model.ProviderHealthState
import com.jarvisblue.core.model.ProviderId
import com.jarvisblue.core.model.TokenUsage
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonElement
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.put

/**
 * Google Gemini (generateContent) provider.
 *
 * Gemini expresses system prompts through `systemInstruction` and tools through
 * `functionDeclarations`; function calls arrive as `functionCall` parts.
 */
class GeminiProvider(private val httpClient: AiHttpClient) : AiProvider {

    override val providerId: ProviderId = ProviderId.GEMINI

    override suspend fun complete(request: AiRequest, config: ProviderSettings): AiResponse {
        val model = request.modelId ?: config.defaultModelId ?: DEFAULT_MODEL
        val base = config.resolveBaseUrl(DEFAULT_BASE_URL)
        val url = "$base/models/$model:generateContent"

        val payload = buildJsonObject {
            val systemText = request.messages.firstOrNull { it.role == "system" }?.content
            if (systemText != null) {
                put("systemInstruction", buildJsonObject {
                    put("parts", buildJsonArray { add(buildJsonObject { put("text", systemText) }) })
                })
            }
            put("contents", buildJsonArray {
                request.messages.filter { it.role != "system" }.forEach { msg ->
                    add(
                        buildJsonObject {
                            put("role", if (msg.role == "assistant") "model" else "user")
                            put("parts", buildJsonArray { add(buildJsonObject { put("text", msg.content) }) })
                        },
                    )
                }
            })
            put("generationConfig", buildJsonObject {
                put("temperature", request.temperature ?: config.temperature)
                put("maxOutputTokens", request.maxOutputTokens ?: config.maxOutputTokens)
            })
            if (request.enableTools && request.tools.isNotEmpty()) {
                put("tools", buildJsonArray {
                    add(
                        buildJsonObject {
                            put("functionDeclarations", buildJsonArray {
                                request.tools.forEach { tool ->
                                    val fn = tool["function"]?.jsonObject
                                    add(
                                        buildJsonObject {
                                            put("name", fn?.get("name")?.asString().orEmpty())
                                            put("description", fn?.get("description")?.asString().orEmpty())
                                            put(
                                                "parameters",
                                                ToolSchema.toGeminiParameters(
                                                    fn?.get("parameters") as? JsonObject ?: buildJsonObject {
                                                        put("type", "object")
                                                        put("properties", buildJsonObject {})
                                                    },
                                                ),
                                            )
                                        },
                                    )
                                }
                            })
                        },
                    )
                })
            }
        }

        val headers = mapOf("x-goog-api-key" to config.apiKey.orEmpty())
        val outcome = httpClient.postJson(url, payload, headers, config.timeoutSeconds)
        val firstError = outcome.errorOrNull
        // When a tool declaration is rejected, retry ONCE as text-only.
        // No tool can be executed in this fallback and no action is claimed.
        val body = if (
            firstError != null && request.enableTools && request.tools.isNotEmpty() &&
            firstError.message.orEmpty().contains("HTTP 400") &&
            (firstError.message.orEmpty().contains("function_declarations", ignoreCase = true) ||
                firstError.message.orEmpty().contains("functionDeclarations", ignoreCase = true))
        ) {
            val noTools = buildJsonObject {
                payload.forEach { (key, value) -> if (key != "tools") put(key, value) }
                put("systemInstruction", buildJsonObject {
                    put("parts", buildJsonArray {
                        add(buildJsonObject {
                            put("text", request.messages.firstOrNull { it.role == "system" }
                                ?.content.orEmpty() + "\nTool execution is unavailable for this " +
                                "message. Answer with text only; never claim any action was executed.")
                        })
                    })
                })
            }
            val retry = httpClient.postJson(url, noTools, headers, config.timeoutSeconds)
            retry.valueOrNull ?: throw (retry.errorOrNull ?: AppError.Network("Gemini text fallback failed"))
        } else {
            outcome.valueOrNull ?: throw (firstError ?: AppError.Network("Gemini request failed"))
        }
        return parseGeminiResponse(body, model)
    }

    private fun parseGeminiResponse(body: JsonObject, model: String): AiResponse {
        val candidate = body["candidates"]?.jsonArray?.firstOrNull()?.jsonObject
            ?: throw AppError.Network("Gemini response contained no candidates")
        val parts = candidate["content"]?.jsonObject?.get("parts")?.jsonArray.orEmpty()

        val text = parts.mapNotNull { part ->
            part.jsonObject["text"]?.asString()
        }.joinToString("\n")

        val toolCalls = parts.mapNotNull { part ->
            val call = part.jsonObject["functionCall"]?.jsonObject ?: return@mapNotNull null
            val name = call["name"]?.asString() ?: return@mapNotNull null
            val args = call["args"] ?: call["arguments"] ?: buildJsonObject {}
            AiToolCall(
                id = "call_$name",
                name = name,
                argumentsJson = args.toString(),
            )
        }

        val usageMeta = body["usageMetadata"]?.jsonObject
        val promptTokens = usageMeta?.get("promptTokenCount").asInt() ?: 0
        val completionTokens = usageMeta?.get("candidatesTokenCount").asInt() ?: 0

        return AiResponse(
            content = text,
            toolCalls = toolCalls,
            providerId = providerId.name,
            modelId = model,
            usage = TokenUsage(promptTokens = promptTokens, completionTokens = completionTokens),
            finishReason = candidate["finishReason"]?.asString() ?: "stop",
        )
    }

    override suspend fun healthCheck(config: ProviderSettings): ProviderHealth {
        val started = System.currentTimeMillis()
        val base = config.resolveBaseUrl(DEFAULT_BASE_URL)
        val url = "$base/models?key=${config.apiKey.orEmpty()}"
        val outcome = httpClient.get(url, emptyMap(), 15)
        val elapsed = System.currentTimeMillis() - started
        return when (outcome) {
            is Outcome.Success -> ProviderHealth(
                providerId = providerId,
                state = ProviderHealthState.HEALTHY,
                latencyMs = elapsed,
                detail = "Gemini endpoint reachable",
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
        const val DEFAULT_BASE_URL = "https://generativelanguage.googleapis.com/v1beta"
        const val DEFAULT_MODEL = "gemini-2.0-flash"
    }
}
