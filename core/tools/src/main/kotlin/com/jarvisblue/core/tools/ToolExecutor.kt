package com.jarvisblue.core.tools

import com.jarvisblue.core.model.ExecutionOutcome
import com.jarvisblue.core.model.ExecutionVerdict
import com.jarvisblue.core.model.RiskLevel
import com.jarvisblue.core.security.EmergencyStop
import com.jarvisblue.core.security.PermissionGrantStore
import kotlinx.serialization.json.JsonObject
import java.util.UUID

/**
 * The single execution path for every tool call.
 *
 * Order of checks (each one can only stop the action):
 *   1. Emergency stop engaged?
 *   2. Tool known and enabled by the user?
 *   3. Arguments valid against the tool schema?
 *   4. Every required permission bucket granted?
 *   5. Effective risk requires a fresh confirmation the user has given?
 *   6. Execute, then write an audit entry.
 *
 * Nothing bypasses this class — the AI layer produces *requests*, and this class
 * decides what actually happens.
 */
class ToolExecutor(
    private val registry: ToolRegistry,
    private val grantStore: PermissionGrantStore,
    private val emergencyStop: EmergencyStop,
) {

    suspend fun execute(
        toolName: String,
        arguments: JsonObject,
        context: ToolContext,
        alreadyConfirmed: Boolean = false,
    ): ExecutionOutcome {
        if (emergencyStop.engaged.value) {
            return outcome(
                verdict = ExecutionVerdict.EMERGENCY_STOP,
                message = "Emergency stop is engaged — no actions can run until you release it.",
                risk = RiskLevel.CRITICAL,
            )
        }

        val registered = registry.find(toolName)
            ?: return outcome(
                verdict = ExecutionVerdict.INVALID_ARGUMENTS,
                message = "Unknown tool '$toolName'.",
            )

        val spec = registered.spec

        if (!context.isToolEnabled(spec.name)) {
            return outcome(
                verdict = ExecutionVerdict.DENIED_PERMISSION,
                message = "The tool '${spec.displayName}' is switched off in the Permissions dashboard.",
            )
        }

        val validation = SchemaValidator.validate(spec, arguments)
        if (validation is SchemaValidator.Result.Invalid) {
            context.audit.record(
                category = "TOOL",
                title = "Rejected malformed call to ${spec.displayName}",
                detail = validation.errors.joinToString("; "),
                severity = "WARNING",
                toolName = spec.name,
                riskLevel = spec.riskLevel.name,
                success = false,
            )
            return outcome(
                verdict = ExecutionVerdict.INVALID_ARGUMENTS,
                message = "Invalid parameters for ${spec.displayName}: ${validation.errors.joinToString("; ")}",
            )
        }
        val normalized = (validation as SchemaValidator.Result.Valid).normalized

        val missing = spec.requiredPermissions
            .filterNot { context.grantedPermissions().contains(it.id) }
        if (missing.isNotEmpty()) {
            context.audit.record(
                category = "PERMISSION",
                title = "Denied ${spec.displayName}: missing permission",
                detail = missing.joinToString(", ") { it.label },
                severity = "NOTICE",
                toolName = spec.name,
                riskLevel = spec.riskLevel.name,
                success = false,
            )
            return outcome(
                verdict = ExecutionVerdict.DENIED_PERMISSION,
                message = "Missing permission: ${missing.joinToString(", ") { it.label }}.",
            )
        }

        val effectiveRisk = RiskEvaluator.evaluate(spec, normalized)
        val needsConfirmation = spec.requiresConfirmation || effectiveRisk.atLeast(RiskLevel.HIGH)

        if (needsConfirmation && !alreadyConfirmed) {
            context.audit.record(
                category = "CONFIRMATION",
                title = "Awaiting confirmation for ${spec.displayName}",
                detail = spec.description,
                severity = "NOTICE",
                toolName = spec.name,
                riskLevel = effectiveRisk.name,
                success = false,
            )
            return outcome(
                verdict = ExecutionVerdict.NEEDS_CONFIRMATION,
                message = "${spec.displayName} needs your confirmation.",
                approvalRequired = true,
                risk = effectiveRisk,
            )
        }

        val startedAt = System.currentTimeMillis()
        return try {
            val output = registered.handler.invoke(context, normalized)
            context.audit.record(
                category = "TOOL",
                title = "Executed ${spec.displayName}",
                detail = output.summary,
                severity = "INFO",
                toolName = spec.name,
                riskLevel = effectiveRisk.name,
                success = true,
            )
            ExecutionOutcome(
                verdict = ExecutionVerdict.COMPLETED,
                result = com.jarvisblue.core.model.ActionResult(
                    actionId = UUID.randomUUID().toString(),
                    toolName = spec.name,
                    success = true,
                    output = output.summary,
                    startedAtEpochMs = startedAt,
                    finishedAtEpochMs = System.currentTimeMillis(),
                    confirmedByUser = alreadyConfirmed,
                ),
                message = output.summary,
                riskLevel = effectiveRisk,
            )
        } catch (t: Throwable) {
            context.audit.record(
                category = "TOOL",
                title = "Failed ${spec.displayName}",
                detail = t.message ?: t::class.java.simpleName,
                severity = "WARNING",
                toolName = spec.name,
                riskLevel = effectiveRisk.name,
                success = false,
            )
            outcome(
                verdict = ExecutionVerdict.ERROR,
                message = "${spec.displayName} failed: ${t.message ?: "unknown error"}",
                risk = effectiveRisk,
            )
        }
    }

    private fun outcome(
        verdict: ExecutionVerdict,
        message: String,
        approvalRequired: Boolean = false,
        risk: RiskLevel = RiskLevel.NONE,
    ) = ExecutionOutcome(
        verdict = verdict,
        message = message,
        approvalRequired = approvalRequired,
        riskLevel = risk,
    )
}
