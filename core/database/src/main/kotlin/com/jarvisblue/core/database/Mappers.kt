package com.jarvisblue.core.database

import com.jarvisblue.core.model.AuditCategory
import com.jarvisblue.core.model.AuditEvent
import com.jarvisblue.core.model.AuditSeverity
import com.jarvisblue.core.model.ChatAttachment
import com.jarvisblue.core.model.ChatMessage
import com.jarvisblue.core.model.Conversation
import com.jarvisblue.core.model.Language
import com.jarvisblue.core.model.MemoryItem
import com.jarvisblue.core.model.MemoryKind
import com.jarvisblue.core.model.MessageRole
import com.jarvisblue.core.model.MessageStatus
import com.jarvisblue.core.model.RiskLevel
import com.jarvisblue.core.model.TokenUsage
import com.jarvisblue.core.model.ToolCallRecord
import kotlinx.serialization.encodeToString
import kotlinx.serialization.json.Json

val mapperJson: Json = Json { ignoreUnknownKeys = true; encodeDefaults = true }

fun MessageEntity.toDomain(): ChatMessage = ChatMessage(
    id = id,
    role = runCatching { MessageRole.valueOf(role) }.getOrDefault(MessageRole.ASSISTANT),
    content = content,
    createdAtEpochMs = createdAtEpochMs,
    status = runCatching { MessageStatus.valueOf(status) }.getOrDefault(MessageStatus.COMPLETE),
    language = Language.fromTag(language),
    providerId = providerId,
    modelId = modelId,
    toolCalls = toolCallsJson?.let { raw ->
        runCatching { mapperJson.decodeFromString<List<ToolCallRecord>>(raw) }.getOrDefault(emptyList())
    } ?: emptyList(),
    attachments = attachmentsJson?.let { raw ->
        runCatching { mapperJson.decodeFromString<List<ChatAttachment>>(raw) }.getOrDefault(emptyList())
    } ?: emptyList(),
    failureReason = failureReason,
    tokenUsage = TokenUsage(promptTokens, completionTokens, estimatedCostUsd),
)

fun ChatMessage.toEntity(conversationId: String): MessageEntity = MessageEntity(
    id = id,
    conversationId = conversationId,
    role = role.name,
    content = content,
    createdAtEpochMs = createdAtEpochMs,
    status = status.name,
    language = language?.tag,
    providerId = providerId,
    modelId = modelId,
    toolCallsJson = runCatching {
        mapperJson.encodeToString<List<ToolCallRecord>>(toolCalls)
    }.getOrNull(),
    attachmentsJson = runCatching {
        mapperJson.encodeToString<List<ChatAttachment>>(attachments)
    }.getOrNull(),
    failureReason = failureReason,
    promptTokens = tokenUsage?.promptTokens ?: 0,
    completionTokens = tokenUsage?.completionTokens ?: 0,
    estimatedCostUsd = tokenUsage?.estimatedCostUsd ?: 0.0,
)

fun ConversationEntity.toDomain(): Conversation = Conversation(
    id = id,
    title = title,
    createdAtEpochMs = createdAtEpochMs,
    updatedAtEpochMs = updatedAtEpochMs,
    providerId = providerId,
    modelId = modelId,
    messageCount = messageCount,
    archived = archived,
)

fun Conversation.toEntity(): ConversationEntity = ConversationEntity(
    id = id,
    title = title,
    createdAtEpochMs = createdAtEpochMs,
    updatedAtEpochMs = updatedAtEpochMs,
    providerId = providerId,
    modelId = modelId,
    messageCount = messageCount,
    archived = archived,
)

fun MemoryEntity.toDomain(): MemoryItem = MemoryItem(
    id = id,
    kind = runCatching { MemoryKind.valueOf(kind) }.getOrDefault(MemoryKind.FACT),
    title = title,
    body = body,
    tags = tags.split(',').map { it.trim() }.filter { it.isNotEmpty() },
    source = source,
    createdAtEpochMs = createdAtEpochMs,
    lastAccessedEpochMs = lastAccessedEpochMs,
    accessCount = accessCount,
    pinned = pinned,
)

fun MemoryItem.toEntity(): MemoryEntity = MemoryEntity(
    id = id,
    kind = kind.name,
    title = title,
    body = body,
    tags = tags.joinToString(","),
    source = source,
    createdAtEpochMs = createdAtEpochMs,
    lastAccessedEpochMs = lastAccessedEpochMs,
    accessCount = accessCount,
    pinned = pinned,
)

fun AuditEntity.toDomain(): AuditEvent = AuditEvent(
    id = id,
    timestampEpochMs = timestampEpochMs,
    category = runCatching { AuditCategory.valueOf(category) }.getOrDefault(AuditCategory.SYSTEM),
    severity = runCatching { AuditSeverity.valueOf(severity) }.getOrDefault(AuditSeverity.INFO),
    title = title,
    detail = detail,
    toolName = toolName,
    riskLevel = runCatching { RiskLevel.valueOf(riskLevel) }.getOrDefault(RiskLevel.NONE),
    success = success,
    actor = actor,
)

fun AuditEvent.toEntity(): AuditEntity = AuditEntity(
    id = id,
    timestampEpochMs = timestampEpochMs,
    category = category.name,
    severity = severity.name,
    title = title,
    detail = detail,
    toolName = toolName,
    riskLevel = riskLevel.name,
    success = success,
    actor = actor,
)
