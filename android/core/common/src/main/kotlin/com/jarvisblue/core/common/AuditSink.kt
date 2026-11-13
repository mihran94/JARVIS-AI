package com.jarvisblue.core.common

/**
 * Write-only audit channel. Every privileged action, permission change and
 * confirmation lands here so the user can export a complete history.
 */
interface AuditSink {
    suspend fun record(
        category: String,
        title: String,
        detail: String = "",
        severity: String = "INFO",
        toolName: String? = null,
        riskLevel: String = "NONE",
        success: Boolean = true,
        actor: String = "user",
    )
}

/** Sink that discards everything — used in tests and previews. */
object NoopAuditSink : AuditSink {
    override suspend fun record(
        category: String,
        title: String,
        detail: String,
        severity: String,
        toolName: String?,
        riskLevel: String,
        success: Boolean,
        actor: String,
    ) = Unit
}
