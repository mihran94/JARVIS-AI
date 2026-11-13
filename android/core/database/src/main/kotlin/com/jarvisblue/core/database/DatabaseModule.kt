package com.jarvisblue.core.database

import android.content.Context
import com.jarvisblue.core.common.AuditSink
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object DatabaseModule {

    @Provides
    @Singleton
    fun provideDatabase(@ApplicationContext context: Context): JarvisDatabase =
        JarvisDatabase.get(context)

    @Provides
    fun provideConversationDao(database: JarvisDatabase): ConversationDao = database.conversationDao()

    @Provides
    fun provideMessageDao(database: JarvisDatabase): MessageDao = database.messageDao()

    @Provides
    fun provideMemoryDao(database: JarvisDatabase): MemoryDao = database.memoryDao()

    @Provides
    fun provideTaskDao(database: JarvisDatabase): TaskDao = database.taskDao()

    @Provides
    fun provideAuditDao(database: JarvisDatabase): AuditDao = database.auditDao()

    @Provides
    fun provideProviderConfigDao(database: JarvisDatabase): ProviderConfigDao =
        database.providerConfigDao()

    @Provides
    fun providePeerDao(database: JarvisDatabase): PeerDao = database.peerDao()

    @Provides
    @Singleton
    fun provideAuditSink(database: JarvisDatabase): AuditSink =
        DbAuditSink(database.auditDao())

    @Provides
    @Singleton
    fun provideConversationRepository(
        conversationDao: ConversationDao,
        messageDao: MessageDao,
    ): ConversationRepository = ConversationRepository(conversationDao, messageDao)

    @Provides
    @Singleton
    fun provideMemoryRepository(memoryDao: MemoryDao): MemoryRepository = MemoryRepository(memoryDao)

    @Provides
    @Singleton
    fun provideTaskRepository(taskDao: TaskDao): TaskRepository = TaskRepository(taskDao)

    @Provides
    @Singleton
    fun provideProviderConfigRepository(dao: ProviderConfigDao): ProviderConfigRepository =
        ProviderConfigRepository(dao)

    @Provides
    @Singleton
    fun providePeerRepository(dao: PeerDao): PeerRepository = PeerRepository(dao)
}
