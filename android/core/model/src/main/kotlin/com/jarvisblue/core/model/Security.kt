package com.jarvisblue.core.model

import kotlinx.serialization.Serializable

@Serializable
enum class FindingSeverity { INFO, LOW, MEDIUM, HIGH, CRITICAL }

@Serializable
data class SecurityFinding(
    val id: String,
    val title: String,
    val severity: FindingSeverity,
    val category: String,
    val description: String,
    val remediation: String,
    val evidence: String = "",
    val reference: String = "",
)

@Serializable
enum class AuthorizationKind { OWNED_NETWORK, WRITTEN_PERMISSION, LAB_EXERCISE, SELF_DEVICE }

@Serializable
data class AuthorizationGrant(
    val id: String,
    val kind: AuthorizationKind,
    val scope: String,
    val grantedAtEpochMs: Long,
    val expiresAtEpochMs: Long? = null,
    val notes: String = "",
) {
    fun isActive(nowEpochMs: Long): Boolean =
        expiresAtEpochMs == null || nowEpochMs < expiresAtEpochMs
}

@Serializable
data class SecurityReport(
    val id: String,
    val scope: String,
    val createdAtEpochMs: Long,
    val findings: List<SecurityFinding>,
    val notes: String = "",
) {
    val highestSeverity: FindingSeverity?
        get() = findings.maxByOrNull { it.severity.ordinal }?.severity
}
