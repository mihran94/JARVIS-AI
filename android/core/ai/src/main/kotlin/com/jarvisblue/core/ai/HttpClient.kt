package com.jarvisblue.core.ai

import com.jarvisblue.core.common.AppError
import com.jarvisblue.core.common.Outcome
import com.jarvisblue.core.common.runCatchingOutcome
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonObject
import java.util.concurrent.TimeUnit

class AiHttpClient(
    private val okHttpClient: OkHttpClient = defaultClient(),
) {

    suspend fun postJson(
        url: String,
        body: JsonObject,
        headers: Map<String, String> = emptyMap(),
        timeoutSeconds: Int = 60,
    ): Outcome<JsonObject> = withContext(Dispatchers.IO) {
        runCatchingOutcome {
            val json = body.toString()
            val request = Request.Builder()
                .url(url)
                .post(json.toRequestBody(JSON_MEDIA_TYPE))
                .apply {
                    headers.forEach { (k, v) -> header(k, v) }
                    header("Content-Type", "application/json")
                }
                .build()

            val client = okHttpClient.newBuilder()
                .callTimeout(timeoutSeconds.toLong(), TimeUnit.SECONDS)
                .build()

            okHttpClient.newCall(request).execute().use { response ->
                val payload = response.body?.string().orEmpty()
                if (!response.isSuccessful) {
                    throw when (response.code) {
                        401, 403 -> AppError.Unauthorized("Provider rejected the API key (HTTP ${response.code})")
                        429 -> AppError.RateLimited("Provider rate limit reached (HTTP 429)")
                        else -> AppError.Network("Provider returned HTTP ${response.code}: ${payload.take(400)}")
                    }
                }
                if (payload.isBlank()) throw AppError.Network("Provider returned an empty body")
                parseObject(payload)
            }
        }
    }

    suspend fun get(
        url: String,
        headers: Map<String, String> = emptyMap(),
        timeoutSeconds: Int = 20,
    ): Outcome<JsonObject> = withContext(Dispatchers.IO) {
        runCatchingOutcome {
            val request = Request.Builder()
                .url(url)
                .get()
                .apply { headers.forEach { (k, v) -> header(k, v) } }
                .build()
            val client = okHttpClient.newBuilder()
                .callTimeout(timeoutSeconds.toLong(), TimeUnit.SECONDS)
                .build()
            okHttpClient.newCall(request).execute().use { response ->
                val payload = response.body?.string().orEmpty()
                if (!response.isSuccessful) {
                    throw AppError.Network("HTTP ${response.code}: ${payload.take(300)}")
                }
                parseObject(payload)
            }
        }
    }

    private fun parseObject(payload: String): JsonObject {
        val element = runCatching { Json.parseToJsonElement(payload) }
            .getOrElse { throw AppError.Network("Provider returned malformed JSON") }
        return element as? JsonObject ?: throw AppError.Network("Provider returned a non-object JSON payload")
    }

    companion object {
        private val JSON_MEDIA_TYPE = "application/json; charset=utf-8".toMediaType()

        fun defaultClient(): OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(20, TimeUnit.SECONDS)
            .readTimeout(60, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .retryOnConnectionFailure(true)
            .build()
    }
}
