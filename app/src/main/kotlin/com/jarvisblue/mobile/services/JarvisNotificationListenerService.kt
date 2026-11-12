package com.jarvisblue.mobile.services

import android.service.notification.NotificationListenerService
import android.service.notification.StatusBarNotification
import com.jarvisblue.core.tools.NotificationSnapshot
import dagger.hilt.android.AndroidEntryPoint
import javax.inject.Inject

/**
 * Reads posted notifications so the assistant can summarise them.
 *
 * The user must grant access explicitly in Android settings
 * (Settings → Notifications → Device & app notifications → Notification access).
 * Until then this service is never bound and no notification is visible.
 */
@AndroidEntryPoint
class JarvisNotificationListenerService : NotificationListenerService() {

    @Inject lateinit var store: NotificationStore

    // Android's notification-access grant alone is not consent to retain
    // message content. Keep capture disabled until the app offers explicit,
    // revocable in-app consent with retention and exclusion controls.
    private val notificationCaptureEnabled = false

    override fun onNotificationPosted(sbn: StatusBarNotification?) {
        if (!notificationCaptureEnabled) return
        val notification = sbn ?: return
        val extras = notification.notification?.extras ?: return
        val title = extras.getCharSequence(android.app.Notification.EXTRA_TITLE)?.toString().orEmpty()
        val body = extras.getCharSequence(android.app.Notification.EXTRA_TEXT)?.toString().orEmpty()
        val label = runCatching {
            packageManager.getApplicationLabel(packageManager.getApplicationInfo(notification.packageName, 0))
        }.getOrDefault(notification.packageName)

        store.record(
            NotificationSnapshot(
                packageName = notification.packageName,
                appLabel = label.toString(),
                title = title,
                body = body,
                postedAtEpochMs = notification.postTime,
                ongoing = notification.isOngoing,
            ),
        )
    }

    override fun onListenerConnected() {
        super.onListenerConnected()
        // Only keep the existing snapshot cache; we deliberately do not dump the
        // full history at connect time because the user has not asked for it.
    }
}
