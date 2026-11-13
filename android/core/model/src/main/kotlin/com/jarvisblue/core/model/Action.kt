package com.jarvisblue.core.model

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

/**
 * A single executable step produced by the planner. Plans are data, not effects:
 * nothing happens until [com.jarvisblue.core.tools.ToolExecutor] has validated the
 * schema, checked the permission grant, evaluated the risk and (when required)
 * collected a fresh user confirmation.
 */
@Serializable
data class PlannedAction(
    val id: String,
    val toolName: String,
    val arguments: JsonObject,
    val rationale: String = "",
    val riskLevel: RiskLevel = RiskLevel.LOW,
    val dependsOn: List<String> = emptyList(),
)

@Serializable
data class ActionPlan(
    val id: String,
    val goal: String,
    val steps: List<PlannedAction>,
    val requiresConfirmation: Boolean = false,
    val createdAtEpochMs: Long = 0L,
)

@Serializable
data class ActionResult(
    val actionId: String,
    val toolName: String,
    val success: Boolean,
    val output: String,
    val error: String? = null,
    val startedAtEpochMs: Long = 0L,
    val finishedAtEpochMs: Long = 0L,
    val confirmedByUser: Boolean = false,
)

@Serializable
enum class ExecutionVerdict {
    /** Executed successfully. */
    COMPLETED,
    /** Blocked because a permission was not granted. */
    DENIED_PERMISSION,
    /** Blocked because risk policy required a confirmation that was not given. */
    NEEDS_CONFIRMATION,
    /** Blocked because the arguments did not match the tool schema. */
    INVALID_ARGUMENTS,
    /** Blocked by the global emergency stop. */
    EMERGENCY_STOP,
    /** The tool itself failed. */
    ERROR,
}

@Serializable
data class ExecutionOutcome(
    val verdict: ExecutionVerdict,
    val result: ActionResult? = null,
    val message: String,
    val approvalRequired: Boolean = false,
    val riskLevel: RiskLevel = RiskLevel.NONE,
)
