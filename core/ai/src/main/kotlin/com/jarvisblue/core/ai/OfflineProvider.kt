package com.jarvisblue.core.ai

import com.jarvisblue.core.model.Language
import com.jarvisblue.core.model.ProviderHealth
import com.jarvisblue.core.model.ProviderHealthState
import com.jarvisblue.core.model.ProviderId
import com.jarvisblue.core.model.TokenUsage

/**
 * Deterministic offline fallback.
 *
 * This provider never leaves the device and never claims to be an AI: it explains
 * which capability is unavailable and how to restore it. It exists so the app
 * degrades honestly instead of hallucinating while offline.
 */
class OfflineProvider : AiProvider {

    override val providerId: ProviderId = ProviderId.OFFLINE_ECHO

    override suspend fun complete(request: AiRequest, config: ProviderSettings): AiResponse {
        val lastUser = request.messages.lastOrNull { it.role == "user" }?.content.orEmpty()
        val reply = buildString {
            append("Offline mode. ")
            append("I could not reach a configured AI provider, so I will not guess at an answer.\n\n")
            append("You asked: \"")
            append(lastUser.take(300))
            append("\"\n\n")
            append("To restore live intelligence, open Settings → AI Providers and enable a ")
            append("provider with a valid API key, or point JARVIS BLUE at your own ")
            append("Ollama server over a private tunnel.")
        }
        return AiResponse(
            content = reply,
            providerId = providerId.name,
            modelId = "offline-fallback",
            usage = TokenUsage(promptTokens = 0, completionTokens = 0),
            finishReason = "offline",
        )
    }

    override suspend fun healthCheck(config: ProviderSettings): ProviderHealth = ProviderHealth(
        providerId = providerId,
        state = ProviderHealthState.HEALTHY,
        detail = "Built-in offline responder is always available",
        checkedAtEpochMs = System.currentTimeMillis(),
    )
}
