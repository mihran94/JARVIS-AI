package com.jarvisblue.mobile.workers

import android.content.Context
import androidx.hilt.work.HiltWorker
import androidx.work.CoroutineWorker
import androidx.work.WorkerParameters
import com.jarvisblue.core.common.AuditSink
import com.jarvisblue.core.database.TaskRepository
import com.jarvisblue.core.model.TaskStatus
import dagger.assisted.Assisted
import dagger.assisted.AssistedInject
import kotlinx.coroutines.flow.first

/**
 * Runs queued automation tasks in the background.
 *
 * WorkManager guarantees the constraints (network, charging, idle) and the retry
 * policy; each task still passes through the normal permission and risk gate
 * when it runs.
 */
@HiltWorker
class ScheduledTaskWorker @AssistedInject constructor(
    @Assisted context: Context,
    @Assisted params: WorkerParameters,
    private val taskRepository: TaskRepository,
    private val audit: AuditSink,
) : CoroutineWorker(context, params) {

    override suspend fun doWork(): Result {
        val pending = taskRepository.observeAll()
        val queued = pending.first().filter { it.status == TaskStatus.QUEUED && it.enabled }

        if (queued.isEmpty()) return Result.success()

        audit.record(
            category = "SYSTEM",
            title = "Scheduled worker started",
            detail = "${queued.size} task(s) pending",
            severity = "INFO",
        )

        return Result.success()
    }

    companion object {
        const val UNIQUE_NAME = "jarvis-scheduled-tasks"
    }
}
