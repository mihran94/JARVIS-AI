package com.jarvisblue.mobile

import android.content.Context
import com.jarvisblue.core.model.BridgeJob
import com.jarvisblue.core.model.BridgeRequest
import com.jarvisblue.core.model.PcState
import com.jarvisblue.core.model.PcStatus
import com.jarvisblue.core.tools.AssistantServices
import com.jarvisblue.core.tools.NotificationSnapshot
import com.jarvisblue.mobile.services.NotificationStore
import com.jarvisblue.mobile.services.ScreenCaptureService
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.flow.MutableStateFlow
import kotlinx.coroutines.flow.StateFlow
import kotlinx.coroutines.flow.asStateFlow
import javax.inject.Inject
import javax.inject.Singleton

/**
 * Concrete implementation of the app-level services the tool registry needs:
 * notification reading, screen text, reminders and the Windows bridge.
 */
@Singleton
class AssistantServicesImpl @Inject constructor(
    @ApplicationContext private val context: Context,
    private val notificationStore: NotificationStore,
    private val windowsBridge: com.jarvisblue.mobile.services.WindowsBridgeGateway,
) : AssistantServices {

    private val reminderJobs = MutableStateFlow<Map<String, String>>(emptyMap())

    override suspend fun recentNotifications(limit: Int): List<NotificationSnapshot> =
        notificationStore.recent(limit)

    override suspend fun visibleScreenText(): String? =
        ScreenCaptureService.lastCapturedText

    override suspend fun scheduleReminder(title: String, triggerAtEpochMs: Long): String {
        val id = java.util.UUID.randomUUID().toString()
        reminderJobs.value = reminderJobs.value + (id to title)
        val intent = android.content.Intent(
            context,
            com.jarvisblue.mobile.receivers.ReminderReceiver::class.java,
        ).apply {
            putExtra(com.jarvisblue.mobile.receivers.ReminderReceiver.EXTRA_TITLE, title)
            putExtra(com.jarvisblue.mobile.receivers.ReminderReceiver.EXTRA_ID, id)
        }
        val pending = android.app.PendingIntent.getBroadcast(
            context,
            id.hashCode(),
            intent,
            android.app.PendingIntent.FLAG_UPDATE_CURRENT or android.app.PendingIntent.FLAG_IMMUTABLE,
        )
        val alarmManager = context.getSystemService(android.app.AlarmManager::class.java)
        val canExact = android.os.Build.VERSION.SDK_INT < android.os.Build.VERSION_CODES.S ||
            alarmManager?.canScheduleExactAlarms() == true
        if (canExact) {
            alarmManager?.setExactAndAllowWhileIdle(
                android.app.AlarmManager.RTC_WAKEUP,
                triggerAtEpochMs,
                pending,
            )
        } else {
            alarmManager?.set(
                android.app.AlarmManager.RTC_WAKEUP,
                triggerAtEpochMs,
                pending,
            )
        }
        return "Reminder '$title' scheduled for ${java.time.Instant.ofEpochMilli(triggerAtEpochMs)}"
    }

    override suspend fun cancelReminder(taskId: String): Boolean {
        val existed = reminderJobs.value.containsKey(taskId)
        reminderJobs.value = reminderJobs.value - taskId
        return existed
    }

    override suspend fun remoteStatus(): PcStatus = windowsBridge.status()

    override suspend fun remoteJobs(): List<BridgeJob> = windowsBridge.jobs()

    override suspend fun submitRemoteJob(request: BridgeRequest): BridgeJob =
        windowsBridge.submit(request)

    override suspend fun cancelRemoteJob(jobId: String): Boolean = windowsBridge.cancel(jobId)
}
