package com.jarvisblue.mobile.receivers

import android.content.BroadcastReceiver
import android.content.Context
import android.content.Intent
import androidx.work.ExistingWorkPolicy
import androidx.work.OneTimeWorkRequestBuilder
import androidx.work.WorkManager
import com.jarvisblue.mobile.workers.ScheduledTaskWorker
import java.util.concurrent.TimeUnit

/**
 * Re-arms scheduled work after a reboot or an app update.
 *
 * The wake-word service is deliberately *not* restarted here: the microphone
 * foreground service must always be started by an explicit user action, and
 * Android does not permit starting it silently from a boot receiver on
 * recent releases.
 */
class BootReceiver : BroadcastReceiver() {

    override fun onReceive(context: Context, intent: Intent?) {
        val action = intent?.action ?: return
        if (action != Intent.ACTION_BOOT_COMPLETED &&
            action != Intent.ACTION_MY_PACKAGE_REPLACED
        ) {
            return
        }

        WorkManager.getInstance(context).enqueueUniqueWork(
            ScheduledTaskWorker.UNIQUE_NAME,
            ExistingWorkPolicy.REPLACE,
            OneTimeWorkRequestBuilder<ScheduledTaskWorker>()
                .setInitialDelay(2, TimeUnit.MINUTES)
                .build(),
        )
    }
}
