package com.jarvisblue.core.tools

import com.jarvisblue.core.model.RiskLevel
import com.jarvisblue.core.model.ToolSpec

/**
 * Computes the effective risk of a concrete invocation.
 *
 * The declared risk of the tool is a baseline. The effective risk is raised when
 * the arguments themselves are sensitive — for example a "read file" tool pointed
 * at a path outside the granted workspace, or a messaging tool whose body
 * mentions a payment. Raising the risk can only add friction (an extra
 * confirmation), never remove it.
 */
object RiskEvaluator {

    fun evaluate(spec: ToolSpec, arguments: kotlinx.serialization.json.JsonObject): RiskLevel {
        var risk = spec.riskLevel

        if (spec.destructive) risk = maxOf(risk, RiskLevel.HIGH)

        if (spec.category == com.jarvisblue.core.model.ToolCategory.COMMUNICATION) {
            val body = stringArg(arguments, "body") ?: stringArg(arguments, "message") ?: ""
            if (PAYMENT_MARKERS.any { body.contains(it, ignoreCase = true) }) {
                risk = maxOf(risk, RiskLevel.CRITICAL)
            }
        }

        if (spec.category == com.jarvisblue.core.model.ToolCategory.FILES) {
            val path = stringArg(arguments, "path")
            if (path != null && looksSensitive(path)) {
                risk = maxOf(risk, RiskLevel.MEDIUM)
            }
        }

        if (spec.category == com.jarvisblue.core.model.ToolCategory.REMOTE) {
            risk = maxOf(risk, RiskLevel.HIGH)
        }

        return risk
    }

    fun stringArg(arguments: kotlinx.serialization.json.JsonObject, name: String): String? =
        (arguments[name] as? kotlinx.serialization.json.JsonPrimitive)?.content

    private val PAYMENT_MARKERS = listOf(
        "upi", "otp", "pin", "cvv", "credit card", "debit card", "account number",
        "pay ", "transfer ", "wire ", "₹", "$", "usd", "inr", "bank",
    )

    private val SENSITIVE_PATH_MARKERS = listOf(
        ".ssh", ".gnupg", ".aws", ".config", "keystore", "password", "credential",
        "wallet", "bitcoin", "/data/data/", "auth",
    )

    fun looksSensitive(path: String): Boolean {
        val lower = path.lowercase()
        return SENSITIVE_PATH_MARKERS.any { lower.contains(it) }
    }
}
