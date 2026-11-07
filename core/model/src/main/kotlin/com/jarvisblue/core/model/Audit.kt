package com.jarvisblue.core.model

import kotlinx.serialization.Serializable

enum class AuditSeverity { INFO, NOTICE, WARNING, CRITICAL }

enum class AuditCategory {
    CHAT, TOOL, PERMISSION, CONFIRMATION, VOICE, REMOTE, FILE, NETWORK, AUTH, SYSTEM,
}

@Serializable
data class AuditEvent(
    val id: String,
    val timestampEpochMs: Long,
    val category: AuditCategory,
    val severity: AuditSeverity,
    val title: String,
    val detail: String = "",
    val toolName: String? = null,
    val riskLevel: RiskLevel = RiskLevel.NONE,
    val success: Boolean = true,
    val actor: String = "user",
)
