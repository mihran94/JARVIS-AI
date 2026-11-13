package com.jarvisblue.core.database

import com.jarvisblue.core.common.AuditSink
import com.jarvisblue.core.common.Clock
import com.jarvisblue.core.model.AuditEvent
import com.jarvisblue.core.model.ChatMessage
import com.jarvisblue.core.model.Conversation
import com.jarvisblue.core.model.MemoryItem
import com.jarvisblue.core.model.MemoryKind
import com.jarvisblue.core.model.ProviderConfig
import com.jarvisblue.core.model.PlannedAction
import com.jarvisblue.core.model.ProviderId
import com.jarvisblue.core.model.WindowsPeer
import kotlinx.coroutines.flow.Flow
import kotlinx.coroutines.flow.map
import kotlinx.serialization.encodeToString
import java.util.UUID

class ConversationRepository(
    private val conversationDao: ConversationDao,
    private val messageDao: MessageDao,
    private val clock: Clock = Clock.System,
) {
    fun observeConversations(): Flow<List<Conversation>> =
        conversationDao.observeAll().map { list -> list.map { it.toDomain() } }

    fun observeMessages(conversationId: String): Flow<List<ChatMessage>> =
        messageDao.observeForConversation(conversationId).map { list -> list.map { it.toDomain() } }

    suspend fun recentMessages(conversationId: String, limit: Int = 20): List<ChatMessage> =
        messageDao.recentForConversation(conversationId, limit).map { it.toDomain() }

    suspend fun ensureConversation(id: String, title: String): Conversation {
        conversationDao.byId(id)?.let { return it.toDomain() }
        val now = clock.nowEpochMs()
        val conversation = Conversation(
            id = id,
            title = title,
            createdAtEpochMs = now,
            updatedAtEpochMs = now,
        )
        conversationDao.upsert(conversation.toEntity())
        return conversation
    }

    suspend fun appendMessage(conversationId: String, message: ChatMessage) {
        messageDao.upsert(message.toEntity(conversationId))
        val count = messageDao.recentForConversation(conversationId, 1000).size
        conversationDao.touch(conversationId, message.createdAtEpochMs, count)
    }

    suspend fun deleteConversation(id: String) {
        messageDao.clearConversation(id)
        conversationDao.delete(id)
    }
}

class MemoryRepository(
    private val memoryDao: MemoryDao,
    private val clock: Clock = Clock.System,
) {
    fun observeAll(): Flow<List<MemoryItem>> =
        memoryDao.observeAll().map { list -> list.map { it.toDomain() } }

    suspend fun save(item: MemoryItem) = memoryDao.upsert(item.toEntity())

    suspend fun remember(
        kind: MemoryKind,
        title: String,
        body: String,
        tags: List<String> = emptyList(),
        source: String = "user",
    ): MemoryItem {
        val now = clock.nowEpochMs()
        val item = MemoryItem(
            id = UUID.randomUUID().toString(),
            kind = kind,
            title = title,
            body = body,
            tags = tags,
            source = source,
            createdAtEpochMs = now,
            lastAccessedEpochMs = now,
        )
        memoryDao.upsert(item.toEntity())
        return item
    }

    suspend fun byKind(kind: MemoryKind): List<MemoryItem> =
        memoryDao.byKind(kind.name).map { it.toDomain() }

    suspend fun search(query: String, limit: Int = 10): List<MemoryItem> {
        val tag = query.trim()
        if (tag.isEmpty()) return emptyList()
        return memoryDao.byTag(tag, limit).map { it.toDomain() }
    }

    suspend fun contextWindow(limit: Int = 12): List<MemoryItem> =
        memoryDao.mostRecent(limit).map { it.toDomain() }

    suspend fun touch(id: String) = memoryDao.touch(id, clock.nowEpochMs())

    suspend fun delete(id: String) = memoryDao.delete(id)

    suspend fun clearAll() = memoryDao.clear()
}

class TaskRepository(
    private val taskDao: TaskDao,
    private val clock: Clock = Clock.System,
) {
    fun observeAll(): Flow<List<com.jarvisblue.core.model.AutomationTask>> =
        taskDao.observeAll().map { list ->
            list.map {
                com.jarvisblue.core.model.AutomationTask(
                    id = it.id,
                    title = it.title,
                    goal = it.goal,
                    trigger = runCatching {
                        com.jarvisblue.core.model.TaskTrigger.valueOf(it.trigger)
                    }.getOrDefault(com.jarvisblue.core.model.TaskTrigger.MANUAL),
                    scheduleCron = it.scheduleCron,
                    triggerEvent = it.triggerEvent,
                    steps = it.stepsJson.let { raw ->
                        runCatching {
                            mapperJson.decodeFromString<List<PlannedAction>>(raw)
                        }.getOrDefault(emptyList())
                    },
                    dependencies = it.dependenciesJson.split(',').map(String::trim).filter(String::isNotEmpty),
                    status = runCatching {
                        com.jarvisblue.core.model.TaskStatus.valueOf(it.status)
                    }.getOrDefault(com.jarvisblue.core.model.TaskStatus.QUEUED),
                    maxRetries = it.maxRetries,
                    retryCount = it.retryCount,
                    requiresConfirmation = it.requiresConfirmation,
                    enabled = it.enabled,
                    createdAtEpochMs = it.createdAtEpochMs,
                    updatedAtEpochMs = it.updatedAtEpochMs,
                    lastError = it.lastError,
                    nextRunEpochMs = it.nextRunEpochMs,
                )
            }
        }

    suspend fun upsert(task: com.jarvisblue.core.model.AutomationTask) = taskDao.upsert(
        TaskEntity(
            id = task.id,
            title = task.title,
            goal = task.goal,
            trigger = task.trigger.name,
            scheduleCron = task.scheduleCron,
            triggerEvent = task.triggerEvent,
            stepsJson = runCatching { mapperJson.encodeToString<List<PlannedAction>>(task.steps) }.getOrDefault("[]"),
            dependenciesJson = task.dependencies.joinToString(","),
            status = task.status.name,
            maxRetries = task.maxRetries,
            retryCount = task.retryCount,
            requiresConfirmation = task.requiresConfirmation,
            enabled = task.enabled,
            createdAtEpochMs = task.createdAtEpochMs,
            updatedAtEpochMs = task.updatedAtEpochMs,
            lastError = task.lastError,
            nextRunEpochMs = task.nextRunEpochMs,
        ),
    )

    suspend fun delete(id: String) = taskDao.delete(id)
}

class ProviderConfigRepository(private val dao: ProviderConfigDao) {
    fun observeAll(): Flow<List<ProviderConfig>> =
        dao.observeAll().map { list ->
            list.map {
                ProviderConfig(
                    providerId = runCatching { ProviderId.valueOf(it.providerId) }
                        .getOrDefault(ProviderId.OFFLINE_ECHO),
                    enabled = it.enabled,
                    baseUrl = it.baseUrl,
                    defaultModelId = it.defaultModelId,
                    priority = it.priority,
                    temperature = it.temperature,
                    maxOutputTokens = it.maxOutputTokens,
                    dailyTokenBudget = it.dailyTokenBudget,
                    allowOfflineFallback = it.allowOfflineFallback,
                )
            }
        }

    suspend fun save(config: ProviderConfig) = dao.upsert(
        ProviderConfigEntity(
            providerId = config.providerId.name,
            enabled = config.enabled,
            baseUrl = config.baseUrl,
            defaultModelId = config.defaultModelId,
            priority = config.priority,
            temperature = config.temperature,
            maxOutputTokens = config.maxOutputTokens,
            dailyTokenBudget = config.dailyTokenBudget,
            allowOfflineFallback = config.allowOfflineFallback,
        ),
    )
}

class PeerRepository(private val dao: PeerDao) {
    fun observeAll(): Flow<List<WindowsPeer>> =
        dao.observeAll().map { list ->
            list.map {
                WindowsPeer(
                    peerId = it.peerId,
                    displayName = it.displayName,
                    host = it.host,
                    port = it.port,
                    pairedAtEpochMs = it.pairedAtEpochMs,
                    lastSeenEpochMs = it.lastSeenEpochMs,
                    sharedSecretAlias = it.sharedSecretAlias,
                    trusted = it.trusted,
                )
            }
        }

    suspend fun save(peer: WindowsPeer) = dao.upsert(
        PeerEntity(
            peerId = peer.peerId,
            displayName = peer.displayName,
            host = peer.host,
            port = peer.port,
            pairedAtEpochMs = peer.pairedAtEpochMs,
            lastSeenEpochMs = peer.lastSeenEpochMs,
            sharedSecretAlias = peer.sharedSecretAlias,
            trusted = peer.trusted,
        ),
    )

    suspend fun trusted(): WindowsPeer? = dao.trusted()?.let {
        WindowsPeer(
            peerId = it.peerId,
            displayName = it.displayName,
            host = it.host,
            port = it.port,
            pairedAtEpochMs = it.pairedAtEpochMs,
            lastSeenEpochMs = it.lastSeenEpochMs,
            sharedSecretAlias = it.sharedSecretAlias,
            trusted = it.trusted,
        )
    }

    suspend fun delete(id: String) = dao.delete(id)
}

/** Audit sink that persists to the encrypted database. */
class DbAuditSink(
    private val auditDao: AuditDao,
    private val clock: Clock = Clock.System,
) : AuditSink {
    override suspend fun record(
        category: String,
        title: String,
        detail: String,
        severity: String,
        toolName: String?,
        riskLevel: String,
        success: Boolean,
        actor: String,
    ) {
        val event = AuditEvent(
            id = UUID.randomUUID().toString(),
            timestampEpochMs = clock.nowEpochMs(),
            category = runCatching {
                com.jarvisblue.core.model.AuditCategory.valueOf(category)
            }.getOrDefault(com.jarvisblue.core.model.AuditCategory.SYSTEM),
            severity = runCatching {
                com.jarvisblue.core.model.AuditSeverity.valueOf(severity)
            }.getOrDefault(com.jarvisblue.core.model.AuditSeverity.INFO),
            title = title,
            detail = detail,
            toolName = toolName,
            riskLevel = runCatching {
                com.jarvisblue.core.model.RiskLevel.valueOf(riskLevel)
            }.getOrDefault(com.jarvisblue.core.model.RiskLevel.NONE),
            success = success,
            actor = actor,
        )
        auditDao.insert(event.toEntity())
    }
}
