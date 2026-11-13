package com.jarvisblue.core.model

import kotlinx.serialization.Serializable
import kotlinx.serialization.json.JsonObject

/**
 * Declarative contract for a tool the AI is allowed to call.
 *
 * The registry is deliberately schema driven: every tool exposes a JSON-Schema-ish
 * description of its parameters, and [ToolExecutor] refuses to invoke a tool whose
 * arguments do not validate. Models can therefore never smuggle free-form payloads
 * past the permission layer.
 */
@Serializable
data class ToolSpec(
    val name: String,
    val displayName: String,
    val description: String,
    val category: ToolCategory,
    val parameters: List<ToolParameter>,
    val riskLevel: RiskLevel,
    /** Permission buckets that must all be granted before execution. */
    val requiredPermissions: Set<Permission>,
    /** true when a fresh user confirmation is mandatory for every invocation. */
    val requiresConfirmation: Boolean = false,
    val destructive: Boolean = false,
    val offlineCapable: Boolean = true,
    val exampleArguments: JsonObject? = null,
)

@Serializable
data class ToolParameter(
    val name: String,
    val type: ParamType,
    val description: String,
    val required: Boolean = false,
    val default: String? = null,
    val enumValues: List<String> = emptyList(),
    val minimum: Double? = null,
    val maximum: Double? = null,
    val maxLength: Int? = null,
)

@Serializable
enum class ParamType { STRING, INTEGER, NUMBER, BOOLEAN, OBJECT, ARRAY }

@Serializable
enum class ToolCategory {
    DEVICE, AUTOMATION, COMMUNICATION, FILES, INFORMATION, SYSTEM,
    DEVELOPMENT, SECURITY, REMOTE, MEMORY, QUANTUM, MEDIA,
}

@Serializable
enum class RiskLevel(val score: Int) {
    /** Read-only, no side effects. */
    NONE(0),
    /** Local, reversible, non-sensitive. */
    LOW(1),
    /** Touches user data or settings; may need confirmation. */
    MEDIUM(2),
    /** Irreversible or communicates outward; always needs confirmation. */
    HIGH(3),
    /** Financial / destructive / credential-bearing. Always confirmed, never auto-run. */
    CRITICAL(4);

    fun atLeast(other: RiskLevel): Boolean = score >= other.score
}
