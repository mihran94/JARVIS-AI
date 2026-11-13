package com.jarvisblue.core.database

import androidx.room.Entity
import androidx.room.Index
import androidx.room.PrimaryKey

@Entity(tableName = "conversations")
data class ConversationEntity(
    @PrimaryKey val id: String,
    val title: String,
    val createdAtEpochMs: Long,
    val updatedAtEpochMs: Long,
    val providerId: String?,
    val modelId: String?,
    val messageCount: Int = 0,
    val archived: Boolean = false,
)

@Entity(
    tableName = "messages",
    indices = [Index("conversationId"), Index("createdAtEpochMs")],
)
data class MessageEntity(
    @PrimaryKey val id: String,
    val conversationId: String,
    val role: String,
    val content: String,
    val createdAtEpochMs: Long,
    val status: String,
    val language: String?,
    val providerId: String?,
    val modelId: String?,
    val toolCallsJson: String?,
    val attachmentsJson: String?,
    val failureReason: String?,
    val promptTokens: Int = 0,
    val completionTokens: Int = 0,
    val estimatedCostUsd: Double = 0.0,
)

@Entity(
    tableName = "memory_items",
    indices = [Index("kind"), Index("createdAtEpochMs")],
)
data class MemoryEntity(
    @PrimaryKey val id: String,
    val kind: String,
    val title: String,
    val body: String,
    val tags: String,
    val source: String,
    val createdAtEpochMs: Long,
    val lastAccessedEpochMs: Long,
    val accessCount: Int,
    val pinned: Boolean,
)

@Entity(tableName = "automation_tasks", indices = [Index("status")])
data class TaskEntity(
    @PrimaryKey val id: String,
    val title: String,
    val goal: String,
    val trigger: String,
    val scheduleCron: String?,
    val triggerEvent: String?,
    val stepsJson: String,
    val dependenciesJson: String,
    val status: String,
    val maxRetries: Int,
    val retryCount: Int,
    val requiresConfirmation: Boolean,
    val enabled: Boolean,
    val createdAtEpochMs: Long,
    val updatedAtEpochMs: Long,
    val lastError: String?,
    val nextRunEpochMs: Long?,
)

@Entity(tableName = "audit_events", indices = [Index("timestampEpochMs"), Index("category")])
data class AuditEntity(
    @PrimaryKey val id: String,
    val timestampEpochMs: Long,
    val category: String,
    val severity: String,
    val title: String,
    val detail: String,
    val toolName: String?,
    val riskLevel: String,
    val success: Boolean,
    val actor: String,
)

@Entity(tableName = "provider_configs")
data class ProviderConfigEntity(
    @PrimaryKey val providerId: String,
    val enabled: Boolean,
    val baseUrl: String?,
    val defaultModelId: String?,
    val priority: Int,
    val temperature: Double,
    val maxOutputTokens: Int,
    val dailyTokenBudget: Int,
    val allowOfflineFallback: Boolean,
)

@Entity(tableName = "windows_peers")
data class PeerEntity(
    @PrimaryKey val peerId: String,
    val displayName: String,
    val host: String,
    val port: Int,
    val pairedAtEpochMs: Long,
    val lastSeenEpochMs: Long,
    val sharedSecretAlias: String,
    val trusted: Boolean,
)

@Entity(tableName = "settings")
data class SettingEntity(
    @PrimaryKey val key: String,
    val value: String,
)
