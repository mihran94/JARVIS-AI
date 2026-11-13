package com.jarvisblue.core.tools

import com.jarvisblue.core.model.RiskLevel
import com.jarvisblue.core.model.ToolCategory
import com.jarvisblue.core.model.ToolSpec
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class RiskEvaluatorTest {

    private val communicationTool = ToolSpec(
        name = "compose_message",
        displayName = "Draft a message",
        description = "",
        category = ToolCategory.COMMUNICATION,
        parameters = emptyList(),
        riskLevel = RiskLevel.HIGH,
        requiredPermissions = emptySet(),
    )

    @Test
    fun `payment content raises communication risk to critical`() {
        val args = buildJsonObject {
            put("body", JsonPrimitive("send 5000 usd to my bank account now"))
        }
        assertEquals(RiskLevel.CRITICAL, RiskEvaluator.evaluate(communicationTool, args))
    }

    @Test
    fun `ordinary message keeps its declared risk`() {
        val args = buildJsonObject { put("body", JsonPrimitive("running late, see you soon")) }
        assertEquals(RiskLevel.HIGH, RiskEvaluator.evaluate(communicationTool, args))
    }

    @Test
    fun `remote tools are always at least high risk`() {
        val remoteTool = communicationTool.copy(
            category = ToolCategory.REMOTE,
            riskLevel = RiskLevel.LOW,
        )
        val risk = RiskEvaluator.evaluate(remoteTool, buildJsonObject { })
        assertTrue(risk.atLeast(RiskLevel.HIGH))
    }

    @Test
    fun `destructive tools are raised to high risk`() {
        val destructive = communicationTool.copy(
            category = ToolCategory.FILES,
            riskLevel = RiskLevel.LOW,
            destructive = true,
        )
        assertTrue(RiskEvaluator.evaluate(destructive, buildJsonObject { }).atLeast(RiskLevel.HIGH))
    }

    @Test
    fun `sensitive paths raise file risk`() {
        val fileTool = communicationTool.copy(category = ToolCategory.FILES, riskLevel = RiskLevel.LOW)
        val risk = RiskEvaluator.evaluate(
            fileTool,
            buildJsonObject { put("path", JsonPrimitive("/home/user/.ssh/id_rsa")) },
        )
        assertTrue(risk.atLeast(RiskLevel.MEDIUM))
    }
}
