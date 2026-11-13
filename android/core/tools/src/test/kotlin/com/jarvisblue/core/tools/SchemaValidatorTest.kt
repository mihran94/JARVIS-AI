package com.jarvisblue.core.tools

import com.jarvisblue.core.model.ParamType
import com.jarvisblue.core.model.ToolParameter
import com.jarvisblue.core.model.ToolSpec
import com.jarvisblue.core.model.RiskLevel
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonObject
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test

class SchemaValidatorTest {

    private val spec = ToolSpec(
        name = "set_alarm",
        displayName = "Set an alarm",
        description = "Create an alarm.",
        category = com.jarvisblue.core.model.ToolCategory.AUTOMATION,
        parameters = listOf(
            ToolParameter("hour", ParamType.INTEGER, "Hour", required = true, minimum = 0.0, maximum = 23.0),
            ToolParameter("minute", ParamType.INTEGER, "Minute", required = true, minimum = 0.0, maximum = 59.0),
            ToolParameter("label", ParamType.STRING, "Label", maxLength = 10),
        ),
        riskLevel = RiskLevel.LOW,
        requiredPermissions = emptySet(),
    )

    @Test
    fun `accepts a valid call and applies defaults`() {
        val args = buildJsonObject {
            put("hour", JsonPrimitive(7))
            put("minute", JsonPrimitive(30))
        }
        val result = SchemaValidator.validate(spec, args)
        assertTrue(result is SchemaValidator.Result.Valid)
    }

    @Test
    fun `rejects a missing required parameter`() {
        val result = SchemaValidator.validate(spec, buildJsonObject { put("hour", JsonPrimitive(7)) })
        assertTrue(result is SchemaValidator.Result.Invalid)
        assertTrue((result as SchemaValidator.Result.Invalid).errors.any { it.contains("minute") })
    }

    @Test
    fun `rejects unknown parameters so nothing can be smuggled in`() {
        val args = buildJsonObject {
            put("hour", JsonPrimitive(7))
            put("minute", JsonPrimitive(30))
            put("__injected", JsonPrimitive("drop table"))
        }
        val result = SchemaValidator.validate(spec, args)
        assertTrue(result is SchemaValidator.Result.Invalid)
        assertTrue((result as SchemaValidator.Result.Invalid).errors.any { it.contains("Unknown parameter") })
    }

    @Test
    fun `rejects a wrong type`() {
        val args = buildJsonObject {
            put("hour", JsonPrimitive("seven"))
            put("minute", JsonPrimitive(30))
        }
        val result = SchemaValidator.validate(spec, args)
        assertTrue(result is SchemaValidator.Result.Invalid)
    }

    @Test
    fun `rejects an out of range number`() {
        val args = buildJsonObject {
            put("hour", JsonPrimitive(99))
            put("minute", JsonPrimitive(30))
        }
        val result = SchemaValidator.validate(spec, args)
        assertTrue(result is SchemaValidator.Result.Invalid)
        assertTrue((result as SchemaValidator.Result.Invalid).errors.any { it.contains("maximum") })
    }

    @Test
    fun `rejects a string longer than maxLength`() {
        val args = buildJsonObject {
            put("hour", JsonPrimitive(7))
            put("minute", JsonPrimitive(30))
            put("label", JsonPrimitive("this label is definitely too long"))
        }
        val result = SchemaValidator.validate(spec, args)
        assertTrue(result is SchemaValidator.Result.Invalid)
    }

    @Test
    fun `rejects a value outside the enum`() {
        val enumSpec = spec.copy(
            parameters = listOf(
                ToolParameter(
                    "action", ParamType.STRING, "Action",
                    enumValues = listOf("play", "pause"),
                ),
            ),
        )
        val result = SchemaValidator.validate(
            enumSpec,
            buildJsonObject { put("action", JsonPrimitive("selfdestruct")) },
        )
        assertTrue(result is SchemaValidator.Result.Invalid)
    }

    @Test
    fun `empty arguments satisfy a tool with no parameters`() {
        val noArgSpec = spec.copy(parameters = emptyList())
        val result = SchemaValidator.validate(noArgSpec, JsonObject(emptyMap()))
        assertTrue(result is SchemaValidator.Result.Valid)
    }
}
