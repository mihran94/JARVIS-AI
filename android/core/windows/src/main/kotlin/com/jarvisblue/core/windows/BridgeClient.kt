package com.jarvisblue.core.windows

import com.jarvisblue.core.common.AppError
import com.jarvisblue.core.common.Outcome
import com.jarvisblue.core.common.runCatchingOutcomeSuspend
import com.jarvisblue.core.model.BridgeJob
import com.jarvisblue.core.model.BridgeJobKind
import com.jarvisblue.core.model.BridgeJobState
import com.jarvisblue.core.model.BridgeRequest
import com.jarvisblue.core.model.PcState
import com.jarvisblue.core.model.PcStatus
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import kotlinx.serialization.json.Json
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonArray
import kotlinx.serialization.json.jsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import okhttp3.MediaType.Companion.toMediaType
import okhttp3.OkHttpClient
import okhttp3.Request
import okhttp3.RequestBody.Companion.toRequestBody
import okhttp3.WebSocket
import okhttp3.WebSocketListener
import okio.ByteString
import java.security.MessageDigest
import java.util.concurrent.TimeUnit
import javax.crypto.Mac
import javax.crypto.spec.SecretKeySpec

/**
 * Client for the JARVIS BLUE Windows desktop bridge.
 *
 * Transport rules:
 *  - HTTPS/TLS only. There is no plaintext fallback for the control API.
 *  - Every request is signed with HMAC-SHA256 over a canonical string using a
 *    shared secret that never leaves the Keystore-backed vault.
 *  - A timestamp + nonce makes each signature single-use, so a captured request
 *    cannot be replayed.
 *
 * The Windows machine is expected to sit behind a VPN or a private tunnel
 * (Tailscale / WireGuard). No control port is published to the public internet.
 */
class BridgeClient(
    private val httpClient: OkHttpClient = defaultClient(),
    private val secretProvider: suspend () -> String?,
) {

    private val json = Json { ignoreUnknownKeys = true; encodeDefaults = true }

    suspend fun status(baseUrl: String): Outcome<PcStatus> = withContext(Dispatchers.IO) {
        runCatchingOutcomeSuspend {
            val body = signedGet(baseUrl, "/api/status")
            parseStatus(body)
        }
    }

    suspend fun jobs(baseUrl: String): Outcome<List<BridgeJob>> = withContext(Dispatchers.IO) {
        runCatchingOutcomeSuspend {
            val body = signedGet(baseUrl, "/api/jobs")
            val array = body["jobs"] as? JsonArray ?: JsonArray(emptyList())
            array.map { parseJob(it.jsonObject) }
        }
    }

    suspend fun submitJob(baseUrl: String, request: BridgeRequest): Outcome<BridgeJob> =
        withContext(Dispatchers.IO) {
            runCatchingOutcomeSuspend {
                val payload = buildJsonObject {
                    put("kind", request.kind.name)
                    put("title", request.title)
                    put("payload", request.payloadJson)
                    put("requireApproval", request.requireApproval)
                }
                val body = signedPost(baseUrl, "/api/jobs", payload.toString())
                parseJob(body)
            }
        }

    suspend fun cancelJob(baseUrl: String, jobId: String): Outcome<Boolean> =
        withContext(Dispatchers.IO) {
            runCatchingOutcomeSuspend {
                val body = signedPost(baseUrl, "/api/jobs/$jobId/cancel", "{}")
                (body["ok"] as? JsonPrimitive)?.content?.toBooleanStrictOrNull() ?: false
            }
        }

    /** Opens the live event socket. Failures are reported through [onEvent]. */
    fun openEventSocket(
        baseUrl: String,
        onEvent: (String) -> Unit,
        onClosed: (String?) -> Unit,
    ): WebSocket? {
        val secret = runCatching { kotlinx.coroutines.runBlocking { secretProvider() } }.getOrNull()
            ?: return null
        val wsUrl = baseUrl.replaceFirst("https://", "wss://").replaceFirst("http://", "ws://") + "/ws"
        val timestamp = System.currentTimeMillis().toString()
        val nonce = nonce()

        val request = Request.Builder()
            .url(wsUrl)
            .header("X-Jarvis-Key-Id", KEY_ID)
            .header("X-Jarvis-Timestamp", timestamp)
            .header("X-Jarvis-Nonce", nonce)
            .header("X-Jarvis-Signature", sign("GET", "/ws", timestamp, "", secret, nonce))
            .build()

        return httpClient.newWebSocket(request, object : WebSocketListener() {
            override fun onMessage(webSocket: WebSocket, text: String) = onEvent(text)
            override fun onMessage(webSocket: WebSocket, bytes: ByteString) = onEvent(bytes.utf8())
            override fun onFailure(webSocket: WebSocket, t: Throwable, response: okhttp3.Response?) =
                onClosed(t.message)
            override fun onClosed(webSocket: WebSocket, code: Int, reason: String) = onClosed(reason)
        })
    }

    // ------------------------------------------------------------------ internals

    private suspend fun signedGet(baseUrl: String, path: String): JsonObject {
        val secret = requireSecret()
        val timestamp = System.currentTimeMillis().toString()
        val nonce = nonce()
        val request = Request.Builder()
            .url(baseUrl.trimEnd('/') + path)
            .get()
            .header("X-Jarvis-Key-Id", KEY_ID)
            .header("X-Jarvis-Timestamp", timestamp)
            .header("X-Jarvis-Nonce", nonce)
            .header("X-Jarvis-Signature", sign("GET", path, timestamp, "", secret, nonce))
            .build()
        return execute(request)
    }

    private suspend fun signedPost(baseUrl: String, path: String, body: String): JsonObject {
        val secret = requireSecret()
        val timestamp = System.currentTimeMillis().toString()
        val nonce = nonce()
        val request = Request.Builder()
            .url(baseUrl.trimEnd('/') + path)
            .post(body.toRequestBody(JSON_MEDIA))
            .header("Content-Type", "application/json")
            .header("X-Jarvis-Key-Id", KEY_ID)
            .header("X-Jarvis-Timestamp", timestamp)
            .header("X-Jarvis-Nonce", nonce)
            .header("X-Jarvis-Signature", sign("POST", path, timestamp, body, secret, nonce))
            .build()
        return execute(request)
    }

    private fun execute(request: Request): JsonObject {
        httpClient.newCall(request).execute().use { response ->
            val payload = response.body?.string().orEmpty()
            if (!response.isSuccessful) {
                throw when (response.code) {
                    401, 403 -> AppError.Unauthorized("The Windows bridge rejected the pairing signature")
                    404 -> AppError.NotSupported("The Windows bridge does not expose that endpoint")
                    else -> AppError.Network("Windows bridge returned HTTP ${response.code}: ${payload.take(200)}")
                }
            }
            val element = runCatching { json.parseToJsonElement(payload) }.getOrElse {
                throw AppError.Network("Windows bridge returned malformed JSON")
            }
            return element as? JsonObject ?: throw AppError.Network("Windows bridge returned a non-object payload")
        }
    }

    private suspend fun requireSecret(): String = secretProvider()
        ?: throw AppError.NotConfigured("No pairing secret is configured for the Windows bridge")

    private fun parseStatus(body: JsonObject): PcStatus = PcStatus(
        peerId = body["peer_id"]?.jsonPrimitive?.contentOrEmpty() ?: "unknown",
        state = when (body["state"]?.jsonPrimitive?.contentOrEmpty()) {
            "online" -> PcState.ONLINE
            "offline" -> PcState.OFFLINE
            "degraded" -> PcState.DEGRADED
            "pairing_required" -> PcState.PAIRING_REQUIRED
            else -> PcState.UNKNOWN
        },
        hostname = body["hostname"]?.jsonPrimitive?.contentOrEmpty().orEmpty(),
        platform = body["platform"]?.jsonPrimitive?.contentOrEmpty().orEmpty(),
        agentVersion = body["agent_version"]?.jsonPrimitive?.contentOrEmpty().orEmpty(),
        lastHeartbeatEpochMs = body["heartbeat"]?.jsonPrimitive?.contentOrEmpty()?.toLongOrNull() ?: 0L,
        queuedJobs = body["queued_jobs"]?.jsonPrimitive?.contentOrNull()?.toIntOrNull() ?: 0,
        runningJobs = body["running_jobs"]?.jsonPrimitive?.contentOrNull()?.toIntOrNull() ?: 0,
        cpuPercent = body["cpu_percent"]?.jsonPrimitive?.contentOrNull()?.toDoubleOrNull(),
        memoryPercent = body["memory_percent"]?.jsonPrimitive?.contentOrNull()?.toDoubleOrNull(),
        gpuPercent = body["gpu_percent"]?.jsonPrimitive?.contentOrNull()?.toDoubleOrNull(),
        diskFreeGb = body["disk_free_gb"]?.jsonPrimitive?.contentOrNull()?.toDoubleOrNull(),
        detail = body["detail"]?.jsonPrimitive?.contentOrEmpty().orEmpty(),
    )

    private fun parseJob(body: JsonObject): BridgeJob = BridgeJob(
        id = body["id"]?.jsonPrimitive?.contentOrEmpty().orEmpty(),
        kind = runCatching {
            BridgeJobKind.valueOf(body["kind"]?.jsonPrimitive?.contentOrEmpty().orEmpty())
        }.getOrDefault(BridgeJobKind.CUSTOM),
        title = body["title"]?.jsonPrimitive?.contentOrEmpty().orEmpty(),
        state = runCatching {
            BridgeJobState.valueOf(body["state"]?.jsonPrimitive?.contentOrEmpty().orEmpty())
        }.getOrDefault(BridgeJobState.QUEUED),
        progress = body["progress"]?.jsonPrimitive?.contentOrNull()?.toDoubleOrNull() ?: 0.0,
        createdAtEpochMs = body["created_at"]?.jsonPrimitive?.contentOrNull()?.toLongOrNull() ?: 0L,
        updatedAtEpochMs = body["updated_at"]?.jsonPrimitive?.contentOrNull()?.toLongOrNull() ?: 0L,
        logPreview = (body["logs"] as? JsonArray).orEmpty().mapNotNull {
            (it as? JsonPrimitive)?.contentOrEmpty()
        },
        outputFiles = (body["outputs"] as? JsonArray).orEmpty().mapNotNull {
            (it as? JsonPrimitive)?.contentOrEmpty()
        },
        error = body["error"]?.jsonPrimitive?.contentOrEmpty(),
        requiresApproval = body["requires_approval"]?.jsonPrimitive?.contentOrNull()?.toBooleanStrictOrNull() ?: false,
    )

    companion object {
        const val KEY_ID = "jarvis-blue-mobile-v1"
        private val JSON_MEDIA = "application/json; charset=utf-8".toMediaType()

        fun defaultClient(): OkHttpClient = OkHttpClient.Builder()
            .connectTimeout(15, TimeUnit.SECONDS)
            .readTimeout(30, TimeUnit.SECONDS)
            .writeTimeout(30, TimeUnit.SECONDS)
            .pingInterval(30, TimeUnit.SECONDS)
            .build()

        fun nonce(): String = java.util.UUID.randomUUID().toString()

        fun sha256Hex(input: String): String {
            val digest = MessageDigest.getInstance("SHA-256").digest(input.toByteArray())
            return digest.joinToString("") { "%02x".format(it) }
        }

        /**
         * Canonical signature over method, path, timestamp, nonce and body.
         * The server recomputes exactly this string, so both sides must agree.
         */
        fun sign(
            method: String,
            path: String,
            timestamp: String,
            body: String,
            secret: String,
            nonce: String = nonce(),
        ): String {
            val canonical = listOf(
                method.uppercase(),
                path,
                timestamp,
                nonce,
                sha256Hex(body),
            ).joinToString("\n")
            val mac = Mac.getInstance("HmacSHA256")
            mac.init(SecretKeySpec(secret.toByteArray(Charsets.UTF_8), "HmacSHA256"))
            return mac.doFinal(canonical.toByteArray(Charsets.UTF_8))
                .joinToString("") { "%02x".format(it) }
        }
    }
}

private fun JsonPrimitive.contentOrEmpty(): String =
    if (this is kotlinx.serialization.json.JsonNull) "" else content

private fun JsonPrimitive.contentOrNull(): String? =
    if (this is kotlinx.serialization.json.JsonNull) null else content
