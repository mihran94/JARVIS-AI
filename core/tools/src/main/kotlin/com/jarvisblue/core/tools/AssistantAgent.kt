package com.jarvisblue.core.tools

import com.jarvisblue.core.ai.AiMessage
import com.jarvisblue.core.ai.AiRequest
import com.jarvisblue.core.ai.AiRouter
import com.jarvisblue.core.ai.LanguageDetector
import com.jarvisblue.core.ai.PromptBuilder
import com.jarvisblue.core.ai.TaskKind
import com.jarvisblue.core.database.MemoryRepository
import com.jarvisblue.core.model.ChatMessage
import com.jarvisblue.core.model.ExecutionVerdict
import com.jarvisblue.core.model.Language
import com.jarvisblue.core.model.MemoryKind
import com.jarvisblue.core.model.MessageRole
import com.jarvisblue.core.model.MessageStatus
import com.jarvisblue.core.model.ProviderId
import com.jarvisblue.core.model.TokenUsage
import com.jarvisblue.core.model.ToolCallRecord
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put
import java.util.UUID

/** Gate the UI implements to ask the user for a fresh confirmation. */
interface ConfirmationGate {
    suspend fun request(request: ConfirmationRequest): Boolean
}

/** Events emitted while the agent works, so the UI can show live progress. */
sealed interface AgentEvent {
    data class Thinking(val detail: String) : AgentEvent
    data class ToolRequested(val toolName: String, val summary: String) : AgentEvent
    data class ToolCompleted(val toolName: String, val summary: String, val success: Boolean) : AgentEvent
    data class ConfirmationNeeded(val request: ConfirmationRequest) : AgentEvent
    data class Notice(val text: String) : AgentEvent
}

/**
 * The reasoning loop.
 *
 * The model never executes anything. It can only *ask* for tools; every request
 * passes through [ToolExecutor], which enforces the schema, the permission
 * grants, the risk policy and the confirmation gate before anything runs. The
 * model is then told what actually happened — including failures — so it can
 * report the truth rather than a guess.
 */
class AssistantAgent(
    private val router: AiRouter,
    private val registry: ToolRegistry,
    private val executor: ToolExecutor,
    private val memoryRepository: MemoryRepository,
    private val confirmationGate: ConfirmationGate,
    private val toolContext: ToolContext,
    private val platformName: String = "Android",
    private val appVersion: String = "1.0.0",
    private val maxToolIterations: Int = 6,
) {

    suspend fun run(
        userText: String,
        history: List<ChatMessage>,
        language: Language? = null,
        preferredProvider: ProviderId? = null,
        preferredModel: String? = null,
        onEvent: (AgentEvent) -> Unit = {},
    ): ChatMessage {
        val detected = language ?: LanguageDetector.detect(userText)
        val memory = memoryRepository.contextWindow(10)
        val systemPrompt = PromptBuilder.system(
            language = detected,
            memory = memory,
            platform = platformName,
            appVersion = appVersion,
            includeTools = registry.all().isNotEmpty(),
        )

        val messages = mutableListOf(
            AiMessage(role = "system", content = systemPrompt),
        )
        history.takeLast(12).forEach { message ->
            messages += AiMessage(
                role = when (message.role) {
                    MessageRole.USER -> "user"
                    MessageRole.ASSISTANT -> "assistant"
                    MessageRole.SYSTEM -> "system"
                    MessageRole.TOOL -> "tool"
                },
                content = message.content,
            )
        }
        messages += AiMessage(role = "user", content = userText)

        val enabledTools = registry.all()
            .filter { it.spec.name in ENABLED_TOOL_NAMES }
            .map { it.spec.name }
            .toSet()

        val toolSchemas = registry.openAiSchemas(enabledTools)
        val toolRecords = mutableListOf<ToolCallRecord>()

        var promptTokens = 0
        var completionTokens = 0
        var providerUsed = preferredProvider ?: ProviderId.OFFLINE_ECHO
        var modelUsed = preferredModel
        var finalContent = ""
        var failure: String? = null

        for (iteration in 0 until maxToolIterations) {
            val request = AiRequest(
                messages = messages.toList(),
                modelId = preferredModel,
                tools = toolSchemas,
                responseLanguage = detected,
                enableTools = toolSchemas.isNotEmpty(),
            )

            val response = try {
                router.route(
                    request = request,
                    taskKind = TaskKind.CHAT,
                    preferredProvider = preferredProvider,
                    preferredModel = preferredModel,
                )
            } catch (t: Throwable) {
                if (t is kotlinx.coroutines.CancellationException) throw t
                failure = t.message ?: "The AI provider could not be reached"
                onEvent(AgentEvent.Notice(failure))
                finalContent = "I could not reach an AI provider: ${t.message}"
                break
            }

            providerUsed = runCatching { ProviderId.valueOf(response.providerId) }
                .getOrDefault(ProviderId.OFFLINE_ECHO)
            modelUsed = response.modelId
            promptTokens += response.usage.promptTokens
            completionTokens += response.usage.completionTokens
            finalContent = response.content

            if (response.toolCalls.isEmpty()) {
                break
            }

            messages += AiMessage(role = "assistant", content = response.content)

            for (call in response.toolCalls) {
                onEvent(AgentEvent.ToolRequested(call.name, call.argumentsJson))
                val arguments = parseArguments(call.argumentsJson)
                val outcome = runToolWithConfirmation(call.name, arguments, onEvent)
                toolRecords += ToolCallRecord(
                    toolName = call.name,
                    argumentsJson = call.argumentsJson,
                    status = outcome.verdict.name,
                    riskLevel = outcome.riskLevel.name,
                    resultSummary = outcome.message.take(400),
                    requiredConfirmation = outcome.approvalRequired,
                    confirmed = outcome.verdict == ExecutionVerdict.COMPLETED,
                    error = if (outcome.verdict == ExecutionVerdict.COMPLETED) null else outcome.message,
                )
                messages += AiMessage(
                    role = "tool",
                    content = buildString {
                        append("Tool `").append(call.name).append("` finished with verdict ")
                        append(outcome.verdict.name).append(".\n")
                        append("Result: ").append(outcome.message)
                    },
                    name = call.name,
                )
            }
        }

        if (finalContent.isBlank() && failure == null) {
            finalContent = "I completed the requested steps but did not have a final summary to give."
        }

        return ChatMessage(
            id = UUID.randomUUID().toString(),
            role = MessageRole.ASSISTANT,
            content = finalContent,
            createdAtEpochMs = System.currentTimeMillis(),
            status = if (failure != null) MessageStatus.FAILED else MessageStatus.COMPLETE,
            language = detected,
            providerId = providerUsed.name,
            modelId = modelUsed,
            toolCalls = toolRecords,
            failureReason = failure,
            tokenUsage = TokenUsage(promptTokens, completionTokens),
        )
    }

    /**
     * Runs a tool, pausing for a fresh user confirmation when the risk policy
     * requires one. A refusal is reported back to the model as a real result,
     * so it can explain what happened rather than pretending it worked.
     */
    suspend fun runToolWithConfirmation(
        toolName: String,
        arguments: JsonObject,
        onEvent: (AgentEvent) -> Unit = {},
    ): com.jarvisblue.core.model.ExecutionOutcome {
        val context = toolContext
        val spec = registry.find(toolName)?.spec
            ?: return com.jarvisblue.core.model.ExecutionOutcome(
                verdict = ExecutionVerdict.INVALID_ARGUMENTS,
                message = "Unknown tool '$toolName'",
            )

        val first = executor.execute(toolName, arguments, context, alreadyConfirmed = false)
        if (first.verdict != ExecutionVerdict.NEEDS_CONFIRMATION) {
            onEvent(
                AgentEvent.ToolCompleted(
                    toolName,
                    first.message,
                    first.verdict == ExecutionVerdict.COMPLETED,
                ),
            )
            return first
        }

        val request = ConfirmationRequest(
            toolName = toolName,
            title = spec.displayName,
            detail = spec.description,
            riskLevel = first.riskLevel.name,
            effects = buildList {
                add("Runs ${spec.displayName} on this device")
                add("Uses the ${spec.requiredPermissions.joinToString(", ") { it.label }} permission")
                if (spec.destructive) add("May remove or overwrite data")
            },
        )
        onEvent(AgentEvent.ConfirmationNeeded(request))

        val approved = confirmationGate.request(request)
        if (!approved) {
            onEvent(AgentEvent.ToolCompleted(toolName, "Declined by the user", false))
            return com.jarvisblue.core.model.ExecutionOutcome(
                verdict = ExecutionVerdict.NEEDS_CONFIRMATION,
                message = "The user declined to run ${spec.displayName}.",
                riskLevel = first.riskLevel,
            )
        }

        val second = executor.execute(toolName, arguments, context, alreadyConfirmed = true)
        onEvent(
            AgentEvent.ToolCompleted(
                toolName,
                second.message,
                second.verdict == ExecutionVerdict.COMPLETED,
            ),
        )
        return second
    }

    /** Stores a note in the personal memory store. */
    suspend fun remember(title: String, body: String, kind: MemoryKind = MemoryKind.FACT): String {
        memoryRepository.remember(kind = kind, title = title, body = body, source = "conversation")
        return "Remembered '$title'"
    }

    private fun parseArguments(raw: String): JsonObject = runCatching {
        kotlinx.serialization.json.Json.parseToJsonElement(raw.ifBlank { "{}" }) as JsonObject
    }.getOrDefault(buildJsonObject { })

    companion object {
        /**
         * Tools that the model may request. Anything outside this set is still
         * registered (so the user can call it explicitly from the studio) but is
         * not offered to the model during free-form conversation.
         */
        val ENABLED_TOOL_NAMES: Set<String> = setOf(
            "device_diagnostics",
            "open_app",
            "list_apps",
            "open_settings",
            "set_alarm",
            "call_contact",
            "compose_message",
            "media_control",
            "share_text",
            "summarize_notifications",
            "read_screen",
            "organize_files",
            "list_files",
            "network_probe",
            "security_review",
            "code_quality_check",
            "quantum_simulate",
            "remote_status",
            "remote_jobs",
            "remote_submit_job",
            "remote_cancel_job",
            "remember",
            "recall",
        )
    }
}
