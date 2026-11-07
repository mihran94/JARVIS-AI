package com.jarvisblue.core.model

import kotlinx.serialization.Serializable

enum class MessageRole { SYSTEM, USER, ASSISTANT, TOOL }

@Serializable
enum class MessageStatus { PENDING, STREAMING, COMPLETE, FAILED, CANCELLED }

@Serializable
data class ChatAttachment(
    val id: String,
    val mimeType: String,
    val displayName: String,
    val sizeBytes: Long = 0L,
    /** Only populated for text-like attachments; binary payloads are referenced by uri. */
    val extractedText: String? = null,
    val uri: String? = null,
)

@Serializable
data class ChatMessage(
    val id: String,
    val role: MessageRole,
    val content: String,
    val createdAtEpochMs: Long,
    val status: MessageStatus = MessageStatus.COMPLETE,
    val language: Language? = null,
    val providerId: String? = null,
    val modelId: String? = null,
    val toolCalls: List<ToolCallRecord> = emptyList(),
    val attachments: List<ChatAttachment> = emptyList(),
    val failureReason: String? = null,
    val tokenUsage: TokenUsage? = null,
) {
    val isUser: Boolean get() = role == MessageRole.USER
}

@Serializable
data class ToolCallRecord(
    val toolName: String,
    val argumentsJson: String,
    val status: String,
    val riskLevel: String,
    val resultSummary: String? = null,
    val requiredConfirmation: Boolean = false,
    val confirmed: Boolean = false,
    val error: String? = null,
)

@Serializable
data class TokenUsage(
    val promptTokens: Int = 0,
    val completionTokens: Int = 0,
    val estimatedCostUsd: Double = 0.0,
)

@Serializable
data class Conversation(
    val id: String,
    val title: String,
    val createdAtEpochMs: Long,
    val updatedAtEpochMs: Long,
    val providerId: String? = null,
    val modelId: String? = null,
    val messageCount: Int = 0,
    val archived: Boolean = false,
)
