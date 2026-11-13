package com.jarvisblue.core.tools

import android.app.ActivityManager
import android.provider.AlarmClock
import android.app.NotificationManager
import android.content.Context
import android.content.Intent
import android.media.AudioManager
import android.media.session.MediaSessionManager
import android.net.ConnectivityManager
import android.net.Uri
import android.os.BatteryManager
import android.os.Build
import android.os.Environment
import android.os.StatFs
import android.os.SystemClock
import androidx.core.content.ContextCompat
import com.jarvisblue.core.model.DeviceDiagnostics
import java.io.File
import java.util.concurrent.TimeUnit

/**
 * Device automation built on official Android APIs.
 *
 * Everything here goes through an `Intent` that the user can see in the system's
 * own UI, or through a read-only system query. No method reaches into another
 * app's sandbox, no method reads protected storage, and no method silently
 * places a call or sends a message.
 */
class DeviceControlEngine(private val context: Context) {

    /** Launches a user-visible activity. The user always sees what opens. */
    fun launchActivity(intent: Intent): String {
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(intent)
        return "Opened ${intent.describeIntent()}"
    }

    fun launchApp(packageName: String): String {
        val intent = context.packageManager.getLaunchIntentForPackage(packageName)
            ?: throw IllegalArgumentException("No launchable activity for '$packageName'")
        intent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK)
        context.startActivity(intent)
        return "Launched ${context.packageManager.getApplicationLabel(context.packageManager.getApplicationInfo(packageName, 0))}"
    }

    fun listInstalledApps(): List<Pair<String, String>> {
        val pm = context.packageManager
        return pm.getInstalledApplications(0)
            .map { it.packageName to pm.getApplicationLabel(it).toString() }
            .sortedBy { it.second.lowercase() }
    }

    fun findApp(query: String): Pair<String, String>? {
        val needle = query.trim().lowercase()
        if (needle.isEmpty()) return null
        return listInstalledApps().firstOrNull { (pkg, label) ->
            label.lowercase().contains(needle) || pkg.lowercase().contains(needle)
        }
    }

    /** Opens the dialler with the number pre-filled. It does *not* place the call. */
    fun openDialer(number: String): String {
        val intent = Intent(Intent.ACTION_DIAL, Uri.parse("tel:${number.filter { it.isDigit() || it == '+' }}"))
        return launchActivity(intent)
    }

    /** Opens a compose screen. The message is never sent by the app. */
    fun openMessageComposer(recipient: String?, body: String?): String {
        val intent = if (recipient.isNullOrBlank()) {
            Intent(Intent.ACTION_SEND)
                .setType("text/plain")
                .putExtra(Intent.EXTRA_TEXT, body.orEmpty())
        } else {
            Intent(Intent.ACTION_SENDTO, Uri.parse("smsto:${Uri.encode(recipient)}"))
                .putExtra("sms_body", body.orEmpty())
        }
        return launchActivity(intent)
    }

    fun setAlarm(hour: Int, minute: Int, label: String?): String {
        val intent = Intent(AlarmClock.ACTION_SET_ALARM).apply {
            putExtra(AlarmClock.EXTRA_HOUR, hour)
            putExtra(AlarmClock.EXTRA_MINUTES, minute)
            putExtra(AlarmClock.EXTRA_SKIP_UI, false)
            if (!label.isNullOrBlank()) putExtra(AlarmClock.EXTRA_MESSAGE, label)
        }
        return launchActivity(intent)
    }

    /** Media transport keys are dispatched to whichever app owns the media session. */
    fun dispatchMediaKey(action: Int): String {
        val audioManager = context.getSystemService(Context.AUDIO_SERVICE) as AudioManager
        val down = android.view.KeyEvent(android.view.KeyEvent.ACTION_DOWN, action)
        val up = android.view.KeyEvent(android.view.KeyEvent.ACTION_UP, action)
        audioManager.dispatchMediaKeyEvent(down)
        audioManager.dispatchMediaKeyEvent(up)
        return "Media command ${mediaActionName(action)} sent"
    }

    fun activeMediaSessions(): List<String> = runCatching {
        val manager = context.getSystemService(Context.MEDIA_SESSION_SERVICE) as MediaSessionManager
        manager.getActiveSessions(null).map { it.packageName }.distinct()
    }.getOrDefault(emptyList())

    fun openSettingsScreen(setting: String): String {
        val intent = when (setting) {
            "wifi" -> Intent(android.provider.Settings.ACTION_WIFI_SETTINGS)
            "bluetooth" -> Intent(android.provider.Settings.ACTION_BLUETOOTH_SETTINGS)
            "battery" -> Intent(android.provider.Settings.ACTION_BATTERY_SAVER_SETTINGS)
            "display" -> Intent(android.provider.Settings.ACTION_DISPLAY_SETTINGS)
            "sound" -> Intent(android.provider.Settings.ACTION_SOUND_SETTINGS)
            "apps" -> Intent(android.provider.Settings.ACTION_APPLICATION_SETTINGS)
            "location" -> Intent(android.provider.Settings.ACTION_LOCATION_SOURCE_SETTINGS)
            "security" -> Intent(android.provider.Settings.ACTION_SECURITY_SETTINGS)
            "storage" -> Intent(android.provider.Settings.ACTION_INTERNAL_STORAGE_SETTINGS)
            "developer" -> Intent(android.provider.Settings.ACTION_APPLICATION_DEVELOPMENT_SETTINGS)
            "accessibility" -> Intent(android.provider.Settings.ACTION_ACCESSIBILITY_SETTINGS)
            "notification" -> Intent(android.provider.Settings.ACTION_APP_NOTIFICATION_SETTINGS)
            "home" -> Intent(android.provider.Settings.ACTION_HOME_SETTINGS)
            else -> Intent(android.provider.Settings.ACTION_SETTINGS)
        }
        return launchActivity(intent)
    }

    fun diagnostics(): DeviceDiagnostics {
        val batteryManager = context.getSystemService(Context.BATTERY_SERVICE) as BatteryManager
        val intent = context.registerReceiver(null, android.content.IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val level = intent?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
        val scale = intent?.getIntExtra(BatteryManager.EXTRA_SCALE, -1) ?: -1
        val percent = if (level >= 0 && scale > 0) (level * 100f / scale).toInt() else null
        val status = intent?.getIntExtra(BatteryManager.EXTRA_STATUS, -1) ?: -1

        val stat = StatFs(Environment.getDataDirectory().path)
        val storageTotal = stat.totalBytes.toDouble() / 1_073_741_824.0
        val storageFree = stat.availableBytes.toDouble() / 1_073_741_824.0

        val activityManager = context.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        val memInfo = ActivityManager.MemoryInfo()
        activityManager.getMemoryInfo(memInfo)

        val connectivity = context.getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager
        val network = connectivity.activeNetwork
        val capabilities = connectivity.getNetworkCapabilities(network)
        val networkType = when {
            capabilities == null -> "none"
            capabilities.hasTransport(android.net.NetworkCapabilities.TRANSPORT_WIFI) -> "wifi"
            capabilities.hasTransport(android.net.NetworkCapabilities.TRANSPORT_CELLULAR) -> "cellular"
            capabilities.hasTransport(android.net.NetworkCapabilities.TRANSPORT_ETHERNET) -> "ethernet"
            capabilities.hasTransport(android.net.NetworkCapabilities.TRANSPORT_VPN) -> "vpn"
            else -> "other"
        }

        val vpnActive = capabilities?.hasTransport(android.net.NetworkCapabilities.TRANSPORT_VPN) == true

        val wifiSsid = runCatching {
            val wifiManager = context.applicationContext.getSystemService(
                Context.WIFI_SERVICE,
            ) as android.net.wifi.WifiManager
            @Suppress("DEPRECATION")
            wifiManager.connectionInfo?.ssid?.trim('"')
        }.getOrNull()

        return DeviceDiagnostics(
            batteryPercent = percent,
            batteryCharging = status == BatteryManager.BATTERY_STATUS_CHARGING ||
                status == BatteryManager.BATTERY_STATUS_FULL,
            batteryHealth = when (intent?.getIntExtra(BatteryManager.EXTRA_HEALTH, -1)) {
                BatteryManager.BATTERY_HEALTH_GOOD -> "good"
                BatteryManager.BATTERY_HEALTH_OVERHEAT -> "overheating"
                BatteryManager.BATTERY_HEALTH_DEAD -> "dead"
                BatteryManager.BATTERY_HEALTH_OVER_VOLTAGE -> "over voltage"
                BatteryManager.BATTERY_HEALTH_COLD -> "cold"
                else -> null
            },
            temperatureC = intent?.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, 0)
                ?.takeIf { it != 0 }?.div(10.0),
            storageUsedGb = (storageTotal - storageFree).takeIf { storageTotal > 0 },
            storageTotalGb = storageTotal.takeIf { it > 0 },
            storageFreeGb = storageFree.takeIf { storageTotal > 0 },
            ramUsedGb = (memInfo.totalMem - memInfo.availMem).toDouble() / 1_073_741_824.0,
            ramTotalGb = memInfo.totalMem.toDouble() / 1_073_741_824.0,
            networkType = networkType,
            networkConnected = network != null,
            wifiSsid = wifiSsid?.takeIf { it.isNotEmpty() },
            vpnActive = vpnActive,
            sdkInt = Build.VERSION.SDK_INT,
            manufacturer = Build.MANUFACTURER,
            model = Build.MODEL,
            osRelease = Build.VERSION.RELEASE,
            uptimeHours = TimeUnit.MILLISECONDS.toHours(SystemClock.elapsedRealtime()),
        )
    }

    fun shareText(text: String, subject: String? = null): String {
        val intent = Intent(Intent.ACTION_SEND).apply {
            type = "text/plain"
            putExtra(Intent.EXTRA_TEXT, text)
            subject?.let { putExtra(Intent.EXTRA_SUBJECT, it) }
        }
        return launchActivity(Intent.createChooser(intent, "Share via"))
    }

    /** True when the user has enabled the app's notifications. */
    fun notificationsEnabled(): Boolean =
        androidx.core.app.NotificationManagerCompat.from(context).areNotificationsEnabled()

    private fun Intent.describeIntent(): String =
        action?.substringAfterLast('.') ?: "activity"
}

internal const val MEDIA_PLAY = android.view.KeyEvent.KEYCODE_MEDIA_PLAY
internal const val MEDIA_PAUSE = android.view.KeyEvent.KEYCODE_MEDIA_PAUSE
internal const val MEDIA_NEXT = android.view.KeyEvent.KEYCODE_MEDIA_NEXT
internal const val MEDIA_PREVIOUS = android.view.KeyEvent.KEYCODE_MEDIA_PREVIOUS

internal fun mediaActionName(action: Int): String = when (action) {
    MEDIA_PLAY -> "play"
    MEDIA_PAUSE -> "pause"
    MEDIA_NEXT -> "next track"
    MEDIA_PREVIOUS -> "previous track"
    else -> "unknown"
}
