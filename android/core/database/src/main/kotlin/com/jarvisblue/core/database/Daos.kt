package com.jarvisblue.core.database

import androidx.room.Dao
import androidx.room.Insert
import androidx.room.OnConflictStrategy
import androidx.room.Query
import androidx.room.Transaction
import kotlinx.coroutines.flow.Flow

@Dao
interface ConversationDao {
    @Query("SELECT * FROM conversations ORDER BY updatedAtEpochMs DESC")
    fun observeAll(): Flow<List<ConversationEntity>>

    @Query("SELECT * FROM conversations WHERE id = :id")
    suspend fun byId(id: String): ConversationEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(conversation: ConversationEntity)

    @Query("UPDATE conversations SET updatedAtEpochMs = :ts, messageCount = :count WHERE id = :id")
    suspend fun touch(id: String, ts: Long, count: Int)

    @Query("DELETE FROM conversations WHERE id = :id")
    suspend fun delete(id: String)
}

@Dao
interface MessageDao {
    @Query("SELECT * FROM messages WHERE conversationId = :conversationId ORDER BY createdAtEpochMs ASC")
    fun observeForConversation(conversationId: String): Flow<List<MessageEntity>>

    @Query("SELECT * FROM messages WHERE conversationId = :conversationId ORDER BY createdAtEpochMs ASC LIMIT :limit")
    suspend fun recentForConversation(conversationId: String, limit: Int): List<MessageEntity>

    @Query("SELECT * FROM messages ORDER BY createdAtEpochMs DESC LIMIT :limit")
    suspend fun recent(limit: Int): List<MessageEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(message: MessageEntity)

    @Query("DELETE FROM messages WHERE conversationId = :conversationId")
    suspend fun deleteForConversation(conversationId: String)

    @Transaction
    suspend fun clearConversation(conversationId: String) = deleteForConversation(conversationId)
}

@Dao
interface MemoryDao {
    @Query("SELECT * FROM memory_items ORDER BY pinned DESC, lastAccessedEpochMs DESC")
    fun observeAll(): Flow<List<MemoryEntity>>

    @Query("SELECT * FROM memory_items WHERE kind = :kind ORDER BY lastAccessedEpochMs DESC")
    suspend fun byKind(kind: String): List<MemoryEntity>

    @Query("SELECT * FROM memory_items WHERE tags LIKE '%' || :tag || '%' ORDER BY lastAccessedEpochMs DESC LIMIT :limit")
    suspend fun byTag(tag: String, limit: Int): List<MemoryEntity>

    @Query("SELECT * FROM memory_items ORDER BY lastAccessedEpochMs DESC LIMIT :limit")
    suspend fun mostRecent(limit: Int): List<MemoryEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(item: MemoryEntity)

    @Query("DELETE FROM memory_items WHERE id = :id")
    suspend fun delete(id: String)

    @Query("DELETE FROM memory_items")
    suspend fun clear()

    @Query("UPDATE memory_items SET accessCount = accessCount + 1, lastAccessedEpochMs = :ts WHERE id = :id")
    suspend fun touch(id: String, ts: Long)
}

@Dao
interface TaskDao {
    @Query("SELECT * FROM automation_tasks ORDER BY createdAtEpochMs DESC")
    fun observeAll(): Flow<List<TaskEntity>>

    @Query("SELECT * FROM automation_tasks WHERE id = :id")
    suspend fun byId(id: String): TaskEntity?

    @Query("SELECT * FROM automation_tasks WHERE status IN ('QUEUED','RUNNING')")
    suspend fun pending(): List<TaskEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(task: TaskEntity)

    @Query("DELETE FROM automation_tasks WHERE id = :id")
    suspend fun delete(id: String)
}

@Dao
interface AuditDao {
    @Query("SELECT * FROM audit_events ORDER BY timestampEpochMs DESC LIMIT :limit")
    fun observeRecent(limit: Int = 500): Flow<List<AuditEntity>>

    @Query("SELECT * FROM audit_events ORDER BY timestampEpochMs DESC LIMIT :limit")
    suspend fun recent(limit: Int): List<AuditEntity>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun insert(event: AuditEntity)

    @Query("DELETE FROM audit_events")
    suspend fun clear()

    @Query("SELECT COUNT(*) FROM audit_events")
    suspend fun count(): Int
}

@Dao
interface ProviderConfigDao {
    @Query("SELECT * FROM provider_configs")
    fun observeAll(): Flow<List<ProviderConfigEntity>>

    @Query("SELECT * FROM provider_configs WHERE providerId = :id")
    suspend fun byId(id: String): ProviderConfigEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(config: ProviderConfigEntity)
}

@Dao
interface PeerDao {
    @Query("SELECT * FROM windows_peers")
    fun observeAll(): Flow<List<PeerEntity>>

    @Query("SELECT * FROM windows_peers WHERE trusted = 1 LIMIT 1")
    suspend fun trusted(): PeerEntity?

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun upsert(peer: PeerEntity)

    @Query("DELETE FROM windows_peers WHERE peerId = :id")
    suspend fun delete(id: String)
}

@Dao
interface SettingDao {
    @Query("SELECT value FROM settings WHERE `key` = :key")
    suspend fun get(key: String): String?

    @Query("SELECT value FROM settings WHERE `key` = :key")
    fun observe(key: String): Flow<String?>

    @Insert(onConflict = OnConflictStrategy.REPLACE)
    suspend fun put(setting: SettingEntity)
}
