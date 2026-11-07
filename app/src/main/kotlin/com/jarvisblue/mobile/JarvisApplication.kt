package com.jarvisblue.mobile

import android.app.Application
import android.app.NotificationChannel
import android.app.NotificationManager
import android.os.Build
import androidx.hilt.work.HiltWorkerFactory
import androidx.work.Configuration
import androidx.work.WorkManager
import com.jarvisblue.core.tools.CodeQualityChecker
import com.jarvisblue.core.tools.DeviceControlEngine
import com.jarvisblue.core.tools.FileTools
import com.jarvisblue.core.tools.JarvisToolRegistrar
import com.jarvisblue.core.tools.MemoryTools
import com.jarvisblue.core.tools.NetworkDiagnostics
import com.jarvisblue.core.tools.QuantumSimulator
import com.jarvisblue.core.tools.SecurityScanner
import com.jarvisblue.core.tools.ToolRegistry
import dagger.hilt.android.HiltAndroidApp
import javax.inject.Inject

@HiltAndroidApp
class JarvisApplication : Application(), Configuration.Provider {

    @Inject lateinit var workerFactory: HiltWorkerFactory

    @Inject lateinit var toolRegistry: ToolRegistry

    @Inject lateinit var deviceControlEngine: DeviceControlEngine

    @Inject lateinit var fileTools: FileTools

    @Inject lateinit var networkDiagnostics: NetworkDiagnostics

    @Inject lateinit var securityScanner: SecurityScanner

    @Inject lateinit var codeQualityChecker: CodeQualityChecker

    @Inject lateinit var quantumSimulator: QuantumSimulator

    @Inject lateinit var memoryTools: MemoryTools

    @Inject lateinit var assistantServices: AssistantServicesImpl

    @Inject lateinit var workspaceRoot: java.io.File

    override val workManagerConfiguration: Configuration
        get() = Configuration.Builder()
            .setWorkerFactory(workerFactory)
            .setMinimumLoggingLevel(android.util.Log.INFO)
            .build()

    override fun onCreate() {
        super.onCreate()
        WorkManager.initialize(this, workManagerConfiguration)
        registerTools()
        createNotificationChannels()
    }

    /**
     * Registers the capability surface exactly once at startup.
     *
     * Everything the assistant can do is declared here — there is no dynamic
     * tool creation at runtime, so the permission matrix always matches reality.
     */
    private fun registerTools() {
        if (toolRegistry.all().isNotEmpty()) return
        JarvisToolRegistrar(
            registry = toolRegistry,
            device = deviceControlEngine,
            files = fileTools,
            network = networkDiagnostics,
            scanner = securityScanner,
            quality = codeQualityChecker,
            quantum = quantumSimulator,
            services = assistantServices,
            workspaceRoot = workspaceRoot,
        ).registerAll()
        memoryTools.register(toolRegistry)
    }

    private fun createNotificationChannels() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.O) return
        val manager = getSystemService(NotificationManager::class.java) ?: return

        val wake = NotificationChannel(
            WAKE_CHANNEL_ID,
            getString(R.string.wake_channel_name),
            NotificationManager.IMPORTANCE_LOW,
        ).apply {
            description = getString(R.string.wake_channel_description)
            setShowBadge(false)
        }

        val reminders = NotificationChannel(
            REMINDER_CHANNEL_ID,
            getString(R.string.reminder_channel_name),
            NotificationManager.IMPORTANCE_DEFAULT,
        ).apply {
            description = getString(R.string.reminder_channel_description)
        }

        manager.createNotificationChannels(listOf(wake, reminders))
    }

    companion object {
        const val WAKE_CHANNEL_ID = "jarvis_wake_word"
        const val REMINDER_CHANNEL_ID = "jarvis_reminders"
    }
}
