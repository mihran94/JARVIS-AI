package com.jarvisblue.core.ai

import com.jarvisblue.core.model.ParamType
import com.jarvisblue.core.model.ToolParameter
import com.jarvisblue.core.model.ToolSpec
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.jsonPrimitive
import kotlinx.serialization.json.put
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class GeminiSchemaAdapterTest {
    @Test fun preservesOpenAiSchemaButConvertsGemini() {
        val spec = ToolSpec(
            name = "test_tool", description = "A safe test tool",
            parameters = listOf(
                ToolParameter("text", ParamType.STRING, "Text", required = true, maxLength = 40),
            ),
        )
        val openAi = ToolSchema.toJsonSchema(spec)
        assertTrue(openAi.containsKey("additionalProperties"))
        assertEquals("object", openAi["type"]?.jsonPrimitive?.content)
        val gemini = ToolSchema.toGeminiDeclaration(spec)
        val parameters = gemini["parameters"] as JsonObject
        assertFalse(parameters.containsKey("additionalProperties"))
        assertEquals("OBJECT", parameters["type"]?.jsonPrimitive?.content)
        val textField = (parameters["properties"] as JsonObject)["text"] as JsonObject
        assertEquals("STRING", textField["type"]?.jsonPrimitive?.content)
        assertEquals("40", textField["maxLength"]?.jsonPrimitive?.content)
    }

    @Test fun removesUnsupportedFieldsRecursively() {
        val schema = buildJsonObject {
            put("type", "object")
            put("additionalProperties", false)
            put("properties", buildJsonObject {
                put("nested", buildJsonObject {
                    put("type", "object")
                    put("additionalProperties", false)
                    put("default", "do not send")
                })
            })
        }
        val result = ToolSchema.toGeminiParameters(schema)
        val nested = (result["properties"] as JsonObject)["nested"] as JsonObject
        assertFalse(result.containsKey("additionalProperties"))
        assertFalse(nested.containsKey("additionalProperties"))
        assertFalse(nested.containsKey("default"))
        assertEquals("OBJECT", nested["type"]?.jsonPrimitive?.content)
    }
}
