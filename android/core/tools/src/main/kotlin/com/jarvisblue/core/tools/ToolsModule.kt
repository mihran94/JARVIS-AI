package com.jarvisblue.core.tools

import android.content.Context
import com.jarvisblue.core.database.MemoryRepository
import com.jarvisblue.core.security.EmergencyStop
import com.jarvisblue.core.security.PermissionGrantStore
import dagger.Module
import dagger.Provides
import dagger.hilt.InstallIn
import dagger.hilt.android.qualifiers.ApplicationContext
import dagger.hilt.components.SingletonComponent
import java.io.File
import javax.inject.Singleton

@Module
@InstallIn(SingletonComponent::class)
object ToolsModule {

    @Provides
    @Singleton
    fun provideToolRegistry(): ToolRegistry = ToolRegistry()

    @Provides
    @Singleton
    fun provideDeviceControlEngine(@ApplicationContext context: Context): DeviceControlEngine =
        DeviceControlEngine(context)

    @Provides
    @Singleton
    fun provideFileTools(@ApplicationContext context: Context): FileTools = FileTools(context)

    @Provides
    @Singleton
    fun provideNetworkDiagnostics(): NetworkDiagnostics = NetworkDiagnostics()

    @Provides
    @Singleton
    fun provideSecurityScanner(): SecurityScanner = SecurityScanner()

    @Provides
    @Singleton
    fun provideCodeQualityChecker(): CodeQualityChecker = CodeQualityChecker()

    @Provides
    @Singleton
    fun provideQuantumSimulator(): QuantumSimulator = QuantumSimulator()

    @Provides
    @Singleton
    fun provideWorkspaceRoot(@ApplicationContext context: Context): File =
        File(context.filesDir, "workspace").apply { if (!exists()) mkdirs() }

    @Provides
    @Singleton
    fun provideToolExecutor(
        registry: ToolRegistry,
        grantStore: PermissionGrantStore,
        emergencyStop: EmergencyStop,
    ): ToolExecutor = ToolExecutor(registry, grantStore, emergencyStop)

    @Provides
    @Singleton
    fun provideMemoryTools(repository: MemoryRepository): MemoryTools = MemoryTools(repository)

    @Provides
    @Singleton
    fun provideConfirmationCoordinator(): ConfirmationCoordinator = ConfirmationCoordinator()

    @Provides
    @Singleton
    fun provideIntentRouter(): IntentRouter = IntentRouter()

    @Provides
    @Singleton
    fun provideToolContext(
        provider: ToolContextProvider,
        workspaceRoot: File,
    ): ToolContext = provider.create(workspaceRoot)
}
