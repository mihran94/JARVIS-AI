package com.jarvisblue.core.model

import kotlinx.serialization.Serializable

@Serializable
enum class PcState { UNKNOWN, ONLINE, OFFLINE, DEGRADED, PAIRING_REQUIRED }

@Serializable
enum class BridgeJobState { QUEUED, RUNNING, SUCCEEDED, FAILED, CANCELLED, REJECTED }

@Serializable
enum class BridgeJobKind {
    PYTHON_PROJECT, AFTER_EFFECTS_RENDER, CODE_REVIEW, DOCUMENT_ACCESS, WORKFLOW, CUSTOM,
}

@Serializable
data class PcStatus(
    val peerId: String,
    val state: PcState = PcState.UNKNOWN,
    val hostname: String = "",
    val platform: String = "",
    val agentVersion: String = "",
    val lastHeartbeatEpochMs: Long = 0L,
    val queuedJobs: Int = 0,
    val runningJobs: Int = 0,
    val cpuPercent: Double? = null,
    val memoryPercent: Double? = null,
    val gpuPercent: Double? = null,
    val diskFreeGb: Double? = null,
    val detail: String = "",
)

@Serializable
data class BridgeJob(
    val id: String,
    val kind: BridgeJobKind,
    val title: String,
    val state: BridgeJobState = BridgeJobState.QUEUED,
    val progress: Double = 0.0,
    val createdAtEpochMs: Long = 0L,
    val updatedAtEpochMs: Long = 0L,
    val logPreview: List<String> = emptyList(),
    val outputFiles: List<String> = emptyList(),
    val error: String? = null,
    val requiresApproval: Boolean = false,
)

@Serializable
data class BridgeRequest(
    val kind: BridgeJobKind,
    val title: String,
    val payloadJson: String,
    val requireApproval: Boolean = true,
)

@Serializable
data class WindowsPeer(
    val peerId: String,
    val displayName: String,
    val host: String,
    val port: Int,
    val pairedAtEpochMs: Long,
    val lastSeenEpochMs: Long = 0L,
    val sharedSecretAlias: String,
    val trusted: Boolean = false,
)
