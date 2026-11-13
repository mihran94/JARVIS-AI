package com.jarvisblue.mobile

import android.app.Application
import dagger.hilt.android.HiltAndroidApp

/**
 * Remote-only host. No local Android AI tools, wake listeners, scheduled
 * jobs, screenshot capture or background services are started.
 */
@HiltAndroidApp
class JarvisApplication : Application() {
    // Source modules retained for history still reference these constants.
    // No notification channels or microphone services are activated.
    companion object {
        const val WAKE_CHANNEL_ID = "jarvis_wake_word"
        const val REMINDER_CHANNEL_ID = "jarvis_reminders"
    }
}
