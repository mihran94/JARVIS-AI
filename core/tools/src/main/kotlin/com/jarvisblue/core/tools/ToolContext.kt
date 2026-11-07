package com.jarvisblue.core.tools

import android.content.Context
import com.jarvisblue.core.common.AuditSink
import kotlinx.serialization.json.JsonObject

/** What a tool handler receives when it is invoked. */
data class ToolContext(
    val appContext: Context,
    val audit: AuditSink,
    val grantedPermissions: () -> Set<String>,
    val isToolEnabled: (String) -> Boolean,
    val emergencyStopEngaged: () -> Boolean,
    val requestConfirmation: suspend (ConfirmationRequest) -> Boolean,
    val workspaceRoot: java.io.File,
)

/** Result of a successful tool invocation. */
data class ToolOutput(
    val summary: String,
    val details: Map<String, String> = emptyMap(),
    val data: JsonObject? = null,
)

/** Description of a confirmation the tool needs before it can continue. */
data class ConfirmationRequest(
    val toolName: String,
    val title: String,
    val detail: String,
    val riskLevel: String,
    val effects: List<String>,
)

/** Handler contract for a registered tool. */
fun interface ToolHandler {
    suspend fun invoke(context: ToolContext, arguments: JsonObject): ToolOutput
}
