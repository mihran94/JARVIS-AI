package com.jarvisblue.core.tools

import com.jarvisblue.core.ai.ToolSchema
import com.jarvisblue.core.model.ToolSpec
import kotlinx.serialization.json.JsonObject
import java.util.concurrent.ConcurrentHashMap

/**
 * The single registry of everything JARVIS BLUE can do.
 *
 * Tools are registered once at startup; the AI only ever sees the schemas that
 * are registered here, and the executor only ever dispatches to handlers that
 * are registered here. There is no dynamic tool creation.
 */
class ToolRegistry {

    private val tools = ConcurrentHashMap<String, RegisteredTool>()

    data class RegisteredTool(
        val spec: ToolSpec,
        val handler: ToolHandler,
    )

    fun register(spec: ToolSpec, handler: ToolHandler) {
        require(spec.name.isNotBlank()) { "Tool name must not be blank" }
        require(spec.name.matches(NAME_PATTERN)) {
            "Tool name '${spec.name}' must match ${NAME_PATTERN.pattern}"
        }
        tools[spec.name] = RegisteredTool(spec, handler)
    }

    fun unregister(name: String) {
        tools.remove(name)
    }

    fun find(name: String): RegisteredTool? = tools[name]

    fun all(): List<RegisteredTool> = tools.values.sortedBy { it.spec.name }

    fun specs(): List<ToolSpec> = all().map { it.spec }

    /** Schemas for the OpenAI/Ollama tool-calling format. */
    fun openAiSchemas(include: Set<String> = tools.keys): List<JsonObject> =
        all().filter { it.spec.name in include }.map { ToolSchema.toOpenAiTool(it.spec) }

    fun ollamaSchemas(include: Set<String> = tools.keys): List<JsonObject> =
        all().filter { it.spec.name in include }.map { ToolSchema.toOllamaTool(it.spec) }

    companion object {
        val NAME_PATTERN = Regex("^[a-z][a-z0-9_]{2,63}$")
    }
}
