package com.jarvisblue.core.model

import kotlinx.serialization.Serializable

enum class TaskStatus { QUEUED, RUNNING, WAITING_CONFIRMATION, SUCCEEDED, FAILED, CANCELLED, BLOCKED }

@Serializable
enum class TaskTrigger {
    MANUAL, SCHEDULED, EVENT, CHAINED, VOICE, REMOTE,
}

@Serializable
data class AutomationTask(
    val id: String,
    val title: String,
    val goal: String,
    val trigger: TaskTrigger = TaskTrigger.MANUAL,
    val scheduleCron: String? = null,
    val triggerEvent: String? = null,
    val steps: List<PlannedAction> = emptyList(),
    val dependencies: List<String> = emptyList(),
    val status: TaskStatus = TaskStatus.QUEUED,
    val maxRetries: Int = 2,
    val retryCount: Int = 0,
    val requiresConfirmation: Boolean = false,
    val enabled: Boolean = true,
    val createdAtEpochMs: Long = 0L,
    val updatedAtEpochMs: Long = 0L,
    val lastError: String? = null,
    val nextRunEpochMs: Long? = null,
)
