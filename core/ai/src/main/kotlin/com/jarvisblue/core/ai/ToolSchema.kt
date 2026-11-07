package com.jarvisblue.core.ai

import com.jarvisblue.core.model.ParamType
import com.jarvisblue.core.model.ToolSpec
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.JsonPrimitive
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * Converts the declarative [ToolSpec] into the JSON-Schema shapes the different
 * providers expect (OpenAI function schema, Gemini functionDeclarations, Ollama tools).
 */
object ToolSchema {

    fun toJsonSchema(spec: ToolSpec): JsonObject = buildJsonObject {
        put("type", "object")
        put("properties", buildJsonObject {
            spec.parameters.forEach { param ->
                put(param.name, parameterSchema(param))
            }
        })
        val required = spec.parameters.filter { it.required }.map { it.name }
        if (required.isNotEmpty()) {
            put("required", JsonArray(required.map { JsonPrimitive(it) }))
        }
        put("additionalProperties", false)
    }

    fun toOpenAiTool(spec: ToolSpec): JsonObject = buildJsonObject {
        put("type", "function")
        put("function", buildJsonObject {
            put("name", spec.name)
            put("description", spec.description)
            put("parameters", toJsonSchema(spec))
        })
    }

    fun toOllamaTool(spec: ToolSpec): JsonObject = buildJsonObject {
        put("type", "function")
        put("function", buildJsonObject {
            put("name", spec.name)
            put("description", spec.description)
            put("parameters", toJsonSchema(spec))
        })
    }

    fun toGeminiDeclaration(spec: ToolSpec): JsonObject = buildJsonObject {
        put("name", spec.name)
        put("description", spec.description)
        put("parameters", toJsonSchema(spec))
    }

    private fun parameterSchema(param: com.jarvisblue.core.model.ToolParameter): JsonObject =
        buildJsonObject {
            when (param.type) {
                ParamType.STRING -> put("type", "string")
                ParamType.INTEGER -> put("type", "integer")
                ParamType.NUMBER -> put("type", "number")
                ParamType.BOOLEAN -> put("type", "boolean")
                ParamType.OBJECT -> put("type", "object")
                ParamType.ARRAY -> put("type", "array")
            }
            put("description", param.description)
            if (param.enumValues.isNotEmpty()) {
                put("enum", buildJsonArray { param.enumValues.forEach { add(JsonPrimitive(it)) } })
            }
            param.minimum?.let { put("minimum", it) }
            param.maximum?.let { put("maximum", it) }
            param.maxLength?.let { put("maxLength", it) }
            param.default?.let { put("default", JsonPrimitive(it)) }
        }
}
